# SPDX-License-Identifier: Apache-2.0
"""DeepSeek Search/Fetch as an alternate AI-Q search provider.

Implements the SAME tool contract as the shipped providers
(`async (question: str) -> str`, yielded via FunctionInfo.from_fn), so the
planner, writer and eval harness run unchanged apart from the provider.
No core harness code is modified or forked.

API contract (DeepSeek API docs, 2026-10-20):
  Search  POST {base}/v1/tools/search   body: query (1-128 chars, REQUIRED),
          count (1-50, default 10), need_content (bool, default false),
          ori_question, localization.
          -> {"results": [{url, title, snippet, summary, content,
                           rerank_score 0-3, authority 0-4 (-1 unknown),
                           site_name, site_icon, date}]}
  Fetch   POST {base}/v1/tools/fetch    body: url (REQUIRED)
          -> {"title": ..., "content": "<page as Markdown>"}

Billing: $0.75 per 1,000 SUCCESSFUL requests for each of Search and Fetch.
Billable = HTTP 200 AND a result produced (non-empty results / page content).
Empty, failed and timed-out requests are NOT billed. `count` does not affect price.
Every emitted source is stamped provenance="deepseek-search" (durable-record rule).
The API key is read from the process environment only (DEEPSEEK_API_KEY) and is
never written to a file or a log.
"""

import asyncio
import html
import json
import logging
import os
import re
import time

from pydantic import Field
from pydantic import SecretStr

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

logger = logging.getLogger(__name__)

PROVENANCE = "deepseek-search"
_QUERY_MAX = 128  # DeepSeek hard limit: query must be 1-128 chars
_INVALID_XML_CHARACTERS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF￾￿]")
_DEFAULT_USAGE_LOG = "/mnt/c/Users/<user>/stacks/ai-ops-blueprint/eval/results/deepseek-search/usage.jsonl"


def _xml_text(value: object) -> str:
    return _INVALID_XML_CHARACTERS.sub("", "" if value is None else str(value))


def _render_document(url: object, title: object, content: object, rerank: object, authority: object) -> str:
    """Same trusted <Document href=...> envelope the shipped providers emit, plus provenance."""
    url_text = html.escape(_xml_text(url), quote=True)
    title_text = html.escape(_xml_text(title), quote=True)
    content_text = html.escape(_xml_text(content), quote=True)
    extra = f' provenance="{PROVENANCE}" rerank_score="{_xml_text(rerank)}" authority="{_xml_text(authority)}"'
    return (
        f'<Document href="{url_text}"{extra}>\n'
        f"<title>\n{title_text}\n</title>\n"
        f"{content_text}\n</Document>"
    )


def _record_usage(path: str | None, kind: str, billed: bool, detail: dict) -> None:
    """Append one usage record for cost accounting. Never contains the API key."""
    if not path:
        return
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "provider": PROVENANCE, "kind": kind,
           "billed": bool(billed), **detail}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:  # usage logging must never break a run
        logger.warning("deepseek usage log write failed: %s", exc)


def _key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "")


# --------------------------------------------------------------------------- search


class DeepSeekWebSearchToolConfig(FunctionBaseConfig, name="deepseek_web_search"):
    """Retrieves relevant contexts from web search (using DeepSeek Search)."""

    count: int = Field(default=3, ge=1, le=50, description="Results per query (DeepSeek `count`)")
    need_content: bool = Field(default=False,
                               description="Ask DeepSeek for full page content; when false `content` is empty "
                                           "and `summary` is used instead (cheaper payload)")
    max_content_length: int | None = Field(default=1000, description="Truncate each result's text")
    api_key: SecretStr | None = Field(default=None, description="Overrides DEEPSEEK_API_KEY if set")
    api_base_url: str = Field(default="https://api.deepseek.com", description="DeepSeek API base URL")
    max_retries: int = Field(default=3, description="Retries for 408/429/5xx")
    request_timeout: float = Field(default=60.0, description="Per-request timeout in seconds")
    usage_log: str | None = Field(default=_DEFAULT_USAGE_LOG, description="JSONL usage/cost record path")


