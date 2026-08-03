#!/usr/bin/env python3
"""Utility helpers for pastor-sermon-import note generation.

Normalization rule (one place, three cases):
- reading  -> nfc() only
- comparing -> compare_key() (NFC + variation selector removed + wikilink stripped)
- writing  -> the value exactly as the pastor stored it

Emoji values such as "🏷️ 설교" carry an optional U+FE0F variation selector, and
macOS hands back decomposed (NFD) Hangul from the filesystem. Comparing raw
strings therefore fails on values the pastor copied out of their own vault, so
every allow-list check must go through compare_key().
"""
from __future__ import annotations

from pathlib import Path
import re
import unicodedata
from typing import Iterable

# Obsidian 금지 문자 + wikilink 안에서 의미를 갖는 문자들.
# '#'(헤딩) '^'(블록 참조) '[' ']'(링크 경계)가 파일명에 남으면
# `[[제목 #1]]` 이 헤딩 참조로 해석돼 역방향 링크가 조용히 깨진다.
FORBIDDEN_FILENAME_CHARS = set(':?/\\*<>|"#^[]')
VARIATION_SELECTOR = "️"

# Nouns that signal a label-shaped title ("계시의 필요성") rather than a claim
# ("유한한 인간에게 계시는 필수다").
LABEL_TAILS = (
    "필요성", "중요성", "차이", "이해", "의미", "개요", "태도",
    "방법", "이유", "과정", "특징", "원리", "정의", "개념", "역할",
)
# Korean sentence-final endings that indicate a proposition.
CLAIM_TAILS = ("다", "라", "까", "요", "자", "냐", "오", "죠", "군", "네")

TITLE_LIMITS = {"argument": (10, 20), "illustration": (15, 25)}


def nfc(value: str) -> str:
    """Normalize to NFC. Use when reading any external string."""
    return unicodedata.normalize("NFC", value or "")


# 설교가 아닌데 설교 파일처럼 보이는 것들.
GOOGLE_STUB_SUFFIXES = {".gdoc", ".gsheet", ".gslides", ".gdraw", ".gform"}


def sidecar_reason(path: Path) -> str:
    """설교로 다루면 안 되는 파일이면 그 이유를, 아니면 빈 문자열.

    워드는 문서를 열어 둔 동안 "~$설교.docx" 를 남기고, macOS 는 "._이름" 리소스
    포크를 떨어뜨린다. 구글 드라이브의 ".gdoc" 은 실제 문서가 아니라 링크 한 줄이고,
    클라우드 동기화 폴더에는 아직 내려오지 않은 0바이트 자리표시자가 있다.
    넷 다 그냥 두면 빈 설교 노트가 된다.
    """
    name = path.name
    if name.startswith("~$"):
        return "lock_file"
    if name.startswith("._"):
        return "mac_metadata"
    if name.startswith("."):
        return "hidden"
    if path.suffix.lower() in GOOGLE_STUB_SUFFIXES:
        return "google_stub"
    try:
        if path.is_file() and path.stat().st_size == 0:
            return "empty_or_cloud_placeholder"
    except OSError:
        return "unreadable"
    return ""


def is_sidecar(path: Path) -> bool:
    """Word lock files, macOS metadata, and cloud stubs are not sermons."""
    return bool(sidecar_reason(path))


def strip_vs(value: str) -> str:
    """Drop the emoji variation selector so 🏷️ and 🏷 compare equal."""
    return (value or "").replace(VARIATION_SELECTOR, "")


def strip_wikilink(value: str) -> str:
    """Unwrap [[target]] or [[target|alias]] to its target."""
    text = (value or "").strip()
    if text.startswith("[[") and text.endswith("]]"):
        text = text[2:-2]
        if "|" in text:
            text = text.split("|", 1)[0]
    return text.strip()


def compare_key(value: str) -> str:
    """Canonical form for allow-list checks and duplicate detection."""
    return strip_vs(nfc(strip_wikilink(str(value)))).strip()


def collapse_separators(name: str) -> str:
    """Collapse separator runs left by empty pattern placeholders.

    "260101__제목" -> "260101_제목", "_최종_" -> "최종"
    """
    text = re.sub(r"_{2,}", "_", name or "")
    text = re.sub(r"\s*_\s*", "_", text)
    return text.strip("_- ")


