#!/usr/bin/env python3
"""pastor-visit-import 공용 라이브러리 — 표준 라이브러리만 쓴다 (시스템 python3 3.8+).

a4p-pastoral-visit 플러그인(src/sync-core.ts, src/utils.ts, src/constants.ts)의 순수 로직을
**바이트 호환**으로 옮긴 것이다. 플러그인이 성도 노트에 쓰는 줄과 이 스크립트가 쓰는 줄이
글자 하나까지 같아야 플러그인의 멱등(이미 반영됨) 판정이 그대로 동작한다. 임의로 바꾸지 말 것.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import os
import re
import unicodedata

# ── 플러그인 계약 상수 (src/constants.ts) ──
VISIT_SECTIONS = {
    "basicInfo": "## 📋 기본정보",
    "visitInfo": "## 📍 심방정보",
    "conversation": "## 📝 대화내용",
    "prayer": "## 🙏 기도제목",
    "church": "## ⛪ 교회 관련",
    "observation": "## 🔍 관찰 및 평가",
    "followUp": "## 💡 후속조치",
}
SECTION_ORDER = ["basicInfo", "visitInfo", "conversation", "prayer", "church", "observation", "followUp"]
ANCHOR_KEYS = ["conversation", "prayer", "followUp"]
MEMBER_VISIT_LOG = "## 📝 심방 기록"
MEMBER_EMBEDS = "## 📌 중요 심방 내용 (임베드)"
NOTE_TYPE_MEMBER = "교인노트"
NOTE_TYPE_VISIT = "심방일지"
VISIT_TYPES = ["정기심방", "특별심방", "위로심방"]
SUMMARY_EXCLUDE_LABELS = ["주요 대화 주제", "본인 기도제목", "가족 기도제목"]
PLACEHOLDER_LOG = "(심방 기록이 추가되면 여기에 링크됩니다)"
PLACEHOLDER_EMBED = "(임베드가 여기에 추가됩니다)"

H2_RE = re.compile(r"^##\s")
H3_RE = re.compile(r"^###")
# 이모지 제거 — 파이썬 re 에는 \p{Extended_Pictographic} 이 없어 명시 범위로 (7개 헤딩 이모지 전부 포함)
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿←-⇿■-◿️‍]"
)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha1_of(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def loose_heading_text(s: str) -> str:
    """src/utils.ts looseHeadingText — `##` 접두·이모지·중복 공백 제거."""
    t = nfc(s)
    t = re.sub(r"^#+\s*", "", t)
    t = EMOJI_RE.sub("", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def synonym_key(s: str) -> str:
    """동의어 표 조회 키 — 느슨 텍스트에서 공백·끝 콜론까지 제거."""
    return loose_heading_text(s).replace(" ", "").rstrip(":")


def find_section_range(lines: list[str], heading_text: str):
    """src/sync-core.ts findSectionRange — (heading_line, end_line) 또는 None. H2 만 느슨 매칭."""
    target = nfc(heading_text.strip())
    heading_line = -1
    for i, line in enumerate(lines):
        if nfc(line.strip()) == target:
            heading_line = i
            break
    if heading_line == -1:
        loose = loose_heading_text(heading_text)
        if loose:
            for i, line in enumerate(lines):
                if not H2_RE.match(line) or H3_RE.match(line):
                    continue
                if loose_heading_text(line) == loose:
                    heading_line = i
                    break
    if heading_line == -1:
        return None
    end_line = len(lines)
    for i in range(heading_line + 1, len(lines)):
        if H2_RE.match(lines[i]) and not H3_RE.match(lines[i]):
            end_line = i
            break
    return heading_line, end_line


def extract_summary(visit_content: str, visit_type: str, date: str,
                    conversation_heading: str = VISIT_SECTIONS["conversation"]) -> str:
    """src/sync-core.ts extractSummary — 대화내용의 볼드 라벨 상위 2개."""
    lines = visit_content.split("\n")
    rng = find_section_range(lines, conversation_heading)
    labels: list[str] = []
    if rng:
        label_re = re.compile(r"^\s*-\s+\*\*(.+?):?\*\*")
        for i in range(rng[0] + 1, rng[1]):
            m = label_re.match(lines[i])
            if not m:
                continue
            label = re.sub(r":$", "", m.group(1))
            label = re.sub(r"\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]",
                           lambda mm: mm.group(2) if mm.group(2) else mm.group(1), label).strip()
            if not label or label in SUMMARY_EXCLUDE_LABELS:
                continue
            if label not in labels:
                labels.append(label)
            if len(labels) >= 2:
                break
    base = f"{visit_type} ({date})"
    return f"{base}, {', '.join(labels)}" if labels else base


def build_log_line(visit_basename: str, summary: str) -> str:
    return f"- [[{visit_basename}]] — {summary}"


def resolve_anchors(visit_content: str) -> list[str]:
    """src/sync-core.ts resolveAnchors — 일지의 실제 헤딩 텍스트(## 제외)."""
    lines = visit_content.split("\n")
    out = []
    for key in ANCHOR_KEYS:
        heading = VISIT_SECTIONS[key]
        rng = find_section_range(lines, heading)
        if rng:
            out.append(nfc(re.sub(r"^##\s*", "", lines[rng[0]]).strip()))
        else:
            out.append(re.sub(r"^##\s*", "", heading).strip())
    return out


def build_embed_block(visit_basename: str, date: str, visit_type: str, anchors: list[str]) -> list[str]:
    return [f"### {date} {visit_type}"] + [f"![[{visit_basename}#{a}]]" for a in anchors]


def section_contains_link(lines: list[str], rng, visit_basename: str) -> bool:
    needle = f"[[{nfc(visit_basename)}"
    return any(needle in nfc(lines[i]) for i in range(rng[0] + 1, rng[1]))


LOG_DATE_RE = re.compile(r"^-\s+\[\[.+?\]\].*?\((\d{4}-\d{2}-\d{2})\)")
EMBED_DATE_RE = re.compile(r"^###\s+(\d{4}-\d{2}-\d{2})\s")


def compute_append(content: str, section_heading: str, new_block: list[str], new_date: str,
                   visit_basename: str, date_re) -> dict:
    """src/sync-core.ts computeAppend — 날짜순 삽입, 섹션 신설, 멱등 skip."""
    lines = content.split("\n")
    rng = find_section_range(lines, section_heading)
    if rng is None:
        out = list(lines)
        while out and out[-1].strip() == "":
            out.pop()
        out += ["", section_heading, "", *new_block, ""]
        return {"content": "\n".join(out), "created": True, "midway": False, "skipped": False}
    if section_contains_link(lines, rng, visit_basename):
        return {"content": content, "created": False, "midway": False, "skipped": True}
    dated = []
    for i in range(rng[0] + 1, rng[1]):
        m = date_re.match(lines[i])
        if m:
            dated.append((i, m.group(1)))
    insert_at = rng[1]
    while insert_at > rng[0] + 1 and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    midway = False
    for i, d in dated:
        if d > new_date:
            insert_at = i
            midway = True
            break
    out = list(lines)
    if len(new_block) > 1:
        prev_blank = insert_at - 1 >= 0 and out[insert_at - 1].strip() == ""
        to_insert = ([] if prev_blank else [""]) + list(new_block) + [""]
    else:
        to_insert = list(new_block)
    out[insert_at:insert_at] = to_insert
    return {"content": "\n".join(out), "created": False, "midway": midway, "skipped": False}


def plan_sync(member_content: str, visit_basename: str, date: str, visit_type: str, summary: str,
              anchors: list[str]) -> dict:
    """src/sync-core.ts planSync — 심방 기록 줄 + 임베드 블록."""
    log_line = build_log_line(visit_basename, summary)
    embed_block = build_embed_block(visit_basename, date, visit_type, anchors)
    warnings: list[str] = []
    s1 = compute_append(member_content, MEMBER_VISIT_LOG, [log_line], date, visit_basename, LOG_DATE_RE)
    if s1["created"]:
        warnings.append(f'"{MEMBER_VISIT_LOG}" 섹션이 없어 문서 끝에 새로 만듭니다.')
    s2 = compute_append(s1["content"], MEMBER_EMBEDS, embed_block, date, visit_basename, EMBED_DATE_RE)
    if s2["created"]:
        warnings.append(f'"{MEMBER_EMBEDS}" 섹션이 없어 문서 끝에 새로 만듭니다.')
    return {
        "content": s2["content"],
        "log_line": log_line,
        "embed_block": embed_block,
        "warnings": warnings,
        "nothing_to_do": s1["skipped"] and s2["skipped"],
    }


# ── 프론트매터 (줄 단위 — YAML 파서 없음, 원문 보존) ──

def split_frontmatter(text: str):
    """(fm_lines, body_lines, has_fm). 원문을 다시 합치면 바이트가 같다."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[1:i], lines[i + 1:], True
    return [], lines, False


def join_note(fm_lines: list[str], body_lines: list[str], has_fm: bool) -> str:
    if has_fm or fm_lines:
        return "\n".join(["---", *fm_lines, "---", *body_lines])
    return "\n".join(body_lines)


def unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1].replace('\\"', '"')
    return v


def fm_get(fm_lines: list[str], key: str):
    for i, line in enumerate(fm_lines):
        m = re.match(rf"^{re.escape(key)}:\s*(.*)$", line)
        if m:
            val = m.group(1).strip()
            if val:
                return unquote(val)
            for nxt in fm_lines[i + 1:]:
                if re.match(r"^\s*-\s+", nxt):
                    return unquote(re.sub(r"^\s*-\s+", "", nxt).strip())
                if not nxt.startswith(" "):
                    break
            return ""
    return None


def fm_has(fm_lines: list[str], key: str) -> bool:
    return any(re.match(rf"^{re.escape(key)}:(\s|$)", l) for l in fm_lines)


def yaml_scalar(s: str) -> str:
    """src/utils.ts yamlString 과 같은 규칙."""
    if re.search(r"[:#\-?&*,\[\]{}|>!%@`'\"\n]", s) or re.search(r"^\s|\s$", s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def wikilink_target(value) -> str | None:
    if not isinstance(value, str):
        return None
    m = WIKILINK_RE.search(value)
    return nfc(m.group(1).strip()) if m and m.group(1).strip() else None


def yymmdd(date: str) -> str | None:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date or "")
    return f"{m.group(1)[2:]}{m.group(2)}{m.group(3)}" if m else None


def visit_basename(date: str, member: str) -> str | None:
    y = yymmdd(date)
    return f"{y}_심방일지_{nfc(member)}" if y and member else None


# ── 파일 유틸 ──

def iter_md(root: Path):
    for p in sorted(root.rglob("*.md")):
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        yield p


def rel_nfc(root: Path, p: Path) -> str:
    return nfc(p.relative_to(root).as_posix())


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def setup_stdout() -> None:
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8")  # 한국어 윈도우 콘솔
    except (AttributeError, ValueError):
        pass
