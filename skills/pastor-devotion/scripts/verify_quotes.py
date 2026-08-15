#!/usr/bin/env python3
"""발췌·인용이 설교 원문에 실제로 있는지 검증한다.

    python3 verify_quotes.py --source <원문> --quotes <JSON>

- 원문: extract_text.py 출력 JSON(text 키) 또는 일반 텍스트/마크다운 파일
- quotes: {"quotes": ["...", ...]} 또는 문자열 배열 JSON
- 인용 안의 생략 부호(…, ...)로 나뉜 조각 각각이 공백 정규화 후
  원문에 부분일치해야 통과한다.

설교 원문 발췌("주일 말씀 중에서")와 성경 구절 인용 모두 이걸로 검사한다 —
목사님의 육성과 성경 본문은 한 글자도 지어내면 안 되는 영역이다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import sys


def normalize(text: str) -> str:
    text = re.sub(r"[\s ]+", "", text)
    # 따옴표·중점 등 서식 차이는 발췌의 진위와 무관하다.
    return re.sub(r"[\"'“”‘’·]", "", text)


def load_source(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and isinstance(data.get("text"), str):
                return data["text"]
        except ValueError:
            pass
    return raw


def load_quotes(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("quotes", [])
    return [str(q) for q in data if str(q).strip()]


def check(source_text: str, quotes: list[str]) -> dict:
    haystack = normalize(source_text)
    missing: list[dict] = []
    for quote in quotes:
        segments = [s for s in re.split(r"…|\.\.\.", quote) if normalize(s)]
        bad = [s.strip() for s in segments if normalize(s) not in haystack]
        if bad:
            missing.append({"quote": quote, "missing_segments": bad})
    return {"ok": not missing, "checked": len(quotes), "missing": missing}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="설교 원문 (extract_text JSON 또는 텍스트)")
    parser.add_argument("--quotes", required=True, help='발췌 JSON ({"quotes": [...]} 또는 배열)')
    args = parser.parse_args(argv[1:])
    result = check(load_source(Path(args.source).expanduser()),
                   load_quotes(Path(args.quotes).expanduser()))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
