# Known Limits

These limits ship with the artifact on purpose. Each one comes from the evaluation record of 2026-10-20.

1. **Citation precision is the weak metric.** Of 10 spot-checked sources, 9 could be content-checked: 4 fully supported the claim and 5 had precision defects (a wrong year, a misattributed sub-claim, an interpolated pair of percentiles, an unsupported median, and an off-by-one citation key). The tenth source was a dead link. Fabrication is zero, but precision is not clean yet.

2. **The researcher note cap starves source pools.** The cap is 8,192 tokens. It truncated 5 researcher notes on Q02, which starved that question's source pool and visibly lowered its citation count.

3. **A report can lose citation integrity completely.** Q06 shows this. The citation integrity gate catches it and refuses to publish, but the run's cost ($0.20) is spent either way. The gate prevents bad output. It does not prevent wasted spend.

4. **The writer can loop without committing.** Q08 shows this. Right now the only loop guard is the server-side 3,600 s graph budget, which raised `DeepResearchExecutionTimeout` on Q08. The eval driver's 5,400 s cancel deadline did not fire.

5. **The architecture is hybrid by necessity, not by preference.** The build runs on a Windows on ARM laptop (Lenovo Yoga, NVIDIA RTX Spark). Components that needed DGX OS or x86 Linux were excluded on vendor evidence:
   - NemoClaw: NVIDIA's own support matrix lists DGX OS hardware only, with no Windows or WSL2 path.
   - OpenShell and Milvus: excluded in this build.
   - Several container candidates: their registry manifests are amd64-only. The manifest takes precedence over NGC metadata.

6. **The citation-precision components are staged but not evaluated.** The embedder `nvidia/Nemotron-3.5-Embed-1B-BF16` and the reranker `nvidia/llama-nemotron-rerank-vl-1b-v2` are staged on the build machine for the citation-precision leg. None of the results in [EVAL-TABLE.md](EVAL-TABLE.md) include them, and no precision improvement is claimed.