@register_function(config_type=DeepSeekWebSearchToolConfig)
async def deepseek_web_search(tool_config: DeepSeekWebSearchToolConfig, builder: Builder):
    import httpx

    if tool_config.api_key and not _key():
        os.environ["DEEPSEEK_API_KEY"] = tool_config.api_key.get_secret_value()

    if not _key():
        async def _stub(question: str) -> str:
            """Web search tool (unavailable - missing DEEPSEEK_API_KEY)."""
            return ("Error: DeepSeek search is unavailable because DEEPSEEK_API_KEY is not set. "
                    "Set it in the process environment and restart.")
        logger.warning("DEEPSEEK_API_KEY not found; deepseek_web_search registered as an error stub.")
        yield FunctionInfo.from_fn(_stub, description=_stub.__doc__)
        return

    url = f"{tool_config.api_base_url.rstrip('/')}/v1/tools/search"

    async def _deepseek_web_search(question: str) -> str:
        """Retrieves relevant contexts from web search (using DeepSeek Search) for the given question.

        Args:
            question (str): The question to be answered. Truncated to 128 characters (DeepSeek limit).

        Returns:
            str: The web search results containing relevant documents and their URLs.
        """
        q = (question or "").strip()
        if len(q) > _QUERY_MAX:
            q = q[: _QUERY_MAX - 3] + "..."
        if not q:
            return "Search returned no results"

        body = {"query": q, "count": tool_config.count, "need_content": tool_config.need_content}
        headers = {"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"}

        def _clip(text: object) -> str:
            text = "" if text is None else str(text)
            cap = tool_config.max_content_length
            return text[: cap - 3] + "..." if cap and len(text) > cap else text

        last_err = ""
        for attempt in range(tool_config.max_retries):
            try:
                async with httpx.AsyncClient(timeout=tool_config.request_timeout) as client:
                    resp = await client.post(url, json=body, headers=headers)
                if resp.status_code in (408, 429) or resp.status_code >= 500:
                    last_err = f"HTTP {resp.status_code}"
                    _record_usage(tool_config.usage_log, "search", False,
                                  {"status": resp.status_code, "query_chars": len(q), "results": 0})
                    await asyncio.sleep(2 ** attempt)
                    continue
                if resp.status_code != 200:
                    _record_usage(tool_config.usage_log, "search", False,
                                  {"status": resp.status_code, "query_chars": len(q), "results": 0})
                    return f"Error: DeepSeek search failed - HTTP {resp.status_code}: {resp.text[:300]}"

                payload = resp.json()
                results = payload.get("results") or []
                if not isinstance(results, list) or not results:
                    # Empty results are NOT billed.
                    _record_usage(tool_config.usage_log, "search", False,
                                  {"status": 200, "query_chars": len(q), "results": 0})
                    return "Search returned no results"

                # HTTP 200 with a non-empty results array => billable.
                _record_usage(tool_config.usage_log, "search", True,
                              {"status": 200, "query_chars": len(q), "results": len(results),
                               "urls": [r.get("url") for r in results if isinstance(r, dict)]})

                docs = []
                for r in results:
                    if not isinstance(r, dict):
                        continue
                    # Prefer the model-oriented summary; fall back to content then snippet.
                    text = r.get("summary") or r.get("content") or r.get("snippet") or ""
                    docs.append(_render_document(r.get("url"), r.get("title"), _clip(text),
                                                 r.get("rerank_score"), r.get("authority")))
                rendered = "\n\n---\n\n".join(docs)
                return rendered if rendered else "Search returned no results"

            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
                if attempt == tool_config.max_retries - 1:
                    _record_usage(tool_config.usage_log, "search", False,
                                  {"status": "exception", "query_chars": len(q), "results": 0})
                    return f"Error: DeepSeek search failed - {last_err}"
                await asyncio.sleep(2 ** attempt)

        return f"Error: DeepSeek search failed - {last_err}"

    yield FunctionInfo.from_fn(_deepseek_web_search, description=_deepseek_web_search.__doc__)


