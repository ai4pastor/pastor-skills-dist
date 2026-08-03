#!/usr/bin/env python3
"""설교 파일 이름들을 보고 파일명 규칙을 추론한다.

    python3 scripts/guess_naming.py "{설교 폴더}" [--limit 200]

베이직 스킬은 "파일명 규칙이 있으세요?" 를 묻지 않는다. 목사님 파일을 먼저 읽고
"이렇게 읽었습니다, 맞습니까?" 로 확인만 받는다.

읽기 전용이다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import sys
import unicodedata
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_text import SUPPORTED  # noqa: E402

DATE_RES = [
    ("YYMMDD", re.compile(r"^(?P<date>\d{6})(?=[\s_\-])")),
    ("YYYYMMDD", re.compile(r"^(?P<date>\d{8})(?=[\s_\-])")),
    ("YYYY-MM-DD", re.compile(r"^(?P<date>\d{4}[-.]\d{2}[-.]\d{2})(?=[\s_\-])")),
]
# 날짜 뒤에 오는 짧은 토큰 = 설교 구분 표시 후보
MARKER_RE = re.compile(r"^[\s_\-]+(?P<marker>[가-힣A-Za-z]{1,4})(?=[\s_\-])")

# 설교 구분 후보. 목회 현장은 청소년부·어린이부보다 대예배·수요·새벽 쪽이 훨씬 많다.
# 앞의 것이 더 구체적인 표기이므로 순서대로 먼저 맞춰 본다.
KIND_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("주일대예배", ("주일대예배", "대예배", "주일예배", "주일오전", "1부예배", "장년부", "전교인", "주일설교", "주일")),
    ("주일오후예배", ("주일오후", "오후예배", "저녁예배", "2부예배", "찬양예배")),
    ("수요기도회", ("수요기도회", "수요예배", "수요저녁", "수요")),
    ("새벽기도회", ("새벽기도회", "새벽기도", "새벽예배", "새벽")),
    ("금요기도회", ("금요기도회", "금요철야", "철야", "금요")),
    ("특별집회", ("부흥회", "사경회", "특별집회", "집회", "수련회")),
    ("청년부", ("청년부", "대학부", "청년")),
    ("청소년부", ("청소년부", "중고등부", "중등부", "고등부", "학생부", "청소년")),
    ("어린이부", ("어린이부", "유년부", "유치부", "주일학교", "아동부", "어린이")),
    ("심방·경조사", ("심방", "장례", "추도", "결혼", "임직", "돌잔치")),
    ("성경공부", ("성경공부", "제자훈련", "교리공부", "세미나", "강의")),
]
# 옛 버전과 같은 한 글자 표기도 계속 알아본다.
SHORT_MARKER_KINDS = {"대": "주일대예배", "청": "청소년부", "어": "어린이부", "새": "새벽기도회", "수": "수요기도회"}


def kind_for(text: str) -> str:
    """폴더명·파일명 조각에서 설교 구분을 알아낸다. 못 찾으면 빈 문자열."""
    low = nfc(text).lower().replace(" ", "")
    for kind, words in KIND_PATTERNS:
        if any(word.lower().replace(" ", "") in low for word in words):
            return kind
    return ""


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def collect(folder: Path, limit: int) -> list[Path]:
    if folder.is_file():
        return [folder]
    out = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED:
            continue
        if path.name.startswith(("~$", "._", ".")):
            continue
        out.append(path)
        if len(out) >= limit:
            break
    return out


def scan(paths: list[Path]) -> dict:
    """1차 스캔: 날짜·표시·설교 구분 후보 집계."""
    date_hits: dict[str, int] = {}
    marker_hits: dict[str, int] = {}
    folder_kinds: dict[str, str] = {}     # 폴더 이름 → 설교 구분
    stem_kind_hits: dict[str, int] = {}   # 파일명 어디에든 나온 구분
    rows: list[tuple[Path, str, str]] = []   # (path, date_kind, rest)
    no_date = 0

    for path in paths:
        stem = nfc(path.stem)
        if "%" in stem:
            stem = urllib.parse.unquote(stem)

        matched_date = ""
        rest = stem
        for kind, pattern in DATE_RES:
            m = pattern.match(stem)
            if m:
                matched_date = kind
                date_hits[kind] = date_hits.get(kind, 0) + 1
                rest = stem[m.end():]
                break
        if not matched_date:
            no_date += 1

        mm = MARKER_RE.match(rest) if matched_date else None
        if mm:
            token = mm.group("marker")
            marker_hits[token] = marker_hits.get(token, 0) + 1

        for parent in list(path.parents)[:3]:
            name = re.sub(r"^\d+[.\-]?\s*", "", nfc(parent.name))
            hit = kind_for(name)
            if hit:
                folder_kinds[name] = hit
                break

        # 파일명 전체에서도 구분을 찾는다. 이건 집계·질문용이고 제목 파싱은 건드리지
        # 않는다 — 제목 첫 단어를 표시로 오독하는 위험은 위의 위치 기반 규칙에만 있다.
        stem_hit = kind_for(stem)
        if stem_hit:
            stem_kind_hits[stem_hit] = stem_kind_hits.get(stem_hit, 0) + 1

        rows.append((path, matched_date, rest))
    return {"date_hits": date_hits, "marker_hits": marker_hits, "folder_kinds": folder_kinds,
            "stem_kind_hits": stem_kind_hits, "no_date": no_date, "rows": rows}


def marker_kind(token: str) -> str:
    return SHORT_MARKER_KINDS.get(token, "") or kind_for(token)


def decide_markers(marker_hits: dict[str, int], folder_kinds: dict[str, str]) -> list[str]:
    """설교 구분 표시를 확정한다.

    글자 수에 따라 기준이 다르다. 설교 파일명에서 한 글자 토큰(대·청·어·새)은 표기
    관례이고 제목이 한 글자로 시작하는 일은 드물다. 반면 두 글자 이상은 "새벽에
    부르시는" 처럼 제목 첫 단어일 수 있어 반복 근거를 요구한다.
    폴더에서 이미 같은 구분이 확인된 표기는 한 번만 나와도 인정한다.
    """
    folder_kind_values = set(folder_kinds.values())
    decided = []
    for token, count in marker_hits.items():
        kind = marker_kind(token)
        if len(token) == 1:
            decided.append(token)
        elif kind and kind in folder_kind_values:
            decided.append(token)
        elif len(token) >= 2 and count >= 2:
            decided.append(token)
    return sorted(decided, key=lambda t: (-marker_hits[t], t))


def analyze(paths: list[Path]) -> dict:
    scanned = scan(paths)
    date_hits = scanned["date_hits"]
    marker_hits = scanned["marker_hits"]
    folder_kinds = scanned["folder_kinds"]
    stem_kind_hits = scanned["stem_kind_hits"]
    no_date = scanned["no_date"]
    rows = scanned["rows"]
    total = len(paths)
    markers = decide_markers(marker_hits, folder_kinds)

    # 확정된 구분 표시를 기준으로 다시 읽어 목사님께 보여줄 예시를 만든다.
    samples: list[dict] = []
    marker_re = None
    if markers:
        alt = "|".join(re.escape(m) for m in sorted(markers, key=len, reverse=True))
        marker_re = re.compile(rf"^[\s_\-]*(?P<marker>{alt})(?=[\s_\-]|$)[\s_\-]*")
    for path, date_kind, rest in rows[:6]:
        marker = ""
        title = rest.lstrip(" _-")
        if marker_re:
            mm = marker_re.match(rest)
            if mm:
                marker = mm.group("marker")
                title = rest[mm.end():].lstrip(" _-")
        samples.append({"file": path.name, "date_kind": date_kind or "-",
                        "marker": marker or "-", "title": title or nfc(path.stem)})

    date_kind = max(date_hits, key=lambda k: date_hits[k]) if date_hits else ""
    date_ratio = (date_hits.get(date_kind, 0) / total) if total else 0.0

    if date_kind and markers:
        main_pattern = "{yymmdd}_{target}_{title}_{main_passage}.md"
    elif date_kind:
        main_pattern = "{yymmdd}_{title}_{main_passage}.md"
    else:
        main_pattern = "{title}_{main_passage}.md"

    # 설교 구분 후보 — 폴더에서 확인된 것을 먼저, 그다음 파일명에서 나온 것.
    marker_to_kind = {token: marker_kind(token) for token in markers if marker_kind(token)}
    detected: list[str] = []
    for kind in list(folder_kinds.values()) + list(marker_to_kind.values()) + \
            sorted(stem_kind_hits, key=lambda k: -stem_kind_hits[k]):
        if kind not in detected:
            detected.append(kind)

    return {
        "files_scanned": total,
        "date_kind": date_kind or None,
        "date_hits": date_hits,
        "date_ratio": round(date_ratio, 2),
        "files_without_date": no_date,
        "target_markers": markers,
        "marker_hits": {m: marker_hits[m] for m in markers},
        "rejected_markers": {m: n for m, n in marker_hits.items() if m not in markers},
        "reject_reason": "두 글자 이상 토큰은 제목 첫 단어일 수 있어 2회 이상 반복되거나 폴더 이름의 구분과 "
                         "같을 때만 인정합니다.",
        "folder_to_kind": folder_kinds,
        "sermon_kinds_detected": detected,
        "sermon_kind_hits": {"폴더": folder_kinds, "파일명 표시": marker_to_kind,
                             "파일명 어디든": stem_kind_hits},
        "pattern_options": {
            "구분을 파일명에": "{yymmdd}_{kind}_{title}_{main_passage}.md",
            "짧은 표시를 파일명에": "{yymmdd}_{target}_{title}_{main_passage}.md",
            "구분 없이": "{yymmdd}_{title}_{main_passage}.md",
        },
        "suggested": {
            "naming.main_note_pattern": main_pattern,
            "naming.fragment_note_pattern": "{title}.md",
            "naming.target_markers": markers,
            # 폴더 이름 → 정식 구분명. extract_meta 가 이 값을 그대로 구분으로 읽는다.
            "naming.folder_to_target": folder_kinds,
            "naming.date_from_filename": bool(date_kind),
            "naming.target_from_folder": bool(folder_kinds),
            "sermon_kinds.values": detected,
            "sermon_kinds.marker_to_kind": marker_to_kind,
            "sermon_kinds.enabled": bool(detected),
        },
        "samples": samples,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args(argv[1:])

    folder = Path(args.folder).expanduser()
    if not folder.exists():
        print(json.dumps({"error": f"경로를 찾을 수 없습니다: {folder}"}, ensure_ascii=False))
        return 1
    paths = collect(folder, args.limit)
    if not paths:
        types = " / ".join(sorted(SUPPORTED))
        print(json.dumps({"error": f"설교 파일({types})을 찾지 못했습니다: {folder}",
                          "files_scanned": 0}, ensure_ascii=False, indent=2))
        return 1

    result = analyze(paths)
    result["folder"] = str(folder)
    parts: list[str] = []
    if result["target_markers"]:
        hits = ", ".join(f"{m}({result['marker_hits'][m]}회)" for m in result["target_markers"])
        parts.append(f"파일명의 구분 표시로 {hits} 를 찾았습니다.")
    else:
        parts.append("파일명에서 구분 표시를 찾지 못했습니다. 파일명 전체를 제목으로 읽습니다 — "
                     "이 편이 제목 첫 단어를 표시로 잘못 읽는 것보다 안전합니다.")
    if result["sermon_kinds_detected"]:
        parts.append("설교 구분으로 " + " · ".join(result["sermon_kinds_detected"]) + " 을 찾았습니다.")
    else:
        parts.append("설교 구분(대예배·수요·새벽 등)은 찾지 못했습니다 — 목사님께 직접 여쭤보세요.")
    result["explain"] = " ".join(parts)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
