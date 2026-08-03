#!/usr/bin/env python3
"""Utility helpers for pastor-sermon-import note generation."""
from __future__ import annotations

from pathlib import Path
import re
import unicodedata
from typing import Iterable

FORBIDDEN_FILENAME_CHARS = set(':?/\\*<>|"')


def sanitize_title(value: str, fallback: str = "untitled") -> str:
    text = unicodedata.normalize("NFC", value or "").strip()
    text = re.sub(r"\s+", " ", text)
    for ch in FORBIDDEN_FILENAME_CHARS:
        text = text.replace(ch, " ")
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def strip_markdown_link(value: str) -> str:
    if value.startswith("[[") and value.endswith("]]" ):
        return value[2:-2]
    return value


def unique_name(base: str, used: set[str], suffix: str = ".md") -> str:
    stem = sanitize_title(base)
    name = f"{stem}{suffix}"
    if name not in used:
        used.add(name)
        return name
    index = 2
    while True:
        candidate = f"{stem}_{index:02d}{suffix}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        index += 1


def ensure_relative_folder(folder: str) -> Path:
    p = Path(folder)
    if p.is_absolute():
        raise ValueError(f"vault-relative folder required, got absolute path: {folder}")
    if ".." in p.parts:
        raise ValueError(f"folder must not contain '..': {folder}")
    return p


def yaml_list(key: str, values: Iterable[str], quote: bool = True) -> list[str]:
    rows = [f"{key}:"]
    values = list(values)
    if not values:
        rows.append("  []")
        return rows
    for value in values:
        rows.append(f"  - \"{value}\"" if quote else f"  - {value}")
    return rows


def format_frontmatter(fields: dict[str, object]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.extend(yaml_list(key, [str(v) for v in value], quote=True))
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif value is None:
            lines.append(f"{key}: null")
        else:
            lines.append(f"{key}: \"{value}\"")
    lines.append("---")
    return "\n".join(lines) + "\n"
