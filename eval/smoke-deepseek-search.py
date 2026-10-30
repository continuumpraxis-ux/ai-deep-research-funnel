#!/usr/bin/env python3
"""Exact-shape smoke for the new DeepSeek search provider: ONE Search + ONE Fetch
driven through the registered tool functions (not raw curl). Records balance before
and after. Key is read from the process env only.
"""
import asyncio, inspect, json, os, sys
import httpx

BASE = "https://api.deepseek.com"


def balance():
    k = os.environ["DEEPSEEK_API_KEY"]
    r = httpx.post if False else httpx.get
    resp = httpx.get(f"{BASE}/user/balance", headers={"Authorization": f"Bearer {k}"}, timeout=20)
    d = resp.json()
    infos = d.get("balance_infos") or [{}]
    return d.get("is_available"), infos[0].get("total_balance")


def extract_callable(info):
    """Pull the async callable out of a NAT FunctionInfo, whatever it is named."""
    for attr in ("single_fn", "fn", "_single_fn", "stream_fn", "_fn"):
        f = getattr(info, attr, None)
        if f and callable(f):
            return f
    for name in dir(info):
        if name.startswith("__"):
            continue
        f = getattr(info, name, None)
        if callable(f) and (inspect.iscoroutinefunction(f) or inspect.isasyncgenfunction(f)):
            return f
    raise SystemExit(f"could not find callable on FunctionInfo; attrs={dir(info)}")


async def drive(regfn, cfg):
    """Run the plugin's registration (an async context manager) and return its tool callable."""
    obj = regfn(cfg, None)
    if hasattr(obj, "__aenter__"):
        async with obj as info:
            return extract_callable(info)
    async for info in obj:  # fallback if it is a plain async generator
        return extract_callable(info)
    raise SystemExit("registration yielded nothing")


async def main():
    from deepseek_web_search import register as R

    avail, before = balance()
    print(f"[balance BEFORE] is_available={avail} total={before}")

    # ---- ONE Search through the tool ----
    scfg = R.DeepSeekWebSearchToolConfig(count=3)
    search = await drive(R.deepseek_web_search, scfg)
    q = "credible revenue opportunities for solo AI-agent operators"
    print(f"\n[SEARCH] query ({len(q)} chars): {q}")
    out = await search(q)
    print(f"[SEARCH] returned {len(out)} chars")
    print(out[:1200])
    ok_search = out.startswith("<Document") and "provenance=\"deepseek-search\"" in out

    # pull the first URL out of the rendered documents for the fetch
    url = ""
    for part in out.split('<Document href="')[1:]:
        url = part.split('"')[0]
        if url.startswith("http"):
            break
    print(f"\n[SEARCH] first url: {url or '(none)'}")

    # ---- ONE Fetch through the tool ----
    ok_fetch = False
    if url:
        fcfg = R.DeepSeekWebFetchToolConfig()
        fetch = await drive(R.deepseek_web_fetch, fcfg)
        fout = await fetch(url)
        print(f"\n[FETCH] returned {len(fout)} chars")
        print(fout[:600])
        ok_fetch = fout.startswith("<Document")
    else:
        print("\n[FETCH] skipped - no url from search")

    avail2, after = balance()
    print(f"\n[balance AFTER] is_available={avail2} total={after}")
    try:
        spent = round(float(before) - float(after), 4)
        print(f"[spend this smoke] ${spent}")
    except Exception:
        pass

    print(f"\nSMOKE: search_usable={ok_search} fetch_usable={ok_fetch}")
    print("VERDICT:", "PASS" if (ok_search and ok_fetch) else "FAIL")


asyncio.run(main())
