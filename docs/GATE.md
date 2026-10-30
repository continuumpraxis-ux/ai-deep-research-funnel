# The Citation Integrity Gate, and the Q06 Refusal

This document describes the funnel's citation integrity gate and documents
the one recorded case of it refusing a finished report: question Q06 of the
ten-question evaluation run of 2026-10-20. Everything below is taken from
that run's own records (job record, report endpoint response, server log,
and the evaluation results table). The refusal was a natural failure of a
real run. It was not staged, scripted, or reenacted.

## What the gate is

The funnel's last step before a report exists is a verification pass. While
a run executes, every source the researchers retrieve is entered into the
run's source registry. When the writer finishes its draft, the gate checks
the draft's citations against that registry:

- A citation counts only if it matches a source the run actually retrieved.
- If the set of valid citations is empty, verification raises
  `CitationIntegrityError` and the run fails.
- On a refusal, no report is published or persisted. The job ends in a
  failure state with the error recorded, and the report endpoint returns no
  report.

In the source tree the check lives in the citation verification module
(`citation_verification.py`), invoked from the deep researcher agent's
`verify_citations` step.

## The Q06 run

- Question: "How are API pricing changes and model deprecations affecting
  independent AI developers, and what mitigation patterns reduce that risk?"
- Job ID: `439044a5-9071-445d-9c5c-53da9586c311`
- Submitted: 2026-10-20 16:50:29 (America/Phoenix)
- Failed: 2026-10-20 17:04:43, after 854 seconds
- Metered cost: $0.20
- Final status: `failure`

The writer completed its draft (the writer-agent chain end is in the server
log). The gate then compared the draft's citations against the run's source
registry and found zero that matched. With `valid_citations` empty, the run
failed with `CitationIntegrityError` (`citation_integrity_lost`), error
fingerprint `b9793675134d`.

## The evidence

Job record, as returned by the jobs API and saved in the run's results:

```json
{"job_id":"439044a5-9071-445d-9c5c-53da9586c311","status":"failure","agent_type":null,"error":"job failed (CitationIntegrityError); check server logs for details","created_at":"2026-10-20T23:50:29.237306"}
```

Report endpoint response for the same job. This is the physical form of
"nothing persisted": there is no report.

```json
{"job_id":"439044a5-9071-445d-9c5c-53da9586c311","has_report":false,"report":null,"parent_job_id":null,"interaction_action":null,"result_kind":null}
```

The report file in the run's results folder is 0 bytes.

Server log lines (from the evaluation run's server log, 2,817,382 bytes,
extracted 2026-10-25):

```
2026-10-20 17:04:37 - ERROR - deep_researcher_agent.agents.deep_researcher.agent:453 - Deep Research Subagent failed (error_type=CitationIntegrityError detail_chars=23 ref=sha256:1374a3c4a24f)
2026-10-20 17:04:37 - ERROR - deep_researcher_api.jobs.runner:1094 - Job 439044a5-9071-445d-9c5c-53da9586c311 failed (error_type=CitationIntegrityError detail_chars=23 ref=sha256:1374a3c4a24f)
```

Results table row for the run:

```
Q06,failure,854,0,0,0,0.20,2026-10-20 16:50:29,2026-10-20 17:04:43,b9793675134d,"job failed (CitationIntegrityError); check server logs for details"
```

(Report characters 0, citation markers 0, body citations 0: the refused
draft contributed nothing to the published set.)

## Why this case is in the package

A fluent report with citations that do not trace to retrieved sources is
the central failure mode of automated research. The gate converts that
failure from a silent publishing error into a visible, recorded refusal:
the run is marked failed, the reason is in the job record and the server
log, and nothing reaches the reader. Of the ten evaluation questions,
eight passed the gate and were published; Q06 is the documented refusal,
and Q08 (an execution timeout at 3,958 seconds against the 3,600-second
server-side graph budget) is the second documented failure mode. Both are
carried in the evaluation table and the known-limits list, not hidden.

## Reproducibility note

Q06 cannot be reproduced on demand: it was a genuine model-side outcome of
that run, not a fixture. This document is therefore the gate-refusal
evidence of record, quoted from the run's own files, and the recorded run
in this package demonstrates the passing path end to end.
