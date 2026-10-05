#!/usr/bin/env python3
"""pastor-visit-import 의 경로 계약. 표준 라이브러리만 쓴다.

설정 홈은 다른 목회자 스킬과 같은 곳(~/.pastor-sermon-import, PASTOR_SERMON_IMPORT_HOME 으로 재정의).

    <홈>/visit_import.json          이 스킬의 설정 (볼트·성도 폴더·심방일지 폴더)
    <홈>/visit_rules.md             나만의 규칙 — 추가 헤딩 동의어 등 (업데이트에 안전)
    <홈>/visit-import/work/         audit.json · plan.json · manifest (작업 파일 — 교인 이름이 들어가므로 홈 밖으로 옮기지 말 것)
    <홈>/visit-import/backups/<ts>/ 쓰기 전 원본 사본 (볼트 밖 — 볼트 안에 두면 플러그인·Bases 가 또 색인한다)

    python3 scripts/visit_env.py                       # 경로·설정 JSON
    python3 scripts/visit_env.py --ensure              # 폴더 생성
    python3 scripts/visit_env.py --save vault=... member_folder=... visit_folder=...
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import HOME_ENV_VAR, home  # noqa: E402


def config_path() -> Path:
    return home() / "visit_import.json"


def rules_path() -> Path:
    return home() / "visit_rules.md"


def work_dir() -> Path:
    return home() / "visit-import" / "work"


def backups_dir() -> Path:
    return home() / "visit-import" / "backups"


def load_config() -> dict:
    p = config_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(cfg: dict) -> Path:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def vault_hint() -> str:
    """다른 pastor 스킬이 기억한 볼트 경로 (config.json 의 vault.path) — 기본값 제안용."""
    p = home() / "config.json"
    if not p.is_file():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""
    vault = data.get("vault") if isinstance(data, dict) else None
    return str(vault.get("path", "")) if isinstance(vault, dict) else ""


def describe() -> dict:
    cfg = load_config()
    return {
        "home": str(home()),
        "config": str(config_path()),
        "config_exists": config_path().is_file(),
        "vault": cfg.get("vault", ""),
        "member_folder": cfg.get("member_folder", ""),
        "visit_folder": cfg.get("visit_folder", ""),
        "vault_hint": vault_hint(),
        "rules": str(rules_path()),
        "rules_exists": rules_path().is_file(),
        "work": str(work_dir()),
        "backups": str(backups_dir()),
        "env_var": HOME_ENV_VAR,
        "overridden": bool(os.environ.get(HOME_ENV_VAR)),
    }


def main(argv: list[str]) -> int:
    if "--ensure" in argv:
        work_dir().mkdir(parents=True, exist_ok=True)
        backups_dir().mkdir(parents=True, exist_ok=True)
    if "--save" in argv:
        cfg = load_config()
        for kv in argv[argv.index("--save") + 1:]:
            if "=" in kv:
                k, v = kv.split("=", 1)
                cfg[k.strip()] = v.strip()
        save_config(cfg)
    print(json.dumps(describe(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    raise SystemExit(main(sys.argv[1:]))
