#!/usr/bin/env python3
"""Note draft gate for pastor-sermon-lab.

result JSON의 body를 노트로 만들기 전에 결정론적으로 검사한다:
- 등급 커버리지: 사실 섹션에서 연대(BC/AD/세기/연도)·수치(%)·직접 인용을 담은
  글머리/문장에 등급 이모지가 없으면 실패
- 관찰 구역: 제목에 "(관찰)"이 붙은 섹션은 성경 본문 내부 서술 전용 —
  사실 신호(연대·수치·곡선 따옴표)가 나오면 등급 유무와 무관하게 실패
- 표기 변형: 5등급 이모지 외 표기([CONFIRMED] 등) 금지 (forbidden_phrases와 함께)
- 금지 표현: data/forbidden_phrases.json 정규식 검출
- 성경 장 범위: 본문에서 추출한 장절이 data/bible_bounds.json의 장 수를 넘으면 실패
- '## 검증 요약' 직접 작성 금지 (build_note가 실측으로 생성)

exit 0 = ok, exit 1 = blocked.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import sys

from config_loader import default_config
from extract_bible_refs import extract as extract_refs

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRADE_EMOJIS = ("✅", "🟡", "⚠️", "❓", "🚫")

# 등급이 필요한 사실 신호: 연대·수치·직접 인용
FACT_SIGNALS = re.compile(
    r"(BC|AD|주전|주후)\s*\d|\d+\s*세기|\d{3,4}\s*년|\d+(\.\d+)?\s*%|[“”]"
)
HEADING_RE = re.compile(r"^##\s+(?P<title>.+)$")
EXEMPT_HEADINGS = ("(해석)", "검증 요약", "확인 필요한 성경구절", "주의")

# 관찰 구역: 성경 본문에서 직접 확인 가능한 서술만 허용 (grade_rules.md "본문 내용 서술은 등급 비대상").
# 면제가 아니라 금지 — 외부 세계 사실(연대·통계·인용)은 등급을 붙여 사실 섹션에 써야 한다.
OBSERVATION_MARKER = "(관찰)"


def load_forbidden() -> list[dict[str, str]]:
    return json.loads((DATA_DIR / "forbidden_phrases.json").read_text(encoding="utf-8"))["patterns"]


def load_bounds() -> dict[str, int]:
    return json.loads((DATA_DIR / "bible_bounds.json").read_text(encoding="utf-8"))["chapters"]


def split_sections(body: str) -> list[tuple[str, list[str]]]:
    """(섹션 제목, 줄 목록) 목록. 첫 헤딩 전 내용은 제목 ''."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in body.splitlines():
        m = HEADING_RE.match(line)
        if m:
            sections.append((m.group("title").strip(), []))
        else:
            sections[-1][1].append(line)
    return sections


def is_exempt(title: str) -> bool:
    return any(marker in title for marker in EXEMPT_HEADINGS)


def is_observation(title: str) -> bool:
    return OBSERVATION_MARKER in title


def check_coverage(body: str) -> list[str]:
    issues: list[str] = []
    for title, lines in split_sections(body):
        if is_exempt(title):
            continue
        observation = is_observation(title)
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not FACT_SIGNALS.search(stripped):
                continue
            if observation:
                issues.append(
                    f"관찰 섹션에 외부 사실 신호 (섹션 '{title}'): {stripped[:60]} — "
                    "등급을 붙여 사실 섹션(역사·문화 배경 등)으로 옮기거나 성경 본문 관찰로 재서술하십시오"
                )
            elif not any(e in stripped for e in GRADE_EMOJIS):
                issues.append(f"등급 없는 사실 신호 (섹션 '{title or '서두'}'): {stripped[:60]}")
    return issues


def check_forbidden(body: str) -> list[str]:
    issues = []
    for item in load_forbidden():
        for m in re.finditer(item["pattern"], body):
            issues.append(f"금지 표현 '{m.group(0)}' — {item['reason']}")
    return issues


def check_bible_bounds(body: str, config: dict) -> list[str]:
    bounds = load_bounds()
    # normalized는 "{책약어}{장}_{절}" 형식 — 긴 약어 우선 매칭 (예: '요일' before '요')
    books = sorted(bounds, key=len, reverse=True)
    norm_re = re.compile(rf"^(?P<book>{'|'.join(map(re.escape, books))})(?P<chapter>\d+)_")
    issues = []
    seen: set[str] = set()
    for ref in extract_refs(body, config):
        normalized = str(ref.get("normalized", ""))
        m = norm_re.match(normalized)
        if not m:
            continue
        book, chapter = m.group("book"), int(m.group("chapter"))
        key = f"{book}{chapter}"
        if key in seen:
            continue
        seen.add(key)
        limit = bounds[book]
        if chapter > limit:
            issues.append(f"성경 장 범위 초과: {ref.get('raw')} — {book}은 {limit}장까지")
    return issues


def verify_body(body: str, config: dict, mode: str = "research") -> list[str]:
    issues: list[str] = []
    if "## 검증 요약" in body:
        issues.append("'## 검증 요약' 직접 작성 금지 — build_note.py가 생성한다")
    if mode != "diagnose":
        # 진단 본문은 설교에 대한 평가(해석)라 등급 커버리지 대상이 아니다
        issues.extend(check_coverage(body))
    issues.extend(check_forbidden(body))
    issues.extend(check_bible_bounds(body, config))
    return issues


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True, help="result JSON 경로 (body 필드 검사)")
    parser.add_argument("--mode", default="research", choices=["research", "diagnose", "enrich"])
    args = parser.parse_args(argv[1:])

    config = default_config()
    result = json.loads(Path(args.result).expanduser().read_text(encoding="utf-8"))
    body = str(result.get("body", ""))
    issues = verify_body(body, config, args.mode)
    out = {"status": "ok" if not issues else "blocked", "issues": issues}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
