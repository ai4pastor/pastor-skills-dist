#!/usr/bin/env python3
"""Extract sermon metadata from file name and text.

This module is deterministic and read-only.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import re
import sys
from typing import Any

import urllib.parse

from extract_bible_refs import extract as extract_bible_refs
from config_loader import default_config, load_config
from note_utils import compare_key, sanitize_title

DATE_PATTERNS = [
    re.compile(r"(?P<date>\d{6})[_\-\s]+(?P<rest>.+)$"),
    re.compile(r"(?P<date>\d{4}[-.]?\d{2}[-.]?\d{2})[_\-\s]+(?P<rest>.+)$"),
]


def normalize_date(raw: str) -> str:
    raw = raw.strip().replace(".", "-")
    if re.fullmatch(r"\d{6}", raw):
        yy = int(raw[:2])
        year = 2000 + yy if yy < 70 else 1900 + yy
        return f"{year:04d}-{raw[2:4]}-{raw[4:6]}"
    if re.fullmatch(r"\d{8}", raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    return ""


def compact_date(date: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return date[2:4] + date[5:7] + date[8:10]
    return "undated"


def folder_target(path: Path, config: dict[str, Any]) -> str:
    """Fall back to the containing folder name for the audience marker."""
    naming = config.get("naming", {})
    if not naming.get("target_from_folder", True):
        return ""
    mapping = naming.get("folder_to_target") or {}
    if not mapping:
        return ""
    strip_prefix = naming.get("folder_number_prefix_strip", True)
    lookup = {compare_key(folder): str(target) for folder, target in mapping.items()}
    for parent in list(path.parents)[:2]:
        name = parent.name
        if strip_prefix:
            name = re.sub(r"^\d+\.\s*", "", name)
        hit = lookup.get(compare_key(name))
        if hit:
            return hit
    return ""


def parse_filename(path: Path, config: dict[str, Any] | None = None) -> dict[str, str]:
    """Split a file name into date / audience marker / title.

    The audience marker is only extracted when the pastor declared their markers
    in naming.target_markers. With an empty list the whole remainder is the
    title — otherwise "260101_믿음의 길.md" would yield target="믿음의",
    title="길", which is how the previous heuristic mangled every file name that
    did not use a marker.
    """
    config = config or default_config()
    naming = config.get("naming", {})
    raw_stem = path.stem
    if "%" in raw_stem:
        raw_stem = urllib.parse.unquote(raw_stem)
    stem = sanitize_title(raw_stem)

    date = ""
    rest = stem
    if naming.get("date_from_filename", True):
        for pat in DATE_PATTERNS:
            m = pat.match(stem)
            if m:
                date = normalize_date(m.group("date"))
                rest = m.group("rest")
                break

    target = ""
    title = rest
    markers = [str(m).strip() for m in (naming.get("target_markers") or []) if str(m).strip()]
    if markers:
        # Longest first so "청소년" wins over "청"; the lookahead keeps "대하여"
        # from being read as the marker "대".
        alt = "|".join(re.escape(m) for m in sorted(markers, key=len, reverse=True))
        m = re.match(rf"^(?P<target>{alt})(?=[\s_\-]|$)[\s_\-]*-?\s*(?P<title>.*)$", rest)
        if m and m.group("title").strip():
            target = sanitize_title(m.group("target"))
            title = m.group("title")
    if not target:
        target = folder_target(path, config)
    return {"date": date, "target": target, "title": sanitize_title(title)}


def first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        cleaned = sanitize_title(re.sub(r"^#+\s*", "", line.strip()))
        if cleaned:
            return cleaned
    return "untitled"


def build_sermon_id(meta: dict[str, str], main_passage: str) -> str:
    date_part = compact_date(meta.get("date", ""))
    title_part = sanitize_title(meta.get("title", "untitled"))[:40]
    passage_part = sanitize_title(main_passage or "no본문")
    return sanitize_title(f"{date_part}_{title_part}_{passage_part}")


def extract_meta(path: Path, text: str, config: dict[str, Any]) -> dict[str, Any]:
    meta = parse_filename(path, config)
    if not meta["title"] or meta["title"] == "untitled":
        meta["title"] = first_nonempty_line(text)
    bible = extract_bible_refs(text, config)
    ok_refs = [r for r in bible if r.get("status") == "ok"]
    main_passage = ok_refs[0]["normalized"] if ok_refs else ""
    sermon_id = build_sermon_id(meta, main_passage)
    return {
        "source_path": str(path),
        "source_name": path.name,
        "date": meta.get("date", ""),
        "yymmdd": compact_date(meta.get("date", "")),
        "target": meta.get("target", ""),
        "title": meta.get("title", "untitled"),
        "main_passage": main_passage,
        "sermon_id": sermon_id,
        "bible_refs": bible,
        "extracted_at": datetime.now().isoformat(timespec="minutes"),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: extract_meta.py <file> [config.json]", file=sys.stderr)
        return 2
    path = Path(argv[1]).expanduser()
    config = load_config(argv[2]) if len(argv) >= 3 else default_config()
    text = path.read_text(encoding="utf-8") if path.suffix.lower() in {".md", ".txt"} else ""
    print(json.dumps(extract_meta(path, text, config), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
