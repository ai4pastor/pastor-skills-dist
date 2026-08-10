#!/usr/bin/env python3
"""Print the resolved config/work paths as JSON.

Every other step takes its paths from this output instead of hard-coding
`~/.pastor-sermon-import/...`. That keeps one place in charge of where files
land, so an isolated environment only has to set PASTOR_SERMON_IMPORT_HOME.

Usage:
    python3 scripts/paths.py                  # print paths
    python3 scripts/paths.py --ensure         # also create home/ and work/
    python3 scripts/paths.py --vault "{경로}"  # prefer vault-local config if present
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import HOME_ENV_VAR, config_path, home, work_dir  # noqa: E402


def resolve(vault_path: str | None = None) -> dict[str, object]:
    base = home()
    work = work_dir()
    cfg = config_path(vault_path)
    custom = base / "custom_rules.md"
    return {
        "home": str(base),
        "config": str(cfg),
        "config_exists": cfg.exists(),
        "custom_rules": str(custom),
        "custom_rules_exists": custom.exists(),
        "work": str(work),
        "fragments": str(work / "fragments.json"),
        "word": str(work / "word.json"),
        "fragments_dir": str(work / "fragments"),
        "word_dir": str(work / "word"),
        "extract_cache": str(work / "extracted"),
        "env_var": HOME_ENV_VAR,
        "overridden": bool(os.environ.get(HOME_ENV_VAR)),
    }


def main(argv: list[str]) -> int:
    vault = None
    ensure = False
    i = 0
    while i < len(argv):
        if argv[i] == "--ensure":
            ensure = True
        elif argv[i] == "--vault" and i + 1 < len(argv):
            i += 1
            vault = argv[i]
        else:
            print(f"unknown argument: {argv[i]}", file=sys.stderr)
            return 2
        i += 1

    info = resolve(vault)
    if ensure:
        for key in ("home", "work", "fragments_dir", "word_dir", "extract_cache"):
            Path(str(info[key])).mkdir(parents=True, exist_ok=True)
        info["ensured"] = True

    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
