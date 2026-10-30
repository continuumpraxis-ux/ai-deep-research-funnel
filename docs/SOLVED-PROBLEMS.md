# Problems Solved on Evidence

Each problem below was diagnosed from the run record and closed with a measured result.

## The free route is not viable

The OpenRouter free-tier variant (researcher `nvidia/nemotron-3-super-120b-a12b:free`) completed 0 of 10 questions under 429 saturation, with 16,414 OpenRouter request lines in the server log. It was measured at $0, so the ceiling is empirical, not assumed. Evidence: [`eval/evidence/free-researcher/RESULT.md`](../eval/evidence/free-researcher/RESULT.md).

## The NVIDIA rate cap

NVIDIA's per-minute burst cap on the hosted Nemotron endpoint broke the Nemotron roles in two earlier, unpaced Q01 attempts:

- **46** HTTP 429 responses across the orchestrator, planner and writer in one attempt. A probe then settled the class: a 429 followed moments later by a 200, which is a short per-minute burst cap resetting in about a minute, not a depleted quota.
- **90** HTTP 429 responses in the other, clean unpaced attempt. It failed with the same error fingerprint.

Waiting for the cap to reset could not fix it, because a deep-research run re-saturates the cap within minutes. The fix was a pacing proxy: a token bucket for each model plus a global bucket, with a 60 s pause and requeue on any upstream 429, so rejections become latency. In the final evaluation run, 545 Nemotron calls went through the proxy, 125 upstream 429s were absorbed as pauses, and none reached the funnel as a failure. Evidence: [`eval/evidence/deepseek/DIAGNOSIS.md`](../eval/evidence/deepseek/DIAGNOSIS.md), [`eval/evidence/EVAL10-RESULT.md`](../eval/evidence/EVAL10-RESULT.md).

## The two-day blocker

The old nim client's 60-second read limit collided with the proxy's 60-second 429 pauses and with long non-streamed generations. It was root-caused by elimination. A 170k-character call returned in 5.3 seconds, which ruled out payload size, and a larger 175,916-character call succeeded on retry. The fix was swapping the writer client and setting `request_timeout` to 600. Q01 then passed with 41 body citations at $0.19. In the final run, 129 Nemotron calls took longer than 60 s and all of them succeeded.

## Verified negatives

These were ruled out on vendor evidence, not preference:

- **NemoClaw:** NVIDIA's own matrix lists DGX OS hardware only, with no Windows or WSL2 path.
- **OpenShell and Milvus:** excluded in this build.
- **Several container candidates:** their registry manifests are amd64-only. The manifest takes precedence over NGC metadata, per the download compatibility gate.
