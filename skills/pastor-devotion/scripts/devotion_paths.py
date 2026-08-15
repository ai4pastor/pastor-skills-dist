#!/usr/bin/env python3
"""묵상 스킬의 설정 홈과 나만의 규칙 파일 경로를 JSON으로 출력한다.

설정 홈은 설교 정리 스킬과 같은 곳(~/.pastor-sermon-import, PASTOR_SERMON_IMPORT_HOME
으로 재정의)을 쓰되, 규칙 파일은 devotion_rules.md 로 분리한다 — 조각 문체 규칙
(custom_rules.md)과 묵상 규칙이 서로를 덮지 않게.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import HOME_ENV_VAR, home  # noqa: E402


def main() -> int:
    base = home()
    rules = base / "devotion_rules.md"
    print(json.dumps({
        "home": str(base),
        "devotion_rules": str(rules),
        "devotion_rules_exists": rules.exists(),
        "env_var": HOME_ENV_VAR,
        "overridden": bool(os.environ.get(HOME_ENV_VAR)),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
