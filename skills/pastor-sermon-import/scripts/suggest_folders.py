#!/usr/bin/env python3
"""목사님 볼트를 훑어 폴더·분류 노트 후보를 찾아 준다.

    python3 scripts/suggest_folders.py "{볼트 경로}" [--limit 8]

베이직 스킬은 목사님께 빈칸을 타이핑하게 하지 않는다. 볼트를 먼저 읽고
"이 폴더가 맞습니까?" 로 물어보기 위한 재료를 만든다.

읽기 전용이다. 성경 구절 노트가 수만 개인 볼트를 고려해 깊이와 개수를 제한한다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parent))

from find_word_template import search as search_word_template  # noqa: E402

MAX_DEPTH = 3
SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules", ".vault-sermon-import", "__pycache__"}

SERMON_WORDS = ["설교", "sermon", "말씀", "주일", "예배", "강해"]
FRAGMENT_WORDS = ["조각", "fragment", "메모", "note", "노트", "영감", "묵상조각"]
BIBLE_WORDS = ["성경", "bible", "구절", "verse"]
WORD_NOTE_WORDS = ["word", "분류", "속성", "taxonomy", "체계", "가이드라인", "인덱스"]

# 분류 노트 판별용 접두어 (parse_word_source.py 와 같은 계약)
AXIS_PREFIXES = {"world": "📩", "world_major": "📖", "outcome": "🏷", "route": "📝", "doctrine": "🔖"}


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def strip_number_prefix(name: str) -> str:
    return re.sub(r"^\d+[.\-]?\s*", "", name)


def score_folder(rel: Path, words: list[str]) -> int:
    """폴더 경로에 키워드가 얼마나 들어있는지."""
    text = nfc(str(rel)).lower()
    score = 0
    for word in words:
        if word.lower() in text:
            score += 3
    # 마지막 구성요소에 있으면 가중
    leaf = nfc(rel.name).lower()
    for word in words:
        if word.lower() in leaf:
            score += 2
    return score


def walk_folders(vault: Path) -> list[tuple[Path, int]]:
    """(상대경로, 그 폴더의 직속 .md 개수). 깊이 제한."""
    out: list[tuple[Path, int]] = []
    for path in vault.rglob("*"):
        if not path.is_dir():
            continue
        rel = path.relative_to(vault)
        if len(rel.parts) > MAX_DEPTH:
            continue
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts):
            continue
        try:
            md_count = sum(1 for p in path.iterdir() if p.is_file() and p.suffix == ".md")
        except OSError:
            continue
        out.append((rel, md_count))
    return out


def candidates(folders: list[tuple[Path, int]], words: list[str], limit: int,
               avoid: list[str] | None = None) -> list[dict]:
    """키워드 점수 순 후보.

    avoid 는 다른 용도의 폴더를 1순위에서 밀어낸다. "설교조각" 은 '설교' 를 품고
    있어 설교 폴더 1순위로 올라오는데, 스킬은 1순위를 권하므로 그대로 두면 메인
    노트를 조각 폴더에 넣자고 제안하게 된다.
    """
    scored = []
    for rel, md_count in folders:
        score = score_folder(rel, words)
        if score <= 0:
            continue
        if avoid:
            leaf = nfc(rel.name).lower()
            if any(word.lower() in leaf for word in avoid):
                score -= 4
        scored.append({"path": str(rel), "score": score, "notes": md_count,
                       "leaf": strip_number_prefix(rel.name)})
    scored.sort(key=lambda r: (-r["score"], -r["notes"], r["path"]))
    return scored[:limit]


def find_word_notes(vault: Path, folders: list[tuple[Path, int]], limit: int) -> list[dict]:
    """분류 정리 노트 후보. 파일명 키워드 → 그다음 접두어 밀도."""
    hits: list[dict] = []
    seen: set[Path] = set()

    def inspect(path: Path) -> dict | None:
        try:
            if path.stat().st_size > 200_000:
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
                "total": sum(matched.values())}

    # 1) 파일명에 분류 키워드가 있는 노트
    for rel, _ in folders:
        folder = vault / rel
        try:
            entries = [p for p in folder.iterdir() if p.is_file() and p.suffix == ".md"]
        except OSError:
            continue
        for path in entries:
            name = nfc(path.stem).lower()
            if any(word in name for word in WORD_NOTE_WORDS):
                if path in seen:
                    continue
                seen.add(path)
                info = inspect(path)
                if info:
                    info["why"] = "파일명에 분류 관련 단어"
                    hits.append(info)

    # 2) 못 찾으면 설정·인덱스 성격 폴더만 훑는다
    if not hits:
        for rel, _ in folders:
            if not any(w in nfc(str(rel)).lower() for w in ["setting", "설정", "meta", "index", "인덱스", "가이드"]):
                continue
            folder = vault / rel
            try:
                entries = [p for p in folder.iterdir() if p.is_file() and p.suffix == ".md"][:60]
            except OSError:
                continue
            for path in entries:
                if path in seen:
                    continue
                seen.add(path)
                info = inspect(path)
                if info:
                    info["why"] = "설정·인덱스 폴더에서 분류 접두어 발견"
                    hits.append(info)

    hits.sort(key=lambda r: -r["total"])
    return hits[:limit]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vault")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args(argv[1:])

    vault = Path(args.vault).expanduser()
    if not vault.is_dir():
        print(json.dumps({"error": f"볼트 폴더를 찾을 수 없습니다: {vault}"}, ensure_ascii=False))
        return 1

    folders = walk_folders(vault)
    # 분류 정본은 템플릿 폴더·900번대 세팅 폴더에 있을 확률이 가장 높다. 그쪽을
    # 먼저 보고(옵시디언 설정을 직접 읽는다), 없을 때만 폴더 이름으로 훑는다.
    template_scan = search_word_template(vault, args.limit)
    word_notes = list(template_scan.get("word_sources") or [])
    if not word_notes:
        word_notes = find_word_notes(vault, folders, args.limit)

    result = {
        "vault": str(vault),
        "folder_count": len(folders),
        "sermon_folders": candidates(folders, SERMON_WORDS, args.limit, avoid=FRAGMENT_WORDS),
        "fragment_folders": candidates(folders, FRAGMENT_WORDS, args.limit),
        "bible_folders": candidates(folders, BIBLE_WORDS, args.limit),
        "word_notes": word_notes,
        "sermon_templates": template_scan.get("sermon_templates") or [],
        "obsidian_settings": template_scan.get("obsidian_settings") or {},
    }
    if not result["sermon_folders"]:
        result["note_sermon"] = "설교 관련 폴더를 찾지 못했습니다. 새로 만들 폴더 이름을 여쭤보세요."
    if not result["fragment_folders"]:
        result["note_fragment"] = "조각 관련 폴더를 찾지 못했습니다. 새로 만들 폴더 이름을 여쭤보세요."
    if not result["word_notes"]:
        result["note_word"] = "분류 정리 노트를 찾지 못했습니다. 강의 표준 프리셋을 쓸지 여쭤보세요."
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
