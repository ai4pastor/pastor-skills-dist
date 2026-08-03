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

SUPPORTED = {".docx", ".md", ".txt"}
DATE_RES = [
    ("YYMMDD", re.compile(r"^(?P<date>\d{6})(?=[\s_\-])")),
    ("YYYYMMDD", re.compile(r"^(?P<date>\d{8})(?=[\s_\-])")),
    ("YYYY-MM-DD", re.compile(r"^(?P<date>\d{4}[-.]\d{2}[-.]\d{2})(?=[\s_\-])")),
]
# 날짜 뒤에 오는 짧은 토큰 = 대상 표시 후보
MARKER_RE = re.compile(r"^[\s_\-]+(?P<marker>[가-힣A-Za-z]{1,4})(?=[\s_\-])")
FOLDER_WORDS = {
    "청소년부": "청", "청소년": "청", "중고등부": "청", "학생부": "청",
    "어린이부": "어", "유년부": "어", "유치부": "어", "주일학교": "어",
    "대예배": "대", "주일예배": "대", "장년부": "대", "전교인": "대",
}


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


def scan(paths: list[Path]) -> tuple[dict[str, int], dict[str, int], dict[str, str], int, list[tuple[Path, str, str]]]:
    """1차 스캔: 날짜·대상 후보 집계. (date_hits, marker_hits, folder_hits, no_date, rows)"""
    date_hits: dict[str, int] = {}
    marker_hits: dict[str, int] = {}
    folder_hits: dict[str, str] = {}
    rows: list[tuple[Path, str, str]] = []   # (path, date_kind, rest)
    no_date = 0

    for path in paths:
        stem = nfc(path.stem)
        if "%" in stem:
            stem = urllib.parse.unquote(stem)

        matched_kind = ""
        rest = stem
        for kind, pattern in DATE_RES:
            m = pattern.match(stem)
            if m:
                matched_kind = kind
                date_hits[kind] = date_hits.get(kind, 0) + 1
                rest = stem[m.end():]
                break
        if not matched_kind:
            no_date += 1

        mm = MARKER_RE.match(rest) if matched_kind else None
        if mm:
            token = mm.group("marker")
            marker_hits[token] = marker_hits.get(token, 0) + 1

        for parent in list(path.parents)[:3]:
            name = re.sub(r"^\d+[.\-]?\s*", "", nfc(parent.name))
            if name in FOLDER_WORDS:
                folder_hits[name] = FOLDER_WORDS[name]
                break

        rows.append((path, matched_kind, rest))
    return date_hits, marker_hits, folder_hits, no_date, rows


def decide_markers(marker_hits: dict[str, int], folder_hits: dict[str, str]) -> list[str]:
    """대상 표시를 확정한다.

    글자 수에 따라 기준이 다르다. 설교 파일명에서 한 글자 토큰(청·어·대)은 대상
    표기 관례이고 제목이 한 글자로 시작하는 일은 드물다. 반면 두 글자 이상은
    "믿음의 길" 처럼 제목 첫 단어일 수 있어 반복 근거를 요구한다.
    폴더명에서 이미 확인된 표기는 한 번만 나와도 인정한다.
    """
    from_folders = set(folder_hits.values())
    decided = []
    for token, count in marker_hits.items():
        if len(token) == 1:
            decided.append(token)
        elif token in from_folders:
            decided.append(token)
        elif len(token) == 2 and count >= 2:
            decided.append(token)
    return sorted(decided, key=lambda t: (-marker_hits[t], t))


def analyze(paths: list[Path]) -> dict:
    date_hits, marker_hits, folder_hits, no_date, rows = scan(paths)
    total = len(paths)
    markers = decide_markers(marker_hits, folder_hits)

    # 확정된 대상 표시를 기준으로 다시 읽어 목사님께 보여줄 예시를 만든다.
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

    return {
        "files_scanned": total,
        "date_kind": date_kind or None,
        "date_hits": date_hits,
        "date_ratio": round(date_ratio, 2),
        "files_without_date": no_date,
        "target_markers": markers,
        "marker_hits": {m: marker_hits[m] for m in markers},
        "rejected_markers": {m: n for m, n in marker_hits.items() if m not in markers},
        "reject_reason": "두 글자 이상 토큰은 제목 첫 단어일 수 있어 2회 이상 반복되거나 폴더명과 일치할 때만 인정합니다.",
        "folder_to_target": folder_hits,
        "suggested": {
            "naming.main_note_pattern": main_pattern,
            "naming.fragment_note_pattern": "{title}.md",
            "naming.target_markers": markers,
            "naming.folder_to_target": folder_hits,
            "naming.date_from_filename": bool(date_kind),
            "naming.target_from_folder": bool(folder_hits),
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
        print(json.dumps({"error": f"설교 파일(.docx/.md/.txt)을 찾지 못했습니다: {folder}",
                          "files_scanned": 0}, ensure_ascii=False, indent=2))
        return 1

    result = analyze(paths)
    result["folder"] = str(folder)
    if result["target_markers"]:
        hits = ", ".join(f"{m}({result['marker_hits'][m]}회)" for m in result["target_markers"])
        result["explain"] = f"대상 표시로 {hits} 를 찾았습니다."
    else:
        result["explain"] = ("대상 표시를 찾지 못했습니다. 파일명 전체를 제목으로 읽습니다 — "
                             "이 편이 제목 첫 단어를 대상으로 잘못 읽는 것보다 안전합니다.")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
