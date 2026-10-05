#!/usr/bin/env python3
"""2단계 — 변환 계획(plan.json). 결정론 규칙(헤딩 동의어·프론트매터 보강)만 쓴다. 파일을 쓰지 않는다.

    python3 scripts/plan_visits.py --audit <work>/audit.json --member-folder "성도" --visit-folder "심방" \
        --out <work>/plan.json [--merge <work>/llm_plan.json] [--rules <홈>/visit_rules.md] [--table]

- 자유형(freeform) 노트는 needs_llm 에 담기만 한다 → Claude 가 prompts/classify_freeform.md 로 llm_plan.json 을 쓰고 --merge.
- 계획에는 sha1·first_text 가 들어가 apply 단계에서 파일이 바뀌었으면 거부한다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_visits import load_synonyms, strip_honorific  # noqa: E402
from visit_lib import (  # noqa: E402
    ANCHOR_KEYS, NOTE_TYPE_VISIT, SECTION_ORDER, VISIT_SECTIONS, VISIT_TYPES, fm_get, nfc, read_text,
    split_frontmatter, synonym_key, yaml_scalar,
)

CONTAINER_KEYS = {"심방내용", "내용"}


def load_rules(path: Path, table: dict[str, str]) -> int:
    """visit_rules.md 의 `- 대화내용: 심방나눔, 이야기` 같은 줄을 동의어로 추가."""
    if not path or not path.is_file():
        return 0
    name_to_key = {synonym_key(VISIT_SECTIONS[k]): k for k in SECTION_ORDER}
    name_to_key.update({k: k for k in SECTION_ORDER})
    added = 0
    for line in read_text(path).split("\n"):
        m = re.match(r"^\s*-\s*([^:：]+)[:：]\s*(.+)$", line)
        if not m:
            continue
        key = name_to_key.get(synonym_key(m.group(1)))
        if not key:
            continue
        for word in re.split(r"[,，/]", m.group(2)):
            if word.strip():
                table[synonym_key(word)] = key
                added += 1
    return added


def member_index(vault: Path, member_folder: str) -> dict[str, str]:
    """성도 폴더의 파일명(NFC) → 상대경로."""
    root = vault / member_folder if member_folder else vault
    out: dict[str, str] = {}
    if root.is_dir():
        for p in sorted(root.rglob("*.md")):
            if any(part.startswith(".") for part in p.relative_to(vault).parts):
                continue
            out[nfc(p.stem)] = nfc(p.relative_to(vault).as_posix())
    return out


def resolve_member(name: str, index: dict[str, str]) -> dict:
    name = nfc(name)
    if not name:
        return {"name": "", "exists": False, "create": False, "path": "", "hold": "성도 이름을 알 수 없음"}
    if name in index:
        return {"name": name, "exists": True, "create": False, "path": index[name], "hold": ""}
    stripped = strip_honorific(name)
    if stripped in index:
        return {"name": stripped, "exists": True, "create": False, "path": index[stripped], "hold": ""}
    partial = [n for n in index if n.startswith(stripped) or stripped.startswith(n)]
    if len(partial) == 1:
        return {"name": partial[0], "exists": True, "create": False, "path": index[partial[0]], "hold": ""}
    if len(partial) > 1:
        return {"name": stripped, "exists": False, "create": False, "path": "", "hold": f"후보 여럿: {', '.join(partial)}"}
    return {"name": stripped, "exists": False, "create": True, "path": "", "hold": ""}


def plan_note(note: dict, text: str, table: dict[str, str], index: dict[str, str]) -> dict:
    lines = text.split("\n")
    fm, _, has_fm = split_frontmatter(text)
    hold: list[str] = []
    fixes: list[dict] = []
    assigned: dict[str, int] = {}

    headings = note["headings"]
    # 컨테이너 판정: 심방내용 H2 아래에 매핑되는 H3 가 있는가
    for idx, h in enumerate(headings):
        if h["level"] != 2 or synonym_key(h["text"]) not in CONTAINER_KEYS:
            continue
        children = []
        for h2 in headings[idx + 1:]:
            if h2["level"] <= 2:
                break
            children.append(h2)
        if any(table.get(synonym_key(c["text"])) for c in children):
            h["container"] = True

    # 선등록: 이미 플러그인 헤딩과 정확히 같은 H2 — 이 섹션 키는 다른 헤딩이 차지할 수 없다
    for h in headings:
        if h["level"] == 2:
            for k in SECTION_ORDER:
                if lines[h["line"]].strip() == VISIT_SECTIONS[k]:
                    assigned.setdefault(k, h["line"])
    for h in headings:
        if h["level"] not in (2, 3) or h.get("container"):
            continue
        key = table.get(synonym_key(h["text"]))
        if not key:
            continue
        target = VISIT_SECTIONS[key]
        if lines[h["line"]].strip() == target:
            continue
        if key in assigned:
            hold.append(f'{h["line"] + 1}행 "{h["text"]}" — 같은 섹션({target})이 이미 있어 그대로 둠')
            continue
        assigned[key] = h["line"]
        fixes.append({"line": h["line"], "from": lines[h["line"]], "to": target})

    fm_add: dict[str, str] = {}
    if fm_get(fm, "type") is None:
        fm_add["type"] = NOTE_TYPE_VISIT
    elif fm_get(fm, "type") != NOTE_TYPE_VISIT:
        hold.append(f"프론트매터 type 이 이미 '{fm_get(fm, 'type')}' — 사람이 판단")
    g = note.get("guesses", {})
    member = resolve_member(g.get("name", ""), index)
    if member["hold"]:
        hold.append(f"성도 해석 실패: {member['hold']}")
    if fm_get(fm, "성도") is None and member["name"] and not member["hold"]:
        fm_add["성도"] = yaml_scalar(f"[[{member['name']}]]")
    if fm_get(fm, "날짜") is None:
        if g.get("date"):
            fm_add["날짜"] = g["date"]
        else:
            hold.append("날짜를 알 수 없음 — 프론트매터 날짜: YYYY-MM-DD 를 직접 넣어야 함")
    if fm_get(fm, "심방유형") is None and g.get("visit_type"):
        fm_add["심방유형"] = yaml_scalar(g["visit_type"])
    nonstandard = g.get("visit_type") and g["visit_type"] not in VISIT_TYPES

    present = set(assigned)
    for h in headings:
        if h["level"] == 2:
            k = table.get(synonym_key(h["text"]))
            if k and lines[h["line"]].strip() == VISIT_SECTIONS[k]:
                present.add(k)
    new_sections = [VISIT_SECTIONS[k] for k in ANCHOR_KEYS if k not in present]

    return {
        "path": note["path"],
        "sha1": note["sha1"],
        "role": note["role"],
        "format": note["format"],
        "source": "rule",
        "has_frontmatter": has_fm,
        "frontmatter_add": fm_add,
        "heading_fixes": fixes,
        "moves": [],
        "new_sections": new_sections,
        "member": member,
        "nonstandard_visit_type": g.get("visit_type", "") if nonstandard else "",
        "hold": hold,
        "blocking": any(x.startswith("프론트매터 type") for x in hold),
    }


def merge_llm(plan_notes: dict[str, dict], llm: dict, vault: Path, index: dict[str, str]) -> list[str]:
    msgs = []
    for item in llm.get("notes", []):
        path = item.get("path", "")
        target = plan_notes.get(nfc(path))
        if not target:
            msgs.append(f"{path}: 계획에 없는 노트 — 무시")
            continue
        full = vault / path
        if not full.is_file():
            msgs.append(f"{path}: 파일 없음 — 무시")
            continue
        text = read_text(full)
        if item.get("sha1") and item["sha1"] != target["sha1"]:
            msgs.append(f"{path}: sha1 불일치 — LLM 계획 무시")
            continue
        lines = text.split("\n")
        ok = True
        for fx in item.get("heading_fixes", []):
            ln = fx.get("line")
            if not isinstance(ln, int) or ln < 0 or ln >= len(lines) or lines[ln] != fx.get("from"):
                msgs.append(f"{path}: heading_fixes {fx} 가 파일과 안 맞음 — 무시")
                ok = False
        for mv in item.get("moves", []):
            a, b = (mv.get("lines") or [None, None])[:2]
            if not (isinstance(a, int) and isinstance(b, int) and 0 <= a <= b < len(lines)):
                msgs.append(f"{path}: moves 범위 오류 {mv.get('lines')} — 무시")
                ok = False
            elif lines[a].strip() != str(mv.get("first_text", "")).strip():
                msgs.append(f"{path}: moves first_text 불일치 ({a}행) — 무시")
                ok = False
            elif mv.get("to") not in VISIT_SECTIONS.values():
                msgs.append(f"{path}: moves 대상 '{mv.get('to')}' 는 7개 헤딩이 아님 — 무시")
                ok = False
        if not ok:
            continue
        target["heading_fixes"] = sorted(target["heading_fixes"] + [fx for fx in item.get("heading_fixes", [])
                                                                     if fx["line"] not in {f["line"] for f in target["heading_fixes"]}],
                                         key=lambda f: f["line"])
        target["moves"] = item.get("moves", [])
        for k, v in (item.get("frontmatter_add") or {}).items():
            target["frontmatter_add"].setdefault(k, v if k in ("type", "날짜") else yaml_scalar(str(v)))
        if item.get("new_sections"):
            target["new_sections"] = [s for s in VISIT_SECTIONS.values() if s in set(target["new_sections"]) | set(item["new_sections"])]
        if item.get("member_name") and not target["member"]["exists"]:
            target["member"] = resolve_member(item["member_name"], index)
            fm_now, _, _ = split_frontmatter(text)
            if target["member"]["name"] and not target["member"]["hold"] and fm_get(fm_now, "성도") is None:
                target["frontmatter_add"].setdefault("성도", yaml_scalar(f"[[{target['member']['name']}]]"))
            target["hold"] = [h for h in target["hold"] if not h.startswith("성도 해석 실패")]
            if target["member"]["hold"]:
                target["hold"].append(f"성도 해석 실패: {target['member']['hold']}")
        target["source"] = "rule+llm"
        msgs.append(f"{path}: LLM 계획 병합 (교정 {len(item.get('heading_fixes', []))}, 이동 {len(item.get('moves', []))})")
    return msgs


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--member-folder", default="")
    ap.add_argument("--visit-folder", default="")
    ap.add_argument("--merge", default="")
    ap.add_argument("--rules", default="")
    ap.add_argument("--min-confidence", type=float, default=0.5)
    ap.add_argument("--table", action="store_true")
    args = ap.parse_args(argv)

    audit = json.loads(read_text(Path(args.audit).expanduser()))
    vault = Path(audit["vault"])
    table = load_synonyms()
    added = load_rules(Path(args.rules).expanduser(), table) if args.rules else 0
    index = member_index(vault, args.member_folder)

    notes: dict[str, dict] = {}
    needs_llm: list[str] = []
    skipped: list[str] = []
    for n in audit["notes"]:
        if n["role"] != "visit":
            if n["role"] == "mixed":
                skipped.append(f"{n['path']}: 혼합 노트(성도 노트 안에 여러 심방) — 이번 판에서는 손대지 않음")
            continue
        if n["confidence"] < args.min_confidence:
            skipped.append(f"{n['path']}: 신뢰도 {n['confidence']} < {args.min_confidence}")
            continue
        text = read_text(vault / n["path"])
        p = plan_note(n, text, table, index)
        notes[nfc(n["path"])] = p
        if n["format"] == "freeform":
            needs_llm.append(n["path"])

    msgs: list[str] = []
    if args.merge:
        llm = json.loads(read_text(Path(args.merge).expanduser()))
        msgs = merge_llm(notes, llm, vault, index)
        needs_llm = [p for p in needs_llm if notes[nfc(p)]["source"] == "rule"]

    def counts(p: dict) -> dict:
        return {
            "추가": len(p["frontmatter_add"]) + len(p["new_sections"]),
            "교정": len(p["heading_fixes"]),
            "이동": len(p["moves"]),
            "보류": len(p["hold"]),
        }

    plan = {
        "version": 1,
        "vault": str(vault),
        "member_folder": args.member_folder,
        "visit_folder": args.visit_folder,
        "synonyms_from_rules": added,
        "notes": list(notes.values()),
        "needs_llm": needs_llm,
        "skipped": skipped,
        "merge_messages": msgs,
        "summary": {
            "notes": len(notes),
            "converted_noop": sum(1 for p in notes.values() if not p["frontmatter_add"] and not p["heading_fixes"] and not p["moves"] and not p["new_sections"]),
            "members_to_create": sorted({p["member"]["name"] for p in notes.values() if p["member"]["create"]}),
            "blocking": [p["path"] for p in notes.values() if p["blocking"]],
            "nonstandard_visit_types": sorted({p["nonstandard_visit_type"] for p in notes.values() if p["nonstandard_visit_type"]}),
        },
    }
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.table:
        print(f"계획 대상 심방일지 {len(notes)}개 (추가 동의어 {added}개)")
        print(f"{'형식':<10} {'추가':<4} {'교정':<4} {'이동':<4} {'보류':<4} {'성도':<10} 경로")
        for p in notes.values():
            c = counts(p)
            m = p["member"]
            mstat = m["name"] + ("" if m["exists"] else " (새로 만듦)" if m["create"] else " (?)")
            print(f"{p['format']:<10} {c['추가']:<4} {c['교정']:<4} {c['이동']:<4} {c['보류']:<4} {mstat:<10} {p['path']}")
        if needs_llm:
            print("\nClaude 가 읽고 매핑할 자유형 노트 (prompts/classify_freeform.md → llm_plan.json → --merge):")
            for p in needs_llm:
                print(f"  · {p}")
        for s in skipped:
            print(f"  (건너뜀) {s}")
        for m in msgs:
            print(f"  (병합) {m}")
        if plan["summary"]["nonstandard_visit_types"]:
            print(f"\n플러그인 설정 '심방 유형' 에 추가할 값: {', '.join(plan['summary']['nonstandard_visit_types'])}")
        print(f"\n저장: {out}")
    else:
        print(json.dumps({"status": "ok", "out": str(out), "summary": plan["summary"], "needs_llm": needs_llm}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 한국어 윈도우 콘솔·파이프에서 한글·✅ 깨짐 방지
    except (AttributeError, ValueError):
        pass
    raise SystemExit(main(sys.argv[1:]))
