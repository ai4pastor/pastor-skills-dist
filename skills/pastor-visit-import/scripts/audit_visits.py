#!/usr/bin/env python3
"""1단계 — 읽기 전용 진단. 노트를 심방일지·성도 노트·혼합·무관으로 분류하고 형식을 알아본다.

    python3 scripts/audit_visits.py --vault "<볼트>" --folder "심방" [--folder "성도"] --out <work>/audit.json --table
    python3 scripts/audit_visits.py --vault "<볼트>" --table          # 폴더를 모르면 볼트 전체를 훑어 후보 폴더를 추천

출력(JSON): notes[] 에 노트별 role(visit|member|mixed|skip), format(converted|seven|template1|freeform),
confidence, guesses(name·date·visit_type), headings, sha1. 아무것도 쓰지 않는다.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import argparse
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from visit_lib import (  # noqa: E402
    H2_RE, NOTE_TYPE_MEMBER, NOTE_TYPE_VISIT, SECTION_ORDER, VISIT_SECTIONS, fm_get, iter_md,
    loose_heading_text, nfc, read_text, rel_nfc, sha1_of, split_frontmatter, synonym_key,
    wikilink_target,
)

HONORIFIC_RE = re.compile(r"\s*(담임목사|목사|사모|장로|권사|집사|성도|전도사|청년|어르신|선생|형제|자매|님|씨)+$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
YYMMDD_NAME_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})_심방일지_(.+)$")
TEMPLATE_NAME_RE = re.compile(r"^심방기록-(\d{4}-\d{2}-\d{2})-(.+)$")
DATED_H2_RE = re.compile(r"^##\s+\d{4}[-./]\d{1,2}[-./]\d{1,2}")
SKIP_DIRS = {".obsidian", ".trash", ".git", "_pastor-visit-import 백업"}

VISIT_KEYS = {"conversation", "prayer", "followUp", "visitInfo", "basicInfo", "observation", "church"}


def load_synonyms() -> dict[str, str]:
    """synonym_key → 섹션 키. data/heading_synonyms.json (+ 목사님 규칙은 plan 단계에서 합친다)."""
    path = Path(__file__).resolve().parent.parent / "data" / "heading_synonyms.json"
    data = json.loads(read_text(path))
    table: dict[str, str] = {}
    for key in SECTION_ORDER:
        table[synonym_key(VISIT_SECTIONS[key])] = key
        for word in data.get(key, []):
            table[synonym_key(word)] = key
    return table


def strip_honorific(name: str) -> str:
    name = nfc(name.strip())
    name = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", r"\1", name)
    prev = None
    while prev != name:
        prev = name
        name = HONORIFIC_RE.sub("", name).strip()
    return name


def bold_value(body: str, label: str) -> str:
    m = re.search(rf"^[ \t]*-[ \t]+\*\*{re.escape(label)}:?\*\*:?[ \t]*(.*)$", body, re.M)
    return m.group(1).strip() if m else ""


def guess_date(fm, body: str, stem: str, title: str) -> str:
    for key in ("날짜", "date", "심방일"):
        v = fm_get(fm, key)
        if v:
            m = DATE_RE.search(v)
            if m:
                return m.group(0)
    m = TEMPLATE_NAME_RE.match(stem)
    if m:
        return m.group(1)
    m = YYMMDD_NAME_RE.match(stem)
    if m:
        return f"20{m.group(1)}-{m.group(2)}-{m.group(3)}"
    for src in (stem, bold_value(body, "심방일시"), title):
        m = DATE_RE.search(src)
        if m:
            return m.group(0)
    return ""


def guess_name(fm, body: str, stem: str, title: str) -> str:
    v = fm_get(fm, "성도")
    t = wikilink_target(v) if v else None
    if t:
        return t
    if v:
        return strip_honorific(v)
    v = bold_value(body, "성명")
    if v:
        return strip_honorific(v)
    m = TEMPLATE_NAME_RE.match(stem)
    if m:
        return strip_honorific(m.group(2))
    m = YYMMDD_NAME_RE.match(stem)
    if m:
        return nfc(m.group(4))
    m = re.search(r"심방기록\s*[-—]\s*\d{4}-\d{2}-\d{2}\s*[-—]\s*(.+)$", title)
    if m:
        return strip_honorific(m.group(1))
    for src in (title, stem):
        m = re.search(r"([가-힣]{2,4})\s*(?:담임목사|목사|사모|장로|권사|집사|성도|전도사|청년|어르신|형제|자매|님|씨)?\s*심방", src)
        if m and m.group(1) not in ("정기", "특별", "위로", "축하", "전화", "병원", "가정", "새가족", "신년", "심방"):
            return m.group(1)
    return ""


def guess_visit_type(fm, body: str) -> str:
    v = fm_get(fm, "심방유형")
    if v:
        return v
    v = bold_value(body, "심방유형")
    if v:
        return v
    m = re.search(r"^\s*-\s+\[[xX]\]\s*(정기심방|특별심방|위로심방|축하심방|전화심방|병원심방|기타)", body, re.M)
    return m.group(1) if m else ""


def analyze(path: Path, vault: Path, table: dict[str, str], in_named_folder: bool = False) -> dict:
    text = read_text(path)
    fm, body_lines, has_fm = split_frontmatter(text)
    body = "\n".join(body_lines)
    stem = nfc(path.stem)
    headings = []
    for i, line in enumerate(text.split("\n")):
        m = HEADING_RE.match(line)
        if m:
            headings.append({"line": i, "level": len(m.group(1)), "text": m.group(2), "key": table.get(synonym_key(m.group(2)), "")})
    title = next((h["text"] for h in headings if h["level"] == 1), "")
    note_type = fm_get(fm, "type") or ""
    mapped = {h["key"] for h in headings if h["key"] in VISIT_KEYS}
    dated_h2 = sum(1 for h in headings if h["level"] == 2 and DATED_H2_RE.match("## " + h["text"]))

    visit_score = 0
    signals = []
    if note_type == NOTE_TYPE_VISIT:
        visit_score += 5; signals.append("type:심방일지")
    if wikilink_target(fm_get(fm, "성도")):
        visit_score += 3; signals.append("fm:성도")
    if fm_get(fm, "날짜") or fm_get(fm, "date"):
        visit_score += 1; signals.append("fm:날짜/date")
    if TEMPLATE_NAME_RE.match(stem) or YYMMDD_NAME_RE.match(stem):
        visit_score += 2; signals.append("파일명:심방")
    if "심방기록" in title or "심방" in title:
        visit_score += 1; signals.append("제목:심방")
    visit_score += min(len(mapped), 4)
    if mapped:
        signals.append("헤딩:" + ",".join(sorted(mapped)))
    if bold_value(body, "심방일시") or bold_value(body, "심방장소"):
        visit_score += 1; signals.append("본문:심방일시/장소")
    if "심방" in stem and not (TEMPLATE_NAME_RE.match(stem) or YYMMDD_NAME_RE.match(stem)):
        visit_score += 2; signals.append("파일명:심방 포함")
    if re.search(r"^\s*(?:-\s*)?(?:기도|중보|기도제목)\s*[:：]", body, re.M) or re.search(r"^\s*-\s+\[[ xX]\]\s+\S", body, re.M):
        visit_score += 1; signals.append("본문:기도/체크박스")
    if in_named_folder and note_type != NOTE_TYPE_MEMBER and not fm_get(fm, "이름"):
        visit_score += 1; signals.append("지정 폴더")

    member_score = 0
    if note_type == NOTE_TYPE_MEMBER:
        member_score += 5; signals.append("type:교인노트")
    if fm_get(fm, "이름"):
        member_score += 2; signals.append("fm:이름")
    for k in ("구역", "직분", "생년월일", "연락처", "등록일"):
        if fm_get(fm, k):
            member_score += 1
    if re.fullmatch(r"[가-힣]{2,4}(\(.+\))?", stem):
        member_score += 1
    if dated_h2 >= 2:
        signals.append(f"날짜H2:{dated_h2}")

    if note_type == NOTE_TYPE_VISIT or (visit_score >= 3 and visit_score >= member_score and dated_h2 < 2):
        role = "visit"
        confidence = min(1.0, visit_score / 6)
    elif member_score >= 2 and dated_h2 >= 2:
        role = "mixed"
        confidence = min(1.0, (member_score + dated_h2) / 7)
    elif member_score >= 3 or note_type == NOTE_TYPE_MEMBER:
        role = "member"
        confidence = min(1.0, member_score / 5)
    else:
        role = "skip"
        confidence = 0.0

    fmt = ""
    if role == "visit":
        h2_exact = [nfc(h["text"]) for h in headings if h["level"] == 2]
        targets = [re.sub(r"^##\s*", "", VISIT_SECTIONS[k]) for k in SECTION_ORDER]
        loose_h2 = {loose_heading_text(t) for t in h2_exact}
        if note_type == NOTE_TYPE_VISIT and wikilink_target(fm_get(fm, "성도")) and fm_get(fm, "날짜") and all(t in h2_exact for t in targets):
            fmt = "converted"
        elif all(loose_heading_text(t) in loose_h2 for t in targets):
            fmt = "seven"
        else:
            container = any(h["level"] == 2 and synonym_key(h["text"]) == "심방내용" for h in headings)
            h3_children = any(h["level"] == 3 and h["key"] in {"conversation", "prayer", "church"} for h in headings)
            if (container and h3_children) or (fm_get(fm, "date") and fm_get(fm, "time") and "basicInfo" in mapped):
                fmt = "template1"
            else:
                fmt = "freeform"

    return {
        "path": rel_nfc(vault, path),
        "role": role,
        "format": fmt,
        "confidence": round(confidence, 2),
        "signals": signals,
        "has_frontmatter": has_fm,
        "type": note_type,
        "guesses": {
            "name": guess_name(fm, body, stem, title) if role in ("visit", "mixed") else (fm_get(fm, "이름") or stem),
            "date": guess_date(fm, body, stem, title) if role == "visit" else "",
            "visit_type": guess_visit_type(fm, body) if role == "visit" else "",
        },
        "headings": headings,
        "mapped": sorted(mapped),
        "sha1": sha1_of(text),
        "lines": text.count("\n") + 1,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", required=True)
    ap.add_argument("--folder", action="append", default=[], help="볼트 기준 상대 폴더 (여러 번 가능)")
    ap.add_argument("--out", default="")
    ap.add_argument("--table", action="store_true")
    args = ap.parse_args(argv)

    vault = Path(args.vault).expanduser().resolve()
    if not vault.is_dir():
        print(json.dumps({"status": "error", "reason": f"볼트 폴더가 없습니다: {vault}"}, ensure_ascii=False))
        return 1
    table = load_synonyms()
    roots = [vault / f for f in args.folder] if args.folder else [vault]
    notes = []
    seen = set()
    for root in roots:
        if not root.is_dir():
            print(json.dumps({"status": "error", "reason": f"폴더가 없습니다: {root}"}, ensure_ascii=False))
            return 1
        for p in iter_md(root):
            if any(part in SKIP_DIRS for part in p.relative_to(vault).parts):
                continue
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            try:
                notes.append(analyze(p, vault, table, in_named_folder=bool(args.folder)))
            except (UnicodeDecodeError, OSError) as e:
                notes.append({"path": rel_nfc(vault, p), "role": "skip", "format": "", "confidence": 0, "signals": [f"읽기 실패: {e}"], "guesses": {}, "headings": [], "sha1": ""})

    roles = Counter(n["role"] for n in notes)
    formats = Counter(n["format"] for n in notes if n["role"] == "visit")
    folder_counter: Counter = Counter()
    for n in notes:
        if n["role"] in ("visit", "member", "mixed"):
            folder_counter[(str(Path(n["path"]).parent), n["role"])] += 1
    candidates = [{"folder": f, "role": r, "count": c} for (f, r), c in folder_counter.most_common(8)]
    result = {
        "status": "ok",
        "vault": str(vault),
        "folders": args.folder,
        "scanned": len(notes),
        "summary": {"roles": dict(roles), "formats": dict(formats)},
        "candidate_folders": candidates,
        "notes": notes,
    }
    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.table:
        print(f"볼트: {vault}")
        print(f"훑은 노트 {len(notes)}개 — 심방일지 {roles.get('visit', 0)} · 성도 노트 {roles.get('member', 0)} · 혼합 {roles.get('mixed', 0)} · 무관 {roles.get('skip', 0)}")
        if formats:
            print("심방일지 형식: " + ", ".join(f"{k} {v}" for k, v in formats.items()))
        print()
        print(f"{'역할':<6} {'형식':<10} {'신뢰':<5} {'이름':<8} {'날짜':<11} {'유형':<8} 경로")
        for n in notes:
            if n["role"] == "skip":
                continue
            g = n.get("guesses", {})
            print(f"{n['role']:<6} {n['format']:<10} {n['confidence']:<5} {g.get('name', ''):<8} {g.get('date', ''):<11} {g.get('visit_type', ''):<8} {n['path']}")
        if candidates and not args.folder:
            print("\n후보 폴더:")
            for c in candidates:
                print(f"  {c['folder'] or '(볼트 루트)'}  — {c['role']} {c['count']}개")
        if args.out:
            print(f"\n저장: {args.out}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 한국어 윈도우 콘솔·파이프에서 한글·✅ 깨짐 방지
    except (AttributeError, ValueError):
        pass
    raise SystemExit(main(sys.argv[1:]))
