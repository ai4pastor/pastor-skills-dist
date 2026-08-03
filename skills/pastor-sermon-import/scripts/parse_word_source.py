#!/usr/bin/env python3
"""목사님 볼트의 분류 정리 노트를 읽어 프리셋 스키마 JSON으로 만든다.

    python3 scripts/parse_word_source.py "{노트 경로}"
    python3 scripts/parse_word_source.py "{노트}" --prefix world=🌍 --prefix doctrine=✝
    python3 scripts/parse_word_source.py "{노트}" --generic
    python3 scripts/parse_word_source.py --explain

읽기 전용이다. 목사님 노트를 고치지 않는다.

파싱 계약 (기본 접두어)
    World 소분류   [[📩 201 청소년부 설교]]
    World 대분류   [[📖 200 설교 & 사역]]
    Outcome        [[🏷️ 설교]]
    Route          [[📝완료]]
    Doctrine       [[🔖칭의]]

축은 헤딩 이름이 아니라 **그 섹션에서 가장 많이 나온 접두어**로 판정한다.
강사 볼트는 `## ✝️ D — Doctrine` 이라고 적지만 목사님마다 제목이 다르므로,
제목에 의존하면 남의 볼트에서 곧바로 깨진다.

인식된 축이 하나뿐이어도 그것만 담아 반환하고 missing_axes 를 함께 준다.
비어 있는 축은 온보딩이 개별 질문으로 메운다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from note_utils import nfc, strip_vs  # noqa: E402

DEFAULT_PREFIXES = {
    "world": "📩 ",
    "world_major": "📖 ",
    "outcome": "🏷️ ",
    "route": "📝",
    "doctrine": "🔖",
}
AXES = ("world", "outcome", "route", "doctrine")


def prefix_pattern(prefix: str) -> str:
    """접두어 정규식. 이모지 뒤 U+FE0F 를 optional 로 둬서 🏷️ 와 🏷 를 모두 잡는다."""
    return "".join(re.escape(ch) + "️?" for ch in strip_vs(prefix))


def find_values(text: str, prefix: str) -> list[str]:
    pattern = re.compile(rf"\[\[({prefix_pattern(prefix)}[^\]|]+)\]\]")
    seen: dict[str, None] = {}
    for m in pattern.finditer(text):
        seen.setdefault(nfc(m.group(1)).strip(), None)
    return list(seen)


def split_sections(text: str, level: int) -> list[tuple[str, str]]:
    """(헤딩, 본문) 목록. level=2 는 `## `, level=3 은 `### `."""
    marker = "#" * level
    pattern = re.compile(rf"^{marker}\s+(?P<title>.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    out: list[tuple[str, str]] = []
    for idx, m in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        out.append((m.group("title").strip(), text[m.end():end]))
    return out


def classify_section(body: str, prefixes: dict[str, str]) -> str | None:
    """섹션이 어느 축인지 접두어 출현 수로 판정한다."""
    counts = {axis: len(find_values(body, prefixes[axis])) for axis in AXES}
    best = max(counts, key=lambda a: counts[a])
    return best if counts[best] > 0 else None


def parse_generic(text: str) -> dict:
    """접두어가 전혀 안 맞을 때: 헤딩별 항목만 모아 온보딩이 축을 묻게 한다."""
    groups = []
    for title, body in split_sections(text, 2) or [("(전체)", text)]:
        items: list[str] = []
        for line in body.splitlines():
            m = re.match(r"^\s*[-*]\s+(?P<value>.+?)\s*$", line)
            if not m:
                continue
            value = m.group("value").strip()
            link = re.match(r"^\[\[([^\]|]+)(?:\|[^\]]*)?\]\]$", value)
            items.append(nfc(link.group(1) if link else value).strip())
        if items:
            groups.append({"section": title, "values": items})
    return {"mode": "generic", "groups": groups,
            "note": "접두어 매칭이 0건입니다. 각 묶음이 어느 축(World/Outcome/Route/Doctrine)인지 확인이 필요합니다."}


def parse(text: str, prefixes: dict[str, str], doctrine_heading: str | None = None) -> dict:
    text = nfc(text)
    axes: dict[str, dict] = {}
    sections = split_sections(text, 2)

    doctrine_body = None
    if doctrine_heading:
        for title, body in sections:
            if doctrine_heading in title:
                doctrine_body = body
                break

    for title, body in sections:
        axis = classify_section(body, prefixes)
        if not axis or axis in axes:
            continue
        entry: dict = {"prefix": prefixes[axis], "heading": title}
        subsections = split_sections(body, 3)
        if axis == "world":
            entry["major_prefix"] = prefixes["world_major"]
            groups = []
            for sub_title, sub_body in subsections:
                values = find_values(sub_body, prefixes["world"])
                if values:
                    major = find_values(sub_title, prefixes["world_major"])
                    groups.append({"major": major[0] if major else sub_title, "values": values})
            entry["groups"] = groups or [{"major": title, "values": find_values(body, prefixes["world"])}]
            entry["values"] = [v for g in entry["groups"] for v in g["values"]]
            entry["major_values"] = find_values(body, prefixes["world_major"])
        elif axis == "doctrine":
            source = doctrine_body if doctrine_body is not None else body
            groups = []
            for sub_title, sub_body in split_sections(source, 3):
                values = find_values(sub_body, prefixes["doctrine"])
                if values:
                    groups.append({"section": sub_title, "values": values})
            entry["groups"] = groups
            entry["values"] = [v for g in groups for v in g["values"]] or find_values(source, prefixes["doctrine"])
        else:
            entry["values"] = find_values(body, prefixes[axis])
            if axis == "route":
                entry["scalar"] = True
        axes[axis] = entry

    missing = [a for a in AXES if a not in axes or not axes[a].get("values")]
    return {
        "mode": "prefix",
        "axes": axes,
        "missing_axes": missing,
        "counts": {a: len(axes.get(a, {}).get("values", [])) for a in AXES},
    }


SERMON_WORDS = ("설교", "말씀", "주일", "예배", "기도회", "강해", "sermon", "목양", "사역")
FRAGMENT_WORDS = ("조각", "영감", "메모", "묵상")
DONE_WORDS = ("완료", "완성", "마침", "종료", "done")


def has_word(value: str, words: tuple[str, ...]) -> bool:
    low = value.lower()
    return any(word.lower() in low for word in words)


def sermon_subset(parsed: dict) -> dict:
    """설교 임포트에 실제로 쓰이는 값만 골라낸다.

    설교 한 편을 넣는 데 목사님 분류 체계 전부가 필요하지는 않다. World 는 설교·사역
    성격의 값, Outcome 은 설교 값 하나, Route 는 '완료' 하나면 된다. Doctrine 만은
    좁히지 않는다 — 신학 주제는 설교마다 달라 목사님 목록 전체가 후보다.
    """
    axes = parsed.get("axes", {})
    world = axes.get("world", {}) or {}
    world_values = list(world.get("values") or [])

    picked: list[str] = []
    why: list[str] = []
    for group in world.get("groups") or []:
        major = str(group.get("major") or "")
        if has_word(major, SERMON_WORDS):
            for value in group.get("values") or []:
                if value not in picked:
                    picked.append(value)
            why.append(f"'{major}' 묶음 전체")
    for value in world_values:
        if has_word(value, SERMON_WORDS) and value not in picked:
            picked.append(value)
            why.append(f"'{value}' — 이름에 설교 관련 단어")

    fragment_candidate = next((v for v in world_values if has_word(v, FRAGMENT_WORDS)), "")
    sermon_world = [v for v in picked if v != fragment_candidate]

    outcome_values = list((axes.get("outcome", {}) or {}).get("values") or [])
    outcome_hits = [v for v in outcome_values if has_word(v, ("설교",))]

    route_values = list((axes.get("route", {}) or {}).get("values") or [])
    route_hits = [v for v in route_values if has_word(v, DONE_WORDS)]

    doctrine_values = list((axes.get("doctrine", {}) or {}).get("values") or [])

    asks: list[str] = []
    subset: dict = {
        "world": {
            "values": sermon_world,
            "why": why,
            "fragment_candidate": fragment_candidate,
            "all_count": len(world_values),
        },
        "outcome": {
            "values": outcome_values,
            "recommended": outcome_hits[0] if outcome_hits else "",
        },
        "route": {
            "values": route_values,
            "recommended": route_hits[0] if route_hits else "",
            "scalar": True,
        },
        "doctrine": {
            "count": len(doctrine_values),
            "note": "신학 주제는 설교마다 달라 좁히지 않습니다 — 목사님 목록 전체를 후보로 둡니다.",
        },
    }

    if not sermon_world:
        asks.append(f"설교에 쓸 분류(World) 값을 찾지 못했습니다. 전체 {len(world_values)}개 중에서 "
                    "설교에 붙이실 값을 골라 주세요.")
    if not fragment_candidate:
        asks.append("설교 조각에 붙일 값(조각·영감 성격)을 찾지 못했습니다. 하나 골라 주시거나 "
                    "비워 두셔도 됩니다.")
    if subset["route"]["recommended"]:
        asks.append(f"설교는 이미 설교하신 완성 원고라, 진행 단계는 '{subset['route']['recommended']}' 로 "
                    "넣겠습니다. 괜찮으신가요?")
    elif route_values:
        asks.append(f"진행 단계(Route) 중 어느 값을 쓸까요? ({' · '.join(route_values[:6])})")
    if subset["outcome"]["recommended"]:
        asks.append(f"활용 목적(Outcome)은 '{subset['outcome']['recommended']}' 로 넣겠습니다. 맞습니까?")
    subset["ask"] = asks
    return subset


EXPLAIN = """스킬이 분류 노트에서 찾는 모양

    World 소분류   [[📩 201 청소년부 설교]]     (접두어 "📩 ")
    World 대분류   [[📖 200 설교 & 사역]]       (접두어 "📖 ")
    Outcome        [[🏷️ 설교]]                  (접두어 "🏷️ ")
    Route          [[📝완료]]                   (접두어 "📝")
    Doctrine       [[🔖칭의]]                   (접두어 "🔖")