def sanitize_title(value: str, fallback: str = "untitled") -> str:
    text = nfc(value).strip()
    text = re.sub(r"\s+", " ", text)
    for ch in FORBIDDEN_FILENAME_CHARS:
        text = text.replace(ch, " ")
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or fallback


def strip_markdown_link(value: str) -> str:
    """Backwards-compatible alias for strip_wikilink()."""
    return strip_wikilink(value)


def check_title_style(title: str, kind: str = "argument") -> list[str]:
    """Return style warnings for a fragment title. Never rejects — only warns.

    Rejecting a title would drop that fragment's sermon content, so the caller
    reports these to the pastor and keeps the fragment.
    """
    warnings: list[str] = []
    text = nfc(title).strip()
    if not text:
        return ["제목이 비어 있음"]

    is_illustration = kind == "illustration" or text.startswith("💡")
    low, high = TITLE_LIMITS["illustration" if is_illustration else "argument"]
    body = text[1:].strip() if text.startswith("💡") else text
    length = len(body)
    if length < low or length > high:
        label = "예화" if is_illustration else "본 메시지"
        warnings.append(f"제목 '{text}': {label} 제목 권장 길이 {low}~{high}자, 현재 {length}자")

    if is_illustration:
        if not text.startswith("💡 "):
            warnings.append(f"제목 '{text}': 예화 조각은 '💡 '로 시작해야 함")
        if " - " not in body:
            warnings.append(f"제목 '{text}': 예화 제목은 '{{비유명}} - {{핵심메시지}}' 형식")
        return warnings

    if body.endswith(LABEL_TAILS):
        warnings.append(f"제목 '{text}': 라벨형으로 보임 — 명제형 문장으로 (예: 'X는 Y다')")
    elif not (body.endswith(CLAIM_TAILS) or body.endswith(("?", "!", "."))):
        warnings.append(f"제목 '{text}': 명제형이 아님 — 문장으로 끝나야 함")
    if " " not in body and length < 8:
        warnings.append(f"제목 '{text}': 한 단어 제목 — 내용이 드러나는 문장으로")
    return warnings


def parse_bullets(md_text: str) -> tuple[str, list[str], str]:
    """Split an existing fragment note into (frontmatter, bullets, trailer).

    The frontmatter block is returned verbatim so a merge can reuse the pastor's
    existing values byte-for-byte instead of regenerating them.
    """
    text = md_text or ""
    frontmatter = ""
    rest = text
    m = re.match(r"\A(---\n.*?\n---\n)", text, re.DOTALL)
    if m:
        frontmatter = m.group(1)
        rest = text[m.end():]

    lines = rest.splitlines()
    bullets: list[str] = []
    last_bullet_index = -1
    for idx, line in enumerate(lines):
        if re.match(r"^\s*[-*]\s+", line):
            bullets.append(re.sub(r"^\s*[-*]\s+", "", line).strip())
            last_bullet_index = idx
    trailer_lines = lines[last_bullet_index + 1:] if last_bullet_index >= 0 else lines
    trailer = "\n".join(trailer_lines)
    return frontmatter, bullets, trailer


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


DATE_VALUE_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?\Z")
YAML_SPECIAL_RE = re.compile(r"""[:\[\]{}&*!|>%@#,"']""")


def needs_quote(value: str) -> bool:
    """Whether a scalar has to be quoted.

    Follows the vault guideline: wikilinks are quoted, timestamps are not. Bare
    Korean tags stay bare so an imported note looks like the pastor's own notes
    rather than a machine-generated one.
    """
    if value == "":
        return True
    if DATE_VALUE_RE.match(value):
        return False
    if value != value.strip():
        return True
    if value[0] in "-?":
        return True
    return bool(YAML_SPECIAL_RE.search(value))


def yaml_scalar(value: str) -> str:
    return f'"{value}"' if needs_quote(value) else value


def yaml_list(key: str, values: Iterable[str], quote: bool | None = None) -> list[str]:
    rows = [f"{key}:"]
    values = list(values)
    if not values:
        rows.append("  []")
        return rows
    for value in values:
        text = str(value)
        use_quote = needs_quote(text) if quote is None else quote
        rows.append(f'  - "{text}"' if use_quote else f"  - {text}")
    return rows


def format_frontmatter(fields: dict[str, object]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.extend(yaml_list(key, [str(v) for v in value]))
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif value is None:
            lines.append(f"{key}: null")
        else:
            lines.append(f"{key}: {yaml_scalar(str(value))}")
    lines.append("---")
    return "\n".join(lines) + "\n"
