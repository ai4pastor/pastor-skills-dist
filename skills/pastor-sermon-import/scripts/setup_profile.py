#!/usr/bin/env python3
"""Interactive config wizard for pastor-sermon-import.

This script writes the single supported config contract:
the path reported by scripts/paths.py (default ~/.pastor-sermon-import/config.json)
"""
from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from config_loader import default_config, save_config, validate_config


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def ask_list(prompt: str) -> list[str]:
    value = ask(prompt + " (쉼표로 구분, 없으면 빈칸)")
    return [item.strip() for item in value.split(",") if item.strip()]


def ask_choice(prompt: str, choices: set[str], default: str) -> str:
    while True:
        value = ask(prompt, default)
        if value in choices:
            return value
        print(f"허용값: {', '.join(sorted(choices))}")


def main() -> int:
    print("pastor-sermon-import 설정을 시작합니다.")
    print("실제 설교 파일이나 vault 노트는 수정하지 않습니다.\n")

    config: dict[str, Any] = default_config()
    config["created"] = datetime.now().isoformat(timespec="minutes")

    config["vault"]["path"] = ask("Obsidian vault 폴더 경로")
    config["input"]["sermon_sources"] = ask_list("설교 원본 파일 폴더")
    config["output"]["main_sermon_folder"] = ask("vault 안 메인 설교 노트 저장 폴더")
    config["output"]["fragment_folder"] = ask("vault 안 설교 조각 노트 저장 폴더")
    config["output"]["log_folder"] = ask("처리 로그 저장 폴더", ".vault-sermon-import/logs")

    config["naming"]["main_note_pattern"] = ask("메인 설교 노트 파일명 규칙", "{date}_{title}_{main_passage}.md")
    config["naming"]["fragment_note_pattern"] = ask("설교 조각 노트 파일명 규칙", "{sermon_id}_{title}.md")
    config["naming"]["collision_policy"] = ask_choice("기존 노트 충돌 처리 (ask/skip)", {"ask", "skip"}, "ask")

    config["bible"]["link_style"] = ask("성경구절 wikilink 형식: {normalized} 포함 필수", "[[{normalized}]]")
    config["bible"]["range_policy"] = ask_choice("범위 구절 처리 (expand_each_verse/keep_range)", {"expand_each_verse", "keep_range"}, "expand_each_verse")
    note_folder = ask("성경구절 노트 폴더 (없으면 빈칸)")
    config["bible"]["note_folder"] = note_folder

    use_word = ask("WORD 분류 사용 여부 (yes/no)", "no").lower() in {"y", "yes", "예", "네", "true"}
    config["classification"]["use_word"] = use_word
    if use_word:
        config["classification"]["world_values"] = ask_list("world 허용 목록")
        config["classification"]["outcome_values"] = ask_list("outcome 허용 목록")
        config["classification"]["route_values"] = ask_list("route 허용 목록")
        config["classification"]["doctrine_values"] = ask_list("doctrine 허용 목록")

    try:
        validate_config(config)
    except ValueError as exc:
        print(f"설정 오류: {exc}")
        return 1

    print("\n설정 미리보기:\n")
    print(json.dumps(config, ensure_ascii=False, indent=2))
    confirm = ask("이 설정을 저장할까요? 저장하려면 OK 저장")
    if confirm != "OK 저장":
        print("저장하지 않았습니다.")
        return 1

    path = save_config(config)
    print(f"저장 완료: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
