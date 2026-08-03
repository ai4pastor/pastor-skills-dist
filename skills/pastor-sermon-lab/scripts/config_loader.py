#!/usr/bin/env python3
"""Lightweight settings for pastor-sermon-lab.

설정 파일을 목사님이 만들 필요가 없다. 스킬이 사용 중 알게 된 것만
~/.pastor-sermon-lab/memory.json에 조용히 기억한다:
- vault: Obsidian vault 경로 (첫 저장 때 한 번 물어봄)
- folders: 모드별로 마지막에 저장한 폴더 (다음번 기본값 제안용)
- congregation: 진단 때 들은 회중 소개 한 줄 (다음번 재사용 제안용)

성경구절 링크 등 동작 규칙은 수강생 공통 표준 고정값이다 (default_config).
"""
from __future__ import annotations

from pathlib import Path
import json
from typing import Any

CONFIG_DIR = Path.home() / ".pastor-sermon-lab"
MEMORY_PATH = CONFIG_DIR / "memory.json"
WORK_DIR = CONFIG_DIR / "work"
LOG_DIR = CONFIG_DIR / "logs"

# 진단 6차원 — 고정 키. 세션이 달라도 비교 가능해야 하므로 변경 금지.
DIAGNOSIS_DIMENSIONS = ["본문충실", "중심명제", "구조명료", "적용구체", "예화적절", "회중공감"]

# 모드별 웹 검증 검색 상한 (고정 기본값). 연구는 v3 밀도 확장에 맞춰 12.
SEARCH_BUDGET = {"research": 12, "enrich": 5, "diagnose": 3}


def default_config() -> dict[str, Any]:
    """동작 규칙 고정값. extract_bible_refs 등이 사용한다."""
    return {
        "bible": {
            "link_style": "[[{normalized}]]",
            "range_policy": "expand_each_verse",
            "max_range_expand": 50,
            "book_aliases": {},
            "frontmatter_key": "성경구절",
        },
    }


def default_memory() -> dict[str, Any]:
    return {
        "vault": "",
        "folders": {"research": "", "diagnose": "", "enrich": ""},
        "congregation": "",
    }


def load_memory(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path).expanduser() if path else MEMORY_PATH
    memory = default_memory()
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        memory["vault"] = str(data.get("vault", ""))
        folders = data.get("folders", {})
        for mode in memory["folders"]:
            memory["folders"][mode] = str(folders.get(mode, ""))
        memory["congregation"] = str(data.get("congregation", ""))
    return memory


def save_memory(memory: dict[str, Any], path: str | Path | None = None) -> Path:
    p = Path(path).expanduser() if path else MEMORY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    keep = {
        "vault": str(memory.get("vault", "")),
        "folders": {mode: str(memory.get("folders", {}).get(mode, "")) for mode in ("research", "diagnose", "enrich")},
        "congregation": str(memory.get("congregation", "")),
    }
    p.write_text(json.dumps(keep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def remember(vault: str | None = None, mode: str | None = None, folder: str | None = None,
             congregation: str | None = None, path: str | Path | None = None) -> dict[str, Any]:
    memory = load_memory(path)
    if vault:
        memory["vault"] = str(Path(vault).expanduser())
    if mode and folder is not None:
        memory["folders"][mode] = folder
    if congregation is not None:
        memory["congregation"] = congregation
    save_memory(memory, path)
    return memory


# 하위 호환: 일부 스크립트가 load_config를 import한다.
def load_config(path: str | Path | None = None, vault_path: str | None = None) -> dict[str, Any]:
    return default_config()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory", help="memory.json 경로 (기본 ~/.pastor-sermon-lab/memory.json)")
    parser.add_argument("--remember-vault")
    parser.add_argument("--remember-folder", nargs=2, metavar=("MODE", "FOLDER"))
    parser.add_argument("--remember-congregation")
    args = parser.parse_args()
    if args.remember_vault or args.remember_folder or args.remember_congregation is not None:
        mode, folder = (args.remember_folder or (None, None))
        out = remember(vault=args.remember_vault, mode=mode, folder=folder,
                       congregation=args.remember_congregation, path=args.memory)
    else:
        out = load_memory(args.memory)
    print(json.dumps(out, ensure_ascii=False, indent=2))