# ---------------------------------------------------------------------------- fetch


class DeepSeekWebFetchToolConfig(FunctionBaseConfig, name="deepseek_web_fetch"):
    """Fetches a web page as Markdown (using DeepSeek Fetch)."""

    max_content_length: int | None = Field(default=8000, description="Truncate the returned Markdown")
    api_key: SecretStr | None = Field(default=None, description="Overrides DEEPSEEK_API_KEY if set")
    api_base_url: str = Field(default="https://api.deepseek.com", description="DeepSeek API base URL")
    max_retries: int = Field(default=3, description="Retries for 408/429/5xx")
    request_timeout: float = Field(default=60.0, description="Per-request timeout in seconds")
    usage_log: str | None = Field(default=_DEFAULT_USAGE_LOG, description="JSONL usage/cost record path")


@register_function(config_type=DeepSeekWebFetchToolConfig)
async def deepseek_web_fetch(tool_config: DeepSeekWebFetchToolConfig, builder: Builder):
    import httpx

    if tool_config.api_key and not _key():
        os.environ["DEEPSEEK_API_KEY"] = tool_config.api_key.get_secret_value()

    if not _key():
        async def _stub(url: str) -> str:
            """Page fetch tool (unavailable - missing DEEPSEEK_API_KEY)."""
            return "Error: DeepSeek fetch is unavailable because DEEPSEEK_API_KEY is not set."
        yield FunctionInfo.from_fn(_stub, description=_stub.__doc__)
        return

    endpoint = f"{tool_config.api_base_url.rstrip('/')}/v1/tools/fetch"

    async def _deepseek_web_fetch(url: str) -> str:
        """Fetches the given web page and returns it as Markdown (using DeepSeek Fetch).

        Args:
            url (str): The http(s) URL to fetch.

        Returns:
            str: The page rendered as Markdown, wrapped in the standard Document envelope.
        """
        target = (url or "").strip()
        if not target.lower().startswith(("http://", "https://")):
            return "Error: DeepSeek fetch requires an http(s) URL."

        headers = {"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"}
        last_err = ""
        for attempt in range(tool_config.max_retries):
            try:
                async with httpx.AsyncClient(timeout=tool_config.request_timeout) as client:
                    resp = await client.post(endpoint, json={"url": target}, headers=headers)
                if resp.status_code in (408, 429) or resp.status_code >= 500:
                    last_err = f"HTTP {resp.status_code}"
                    _record_usage(tool_config.usage_log, "fetch", False,
                                  {"status": resp.status_code, "url": target, "chars": 0})
                    await asyncio.sleep(2 ** attempt)
                    continue
                if resp.status_code != 200:
                    _record_usage(tool_config.usage_log, "fetch", False,
                                  {"status": resp.status_code, "url": target, "chars": 0})
                    return f"Error: DeepSeek fetch failed - HTTP {resp.status_code}: {resp.text[:300]}"

                payload = resp.json()
                content = payload.get("content") or ""
                if not content:
                    # No page content returned => NOT billed.
                    _record_usage(tool_config.usage_log, "fetch", False,
                                  {"status": 200, "url": target, "chars": 0})
                    return "Fetch returned no content"

                _record_usage(tool_config.usage_log, "fetch", True,
                              {"status": 200, "url": target, "chars": len(content)})
                cap = tool_config.max_content_length
                if cap and len(content) > cap:
                    content = content[: cap - 3] + "..."
                return _render_document(target, payload.get("title"), content, "", "")

            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
                if attempt == tool_config.max_retries - 1:
                    _record_usage(tool_config.usage_log, "fetch", False,
                                  {"status": "exception", "url": target, "chars": 0})
                    return f"Error: DeepSeek fetch failed - {last_err}"
                await asyncio.sleep(2 ** attempt)

        return f"Error: DeepSeek fetch failed - {last_err}"

    yield FunctionInfo.from_fn(_deepseek_web_fetch, description=_deepseek_web_fetch.__doc__)
