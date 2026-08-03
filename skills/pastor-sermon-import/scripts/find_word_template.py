#!/usr/bin/env python3
"""볼트에서 분류(WORD) 정본 노트와 설교 템플릿을 찾는다.

    python3 scripts/find_word_template.py "{볼트 경로}" [--limit 8]

목사님이 분류표 경로를 외우고 있을 거라고 가정하지 않는다. 정본은 대개 두 곳 중
하나에 있다 — 옵시디언 템플릿 폴더, 또는 900번대 세팅·인덱스 폴더. 템플릿 폴더는
짐작하지 않고 `.obsidian` 설정에서 그대로 읽는다(코어 Templates, Templater).

설교 템플릿을 찾으면 그 frontmatter 키 순서도 돌려준다. 목사님이 이미 쓰는 필드
이름·순서에 맞춰 노트를 만들기 위한 근거다.

읽기 전용이다. 찾은 노트를 고치지 않는다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from note_utils import nfc  # noqa: E402

MAX_DEPTH = 4
MAX_NOTE_BYTES = 400_000
MAX_NOTES_PER_FOLDER = 200
SKIP_DIRS = {".trash", ".git", "node_modules", ".vault-sermon-import", "__pycache__"}

# 분류 노트 판별용 접두어 (parse_word_source.py 와 같은 계약)
AXIS_PREFIXES = {"world": "📩", "world_major": "📖", "outcome": "🏷", "route": "📝", "doctrine": "🔖"}
# 세팅·템플릿 성격 폴더 이름
SETTING_WORDS = ("900", "999", "설정", "세팅", "setting", "템플릿", "template", "meta",
                 "인덱스", "index", "가이드", "guide", "대시보드", "dashboard")
WORD_NOTE_WORDS = ("word", "분류", "속성", "taxonomy", "체계", "대시보드", "인덱스", "가이드")
SERMON_WORDS = ("설교", "말씀", "주일", "예배", "기도회", "sermon", "강해")
CLASSIFICATION_KEYS = ("world", "outcome", "route", "doctrine")


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def obsidian_template_folders(vault: Path) -> dict[str, object]:
    """`.obsidian` 설정에서 템플릿 폴더를 그대로 읽는다."""
    settings = vault / ".obsidian"
    core = str(read_json(settings / "templates.json").get("folder") or "").strip()
    templater = str(read_json(settings / "plugins" / "templater-obsidian" / "data.json")
                    .get("templates_folder") or "").strip()
    folders = [f for f in (core, templater) if f]
    return {
        "core_templates_folder": core,
        "templater_folder": templater,
        "folders": list(dict.fromkeys(folders)),
        "settings_present": settings.is_dir(),
    }


def frontmatter_keys(text: str) -> list[str]:
    """frontmatter 키를 나온 순서대로. YAML 파서를 쓰지 않는다 — "[[...]]" 값이 깨진다."""
    m = re.match(r"\A---\n(?P<body>.*?)\n---(?:\n|\Z)", text, re.DOTALL)
    if not m:
        return []
    keys: list[str] = []
    for line in m.group("body").splitlines():
        if not line or line.startswith((" ", "\t", "-")):
            continue
        kv = re.match(r"^([^:#]+):", line)
        if kv:
            key = kv.group(1).strip()
            if key and key not in keys:
                keys.append(key)
    return keys


def inspect_note(path: Path, vault: Path) -> dict | None:
    """분류 정본 후보인지. 접두어가 두 축 이상 나와야 인정한다."""
    try:
        if path.stat().st_size > MAX_NOTE_BYTES:
            return None
        text = nfc(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return None
    matched = {}
    for axis, prefix in AXIS_PREFIXES.items():
        count = len(re.findall(rf"\[\[{re.escape(prefix)}", text))
        if count:
            matched[axis] = count
    if len(matched) < 2:
        return None
    return {"path": str(path.relative_to(vault)), "matched_axes": matched,
            "total": sum(matched.values()), "frontmatter_keys": frontmatter_keys(text)}


def inspect_template(path: Path, vault: Path) -> dict | None:
    """설교 템플릿 후보인지. 파일명 또는 분류 필드로 판정한다."""
    try:
        if path.stat().st_size > MAX_NOTE_BYTES:
            return None
        text = nfc(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return None
    keys = frontmatter_keys(text)
    name_hit = any(word in nfc(path.stem).lower() for word in SERMON_WORDS)
    field_hit = any(key.lower() in CLASSIFICATION_KEYS for key in keys)
    if not (name_hit and keys):
        return None
    return {"path": str(path.relative_to(vault)), "frontmatter_keys": keys,
            "has_classification_fields": field_hit,
            "why": "파일명에 설교 관련 단어" + (" + 분류 필드" if field_hit else "")}


def walk_folders(vault: Path) -> list[Path]:
    out: list[Path] = []
    for path in vault.rglob("*"):
        if not path.is_dir():
            continue
        rel = path.relative_to(vault)
        if len(rel.parts) > MAX_DEPTH:
            continue
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts):
            continue
        out.append(rel)
    return out


def notes_in(vault: Path, rel: Path) -> list[Path]:
    try:
        return [p for p in sorted((vault / rel).iterdir())
                if p.is_file() and p.suffix == ".md"][:MAX_NOTES_PER_FOLDER]
    except OSError:
        return []


def search(vault: Path, limit: int) -> dict[str, object]:
    settings = obsidian_template_folders(vault)
    all_folders = walk_folders(vault)

    # 1순위: 옵시디언이 알려준 템플릿 폴더(와 그 하위). 2순위: 세팅·인덱스 성격 폴더.
    template_roots = [Path(f) for f in settings["folders"]]  # type: ignore[union-attr]
    ordered: list[tuple[Path, str]] = []
    seen_folders: set[Path] = set()

    def add(rel: Path, why: str) -> None:
        if rel in seen_folders:
            return
        seen_folders.add(rel)
        ordered.append((rel, why))

    for root in template_roots:
        for rel in all_folders:
            if rel == root or str(rel).startswith(str(root) + "/"):
                add(rel, "옵시디언 템플릿 폴더 설정")
    for rel in all_folders:
        text = nfc(str(rel)).lower()
        if any(word in text for word in SETTING_WORDS):
            add(rel, "세팅·템플릿·인덱스 성격 폴더")

    word_sources: list[dict] = []
    sermon_templates: list[dict] = []
    seen_notes: set[Path] = set()

    for rel, why in ordered:
        for note in notes_in(vault, rel):
            if note in seen_notes:
                continue
            seen_notes.add(note)
            found = inspect_note(note, vault)
            if found:
                found["why"] = why
                word_sources.append(found)
            template = inspect_template(note, vault)
            if template:
                template["found_in"] = why
                sermon_templates.append(template)

    # 그래도 없으면 볼트 전체에서 파일명 기준으로 한 번 더 훑는다.
    if not word_sources:
        for rel in all_folders:
            for note in notes_in(vault, rel):
                if note in seen_notes:
                    continue
                if not any(word in nfc(note.stem).lower() for word in WORD_NOTE_WORDS):
                    continue
                seen_notes.add(note)
                found = inspect_note(note, vault)
                if found:
                    found["why"] = "파일명에 분류 관련 단어"
                    word_sources.append(found)

    word_sources.sort(key=lambda r: -int(r["total"]))
    sermon_templates.sort(key=lambda r: (not r["has_classification_fields"], r["path"]))

    result: dict[str, object] = {
        "vault": str(vault),
        "obsidian_settings": settings,
        "searched_folders": [{"path": str(rel), "why": why} for rel, why in ordered[:limit * 3]],
        "word_sources": word_sources[:limit],
        "sermon_templates": sermon_templates[:limit],
    }
    if not word_sources:
        result["note_word"] = ("분류 정본 노트를 찾지 못했습니다. 목사님께 경로를 여쭤보시거나, "
                               "강의 표준 분류표(data/word_preset.a4p.json)를 쓸지 여쭤보세요.")
    if not sermon_templates:
        result["note_template"] = "설교 템플릿을 찾지 못했습니다. 파일명 규칙은 기존 설교 노트에서 추론하세요."
    if not settings["settings_present"]:
        result["note_settings"] = ".obsidian 폴더가 없습니다 — 옵시디언 볼트 경로가 맞는지 확인해 주세요."
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="분류 정본·설교 템플릿 탐색")
    parser.add_argument("vault")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args(argv[1:])

    vault = Path(args.vault).expanduser()
    if not vault.is_dir():
        print(json.dumps({"error": f"볼트 폴더를 찾을 수 없습니다: {vault}"}, ensure_ascii=False))
        return 1
    print(json.dumps(search(vault, args.limit), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