- 축은 헤딩 제목이 아니라 그 묶음에서 가장 많이 나온 접두어로 판정합니다.
- `## 제목` 아래 `### 소제목` 이 있으면 묶음으로 함께 기록합니다.
- 접두어가 다르면:  --prefix world=🌍 --prefix doctrine=✝
- 접두어를 아예 쓰지 않으시면:  --generic
"""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("note", nargs="?", help="분류 정리 노트 경로")
    parser.add_argument("--prefix", action="append", default=[], metavar="AXIS=값",
                        help="접두어 오버라이드 (world/world_major/outcome/route/doctrine)")
    parser.add_argument("--doctrine-heading", default=None,
                        help="Doctrine 섹션 제목의 일부 (기본: 접두어로 자동 판정)")
    parser.add_argument("--generic", action="store_true", help="접두어 없이 헤딩·목록만 수집")
    parser.add_argument("--sermon-only", action="store_true",
                        help="설교 임포트에 쓰이는 부분집합(설교 World·Outcome·Route 추천)을 함께 계산")
    parser.add_argument("--explain", action="store_true", help="파싱 계약을 출력")
    args = parser.parse_args(argv[1:])

    if args.explain:
        print(EXPLAIN)
        return 0
    if not args.note:
        parser.error("노트 경로가 필요합니다 (계약을 보려면 --explain)")

    prefixes = dict(DEFAULT_PREFIXES)
    for item in args.prefix:
        if "=" not in item:
            parser.error(f"--prefix 형식은 AXIS=값 입니다: {item}")
        key, value = item.split("=", 1)
        if key not in prefixes:
            parser.error(f"알 수 없는 축: {key} (가능: {', '.join(prefixes)})")
        prefixes[key] = value

    path = Path(args.note).expanduser()
    if not path.is_file():
        print(json.dumps({"error": f"노트를 찾을 수 없습니다: {path}"}, ensure_ascii=False))
        return 1
    text = path.read_text(encoding="utf-8", errors="ignore")

    result = parse_generic(text) if args.generic else parse(text, prefixes, args.doctrine_heading)
    if not args.generic and len(result["missing_axes"]) == len(AXES):
        result = parse_generic(text)
        result["note"] = "접두어 매칭이 0건이라 일반 모드로 다시 읽었습니다. " + result.get("note", "")
    if args.sermon_only:
        if result.get("mode") == "generic":
            result["sermon_subset"] = {"ask": ["묶음이 어느 축인지 먼저 확인해야 설교용 값을 고를 수 있습니다."]}
        else:
            result["sermon_subset"] = sermon_subset(result)
    result["source_note"] = path.name
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
