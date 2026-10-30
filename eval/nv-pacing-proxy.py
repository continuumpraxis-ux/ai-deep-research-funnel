#!/usr/bin/env python3
"""NVIDIA API pacing proxy (built for this project, 2026-10-20).

Sits between the AI-Q server and https://integrate.api.nvidia.com.
Purpose: the trial-tier per-minute cap is tripped by burst fan-out plus
instant retries (NAT retries at 0.25s spacing), not by total volume.
This proxy meters requests per model through a token bucket so bursts
become a stream under the cap. On an upstream 429 it pauses that
model's bucket for the measured ~60s reset window and requeues the
request, so callers see latency instead of failure.

Env knobs:
  NV_PROXY_RATE_PER_MIN   per-model sustained rate (default 24)
  NV_PROXY_GLOBAL_PER_MIN global sustained rate (default 48)
  NV_PROXY_PAUSE_S        bucket pause after upstream 429 (default 60)
  NV_PROXY_MAX_ATTEMPTS   upstream attempts per request (default 12)
  NV_PROXY_PORT           listen port (default 18123)
"""
import asyncio
import json
import os
import time
from collections import defaultdict

import aiohttp
from aiohttp import web

UPSTREAM = "https://integrate.api.nvidia.com"
RATE = float(os.environ.get("NV_PROXY_RATE_PER_MIN", "24"))
GLOBAL_RATE = float(os.environ.get("NV_PROXY_GLOBAL_PER_MIN", "48"))
PAUSE_S = float(os.environ.get("NV_PROXY_PAUSE_S", "60"))
MAX_ATTEMPTS = int(os.environ.get("NV_PROXY_MAX_ATTEMPTS", "12"))
PORT = int(os.environ.get("NV_PROXY_PORT", "18123"))

counters = {"proxied": 0, "upstream_429": 0, "requeued": 0, "waits": 0}


class Bucket:
    """Token bucket with a pause-until timestamp."""

    def __init__(self, per_min: float):
        self.capacity = max(2.0, per_min / 6.0)  # ~10s of burst
        self.tokens = self.capacity
        self.refill_per_s = per_min / 60.0
        self.last = time.monotonic()
        self.pause_until = 0.0
        self.lock = asyncio.Lock()

    async def acquire(self):
        while True:
            async with self.lock:
                now = time.monotonic()
                elapsed = now - self.last
                self.last = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_s)
                wait = 0.0
                if now < self.pause_until:
                    wait = self.pause_until - now
                elif self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                else:
                    wait = (1.0 - self.tokens) / self.refill_per_s
            counters["waits"] += 1
            await asyncio.sleep(min(wait, 5.0))

    def pause(self, seconds: float):
        self.pause_until = time.monotonic() + seconds


buckets = defaultdict(lambda: Bucket(RATE))
global_bucket = Bucket(GLOBAL_RATE)


def model_of(body: bytes) -> str:
    try:
        data = json.loads(body)
        return str(data.get("model") or "unknown")
    except Exception:
        return "unknown"


async def handle(request: web.Request) -> web.StreamResponse:
    body = await request.read()
    model = model_of(body) if request.path.endswith("chat/completions") else "other"
    bucket = buckets[model]
    url = UPSTREAM + request.path_qs
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}
    session: aiohttp.ClientSession = request.app["session"]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        await global_bucket.acquire()
        await bucket.acquire()
        try:
            async with session.request(request.method, url, data=body, headers=headers) as up:
                if up.status == 429:
                    counters["upstream_429"] += 1
                    counters["requeued"] += 1
                    bucket.pause(PAUSE_S)
                    await up.read()
                    print(f"[{time.strftime('%H:%M:%S')}] 429 model={model} attempt={attempt} pausing {PAUSE_S:.0f}s", flush=True)
                    continue
                counters["proxied"] += 1
                resp = web.StreamResponse(status=up.status, reason=up.reason)
                for k, v in up.headers.items():
                    if k.lower() not in ("transfer-encoding", "content-length", "connection"):
                        resp.headers[k] = v
                await resp.prepare(request)
                async for chunk in up.content.iter_chunked(8192):
                    await resp.write(chunk)
                await resp.write_eof()
                return resp
        except aiohttp.ClientError as exc:
            print(f"[{time.strftime('%H:%M:%S')}] upstream error model={model}: {exc}", flush=True)
            await asyncio.sleep(2.0)
            continue
    return web.Response(status=503, text="pacing proxy: upstream attempts exhausted")


async def healthz(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "counters": counters,
                              "rate_per_min": RATE, "global_per_min": GLOBAL_RATE})


async def on_startup(app: web.Application):
    app["session"] = aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=64),
        timeout=aiohttp.ClientTimeout(total=None, connect=15, sock_connect=15),
    )


async def on_cleanup(app: web.Application):
    await app["session"].close()


def main():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/healthz", healthz)
    app.router.add_route("*", "/{tail:.*}", handle)
    print(f"nv-pacing-proxy listening on 127.0.0.1:{PORT} rate={RATE}/min global={GLOBAL_RATE}/min pause={PAUSE_S}s", flush=True)
    web.run_app(app, host="127.0.0.1", port=PORT, access_log=None)


if __name__ == "__main__":
    main()
