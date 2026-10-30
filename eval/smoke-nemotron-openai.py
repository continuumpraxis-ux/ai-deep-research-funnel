#!/usr/bin/env python3
"""Exact-shape smoke for the Nemotron client swap: ONE small Nemotron call through the NAT `openai`
LangChain client (ChatOpenAI), built from the nemotron_ultra_llm block of config_web_deepseek_search.yml,
with a `task` tool bound the way the orchestrator binds tools. NVIDIA key from process env only.
"""
import asyncio, os, sys, time
import yaml

CFG = "/mnt/c/Users/<user>/stacks/ai-ops-blueprint/aiq/configs/config_web_deepseek_search.yml"
BLOCK = sys.argv[1] if len(sys.argv) > 1 else "nemotron_ultra_llm"


async def main():
    from nat.llm.openai_llm import OpenAIModelConfig
    from nat.plugins.langchain.llm import openai_langchain
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.tools import tool

    block = dict(yaml.safe_load(open(CFG))["llms"][BLOCK])
    assert block.pop("_type") == "openai", "block is not _type: openai"
    block["api_key"] = os.environ["NVIDIA_API_KEY"]
    cfg = OpenAIModelConfig(**block)
    shown = {k: v for k, v in block.items() if k != "api_key"}
    print(f"[{BLOCK}] config (key omitted): {shown}")

    @tool
    def task(subagent_type: str, description: str) -> str:
        """Delegate work to a subagent."""
        return "ok"

    obj = openai_langchain(cfg, None)
    async with obj as llm:
        print("client:", type(llm).__name__, "timeout:", getattr(llm, "request_timeout", None),
              "extra_body:", getattr(llm, "extra_body", None))
        bound = llm.bind_tools([task])
        msgs = [SystemMessage(content="You are the orchestrator. Delegate with the task tool."),
                HumanMessage(content="Delegate one research batch on 'solo AI-agent operator revenue' to researcher-agent.")]
        t0 = time.monotonic()
        try:
            out = await bound.ainvoke(msgs)
            dt = time.monotonic() - t0
            print(f"HTTP OK in {dt:.1f} s")
            print("tool_calls:", out.tool_calls)
            print("content:", (out.content or "")[:200])
            print("usage:", getattr(out, "usage_metadata", None))
            print("SMOKE:", "PASS" if out.tool_calls else "PASS (no tool call, but 200)")
        except Exception as e:  # noqa: BLE001
            dt = time.monotonic() - t0
            print(f"SMOKE: FAIL after {dt:.1f} s -> {type(e).__name__}: {str(e)[:1500]}")


asyncio.run(main())
