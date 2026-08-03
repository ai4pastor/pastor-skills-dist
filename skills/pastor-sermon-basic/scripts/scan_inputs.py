#!/usr/bin/env python3
"""Scan sermon source files for pastor-sermon-import."""
from __future__ import annotations

from pathlib import Path
import json
import sys

SUPPORTED = {".docx", ".md", ".txt"}


def scan(path: Path) -> list[dict[str, object]]:
    if path.is_file():
        candidates = [path]
    else:
        candidates = [p for p in path.rglob("*") if p.is_file()]
    rows = []
    for p in sorted(candidates):
        rows.append({
            "path": str(p),
            "name": p.name,
            "suffix": p.suffix.lower(),
            "supported": p.suffix.lower() in SUPPORTED,
            "size": p.stat().st_size,
        })
    return rows


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: scan_inputs.py <file-or-folder>", file=sys.stderr)
        return 2
    path = Path(argv[1]).expanduser()
    if not path.exists():
        print(f"not found: {path}", file=sys.stderr)
        return 1
    rows = scan(path)
    print(json.dumps({"count": len(rows), "supported": sum(1 for r in rows if r["supported"]), "files": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
