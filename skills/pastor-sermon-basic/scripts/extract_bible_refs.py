#!/usr/bin/env python3
"""Korean Bible reference extraction prototype with config-aware links."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from config_loader import default_config, load_config

# 표준 성경 약어 66권 (수강생 공통 성경구절 노트 파일명과 일치)
VALID_BOOKS = {
    "창", "출", "레", "민", "신", "수", "삿", "룻",
    "삼상", "삼하", "왕상", "왕하", "대상", "대하",
    "스", "느", "에", "욥", "시", "잠", "전", "아",
    "사", "렘", "애", "겔", "단",
    "호", "욜", "암", "옵", "욘", "미", "나", "합", "습", "학", "슥", "말",
    "마", "막", "눅", "요", "행", "롬",
    "고전", "고후", "갈", "엡", "빌", "골",
    "살전", "살후", "딤전", "딤후", "딛", "몬",
    "히", "약", "벧전", "벧후",
    "요일", "요이", "요삼", "유", "계",
}

# 풀어쓴 책 이름 → 표준 약어 (66권 전체 + 자주 쓰는 변형)
EXPANDED = {
    "창세기": "창", "출애굽기": "출", "레위기": "레", "민수기": "민",
    "신명기": "신", "여호수아": "수", "사사기": "삿", "룻기": "룻",
    "사무엘상": "삼상", "사무엘하": "삼하",
    "열왕기상": "왕상", "열왕기하": "왕하",
    "역대상": "대상", "역대하": "대하",
    "에스라": "스", "느헤미야": "느", "에스더": "에",
    "욥기": "욥", "시편": "시", "잠언": "잠", "전도서": "전", "아가": "아",
    "이사야": "사", "이사야서": "사",
    "예레미야": "렘", "예레미야서": "렘",
    "예레미야애가": "애", "애가": "애",
    "에스겔": "겔", "에스겔서": "겔",
    "다니엘": "단", "다니엘서": "단",
    "호세아": "호", "요엘": "욜", "아모스": "암", "오바댜": "옵",
    "요나": "욘", "미가": "미", "나훔": "나", "하박국": "합",
    "스바냐": "습", "학개": "학", "스가랴": "슥", "말라기": "말",
    "마태복음": "마", "마가복음": "막", "누가복음": "눅", "요한복음": "요",
    "사도행전": "행", "로마서": "롬",
    "고린도전서": "고전", "고린도후서": "고후",
    "갈라디아서": "갈", "에베소서": "엡", "빌립보서": "빌", "골로새서": "골",
    "데살로니가전서": "살전", "데살로니가후서": "살후",
    "디모데전서": "딤전", "디모데후서": "딤후",
    "디도서": "딛", "빌레몬서": "몬",
    "히브리서": "히", "야고보서": "약",
    "베드로전서": "벧전", "베드로후서": "벧후",
    "요한일서": "요일", "요한이서": "요이", "요한삼서": "요삼",
    "유다서": "유", "요한계시록": "계", "계시록": "계",
}

# 긴 이름 우선 매칭 ("고전"이 "고"보다, "로마서"가 "롬"보다 먼저)
BOOK_PATTERN = "|".join(
    map(re.escape, sorted(set(EXPANDED) | VALID_BOOKS, key=len, reverse=True))
)
# 지원 표기: 요 3:16 / 요3:16 / 요한복음 3장 16절 / 요 3장 16-18절 / 시편 23편 1절 / 시 33:6, 9
REF_RE = re.compile(rf"(?P<book>{BOOK_PATTERN})\s*(?P<chapter>\d+)\s*[:장편]\s*(?P<verses>\d+(?:\s*-\s*\d+)?(?:\s*,\s*\d+(?:\s*-\s*\d+)?)*)\s*절?")
CHAPTER_ONLY_RE = re.compile(rf"(?P<book>{BOOK_PATTERN})\s*(?P<chapter>\d+)\s*(?:장|편)(?!\s*[:장]?\s*\d)")


def make_link(style: str, book: str, chapter: str, verse: str) -> dict[str, str]:
    normalized = f"{book}{chapter}_{verse}"
    return {
        "normalized": normalized,
        "link": style.format(book=book, chapter=chapter, verse=verse, normalized=normalized),
    }


def normalize(book: str, chapter: str, verses: str, config: dict[str, Any]) -> list[dict[str, str]]:
    short = EXPANDED.get(book, book)
    aliases = config.get("bible", {}).get("book_aliases", {})
    short = aliases.get(book, aliases.get(short, short))
    style = config.get("bible", {}).get("link_style", "[[{normalized}]]")
    range_policy = config.get("bible", {}).get("range_policy", "expand_each_verse")
    max_range = int(config.get("bible", {}).get("max_range_expand", 50))
    out: list[dict[str, str]] = []
    for part in re.split(r"\s*,\s*", verses):
        if "-" in part:
            start, end = [int(x) for x in part.split("-", 1)]
            if end < start:
                out.append({"normalized": "", "link": "", "status": "ambiguous", "note": "역방향 범위"})
            elif range_policy == "keep_range":
                normalized = f"{short}{chapter}_{start}-{end}"
                out.append({"normalized": normalized, "link": style.format(book=short, chapter=chapter, verse=f"{start}-{end}", normalized=normalized)})
            elif end - start > max_range:
                out.append({"normalized": "", "link": "", "status": "ambiguous", "note": f"범위가 너무 김: {start}-{end}"})
            else:
                for verse in range(start, end + 1):
                    out.append(make_link(style, short, chapter, str(verse)))
        else:
            out.append(make_link(style, short, chapter, str(int(part))))
    return out


def extract(text: str, config: dict[str, Any]) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    seen = set()
    matched_spans = []
    for m in REF_RE.finditer(text):
        raw = m.group(0)
        matched_spans.append(m.span())
        links = normalize(m.group("book"), m.group("chapter"), m.group("verses"), config)
        for item in links:
            key = item.get("normalized") or f"ambiguous:{raw}:{item.get('note','')}"
            if key in seen:
                continue
            seen.add(key)
            refs.append({"raw": raw, **item, "status": item.get("status", "ok")})

    for m in CHAPTER_ONLY_RE.finditer(text):
        if any(start <= m.start() < end for start, end in matched_spans):
            continue
        raw = m.group(0)
        key = f"ambiguous:{raw}"
        if key in seen:
            continue
        seen.add(key)
        refs.append({"raw": raw, "normalized": "", "link": "", "status": "ambiguous", "note": "절 번호 없음"})
    return refs


def main(argv: list[str]) -> int:
    config = default_config()
    if len(argv) >= 2:
        config = load_config(Path(argv[1]))
    text = sys.stdin.read()
    print(json.dumps({"bible_refs": extract(text, config)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
