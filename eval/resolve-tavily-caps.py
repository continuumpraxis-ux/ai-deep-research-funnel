#!/usr/bin/env python3
"""Change 1 evidence: resolve each Tavily tool block in the served config and in the
capped variant against the REAL TavilyWebSearchToolConfig schema, and print the
effective values (including the derived search_depth the plugin computes)."""
import pathlib, yaml
from tavily_web_search.register import TavilyWebSearchToolConfig

FILES = {
    "served  (config_web_deepseek_researchers.yml)":
        "/root/aiq-gate/configs/config_web_deepseek_researchers.yml",
    "capped  (config_web_tavily_capped.yml)":
        "/mnt/c/Users/<user>/stacks/ai-ops-blueprint/aiq/configs/config_web_tavily_capped.yml",
}

for label, path in FILES.items():
    p = pathlib.Path(path)
    if not p.exists():
        print(f"\n### {label}: MISSING ({path})"); continue
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    print(f"\n### {label}")
    for name, block in (doc.get("functions") or {}).items():
        if not isinstance(block, dict) or block.get("_type") != "tavily_web_search":
            continue
        kwargs = {k: v for k, v in block.items() if k != "_type"}
        cfg = TavilyWebSearchToolConfig(**kwargs)
        derived_depth = "advanced" if cfg.advanced_search else "basic"
        print(f"  {name}:")
        print(f"    max_results        = {cfg.max_results}")
        print(f"    advanced_search    = {cfg.advanced_search}   -> search_depth = {derived_depth}")
        print(f"    include_answer     = {cfg.include_answer!r}")
        print(f"    max_content_length = {cfg.max_content_length}")
        print(f"    max_retries        = {cfg.max_retries}")
        print(f"    api_base_url       = {cfg.api_base_url!r}")
print("\nSchema fields that exist:", sorted(TavilyWebSearchToolConfig.model_fields))
for absent in ("search_depth", "chunks_per_source"):
    print(f"  '{absent}' in schema: {absent in TavilyWebSearchToolConfig.model_fields}")
