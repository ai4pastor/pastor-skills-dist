#!/usr/bin/env python3
"""3·4단계 — 계획(plan.json)을 노트에 적용한다. 기본은 dry-run(diff 미리보기), 쓰기는 이중 게이트.

    python3 scripts/apply_plan.py --plan <work>/plan.json                      # dry-run: 노트별 diff + [추가]/[교정]/[이동]/[보류]
    python3 scripts/apply_plan.py --plan <work>/plan.json --write --approve WRITE
    python3 scripts/apply_plan.py --plan <work>/plan.json --restore <백업 시각> --approve WRITE   # 되돌리기

비파괴 어설션 (하나라도 어긋나면 그 노트는 blocked — 쓰지 않는다):
  ① 원본의 빈 줄 아닌 비헤딩 줄은 결과에 전부 그대로 있다(이동 허용, 유실·수정 불가)
  ② 헤딩은 원문 그대로 남거나 계획의 heading_fixes 에 적힌 것만 바뀐다
  ③ 프론트매터 기존 줄은 순서째 그대로이고 새 키만 뒤에 붙는다
  ④ 계획의 sha1 과 파일이 다르면(계획 뒤에 편집됨) 거부
쓰기 전 원본은 <설정 홈>/visit-import/backups/<시각>/ 에 그대로 복사한다 (볼트 밖).
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
import argparse
import difflib
import json
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from visit_env import backups_dir, work_dir  # noqa: E402
from visit_lib import (  # noqa: E402
    H2_RE, H3_RE, atomic_write, find_section_range, fm_has, nfc, read_text, sha1_of,
    split_frontmatter,
)

HEADING_RE = re.compile(r"^#{1,6}\s+\S")


class Blocked(Exception):
    pass


def body_multiset(text: str) -> Counter:
    _, body, _ = split_frontmatter(text)
    return Counter(l for l in body if l.strip() and not HEADING_RE.match(l))


def transform(text: str, note: dict) -> tuple[str, dict]:
    if sha1_of(text) != note["sha1"]:
        raise Blocked("계획을 세운 뒤 파일이 바뀌었습니다 — audit 부터 다시")
    lines = text.split("\n")
    fm, body, has_fm = split_frontmatter(text)
    counts = {"추가": 0, "교정": 0, "이동": 0, "보류": len(note.get("hold", []))}

    # ② 헤딩 교정 (절대 줄 번호)
    for fx in note.get("heading_fixes", []):
        ln = fx["line"]
        if ln < 0 or ln >= len(lines) or lines[ln] != fx["from"]:
            raise Blocked(f"{ln + 1}행이 계획과 다릅니다: {fx['from']!r}")
        lines[ln] = fx["to"]
        counts["교정"] += 1

    # 새 섹션 — 문서 끝에
    for heading in note.get("new_sections", []):
        if find_section_range(lines, heading):
            continue
        while lines and lines[-1].strip() == "":
            lines.pop()
        lines += ["", heading, ""]
        counts["추가"] += 1

    # ① 이동 — 블록을 떼어 대상 섹션 끝에 붙인다 (원문 그대로)
    moves = sorted(note.get("moves", []), key=lambda m: m["lines"][0])
    blocks = []
    for mv in moves:
        a, b = mv["lines"]
        if not (0 <= a <= b < len(lines)) or lines[a].strip() != str(mv.get("first_text", "")).strip():
            raise Blocked(f"이동 범위 {a + 1}-{b + 1}행이 계획과 다릅니다")
        blocks.append((a, b, mv["to"], lines[a:b + 1]))
    for a, b, _, _ in sorted(blocks, key=lambda x: x[0], reverse=True):
        del lines[a:b + 1]
    for _, _, target, block in blocks:
        rng = find_section_range(lines, target)
        if not rng:
            raise Blocked(f"이동 대상 섹션이 없습니다: {target}")
        insert_at = rng[1]
        while insert_at > rng[0] + 1 and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        lines[insert_at:insert_at] = block
        counts["이동"] += 1

    # ③ 프론트매터 — 새 키만 닫는 --- 앞에
    adds = note.get("frontmatter_add", {})
    if adds:
        new_fm_lines = [f"{k}: {v}" for k, v in adds.items() if not fm_has(fm, k)]
        counts["추가"] += len(new_fm_lines)
        if has_fm:
            close = 1 + len(fm)
            if lines[close].strip() != "---":
                raise Blocked("프론트매터 닫는 줄을 찾지 못했습니다")
            lines[close:close] = new_fm_lines
        elif new_fm_lines:
            lines[0:0] = ["---", *new_fm_lines, "---", ""]

    new_text = "\n".join(lines)

    # 어설션
    before, after = body_multiset(text), body_multiset(new_text)
    if before != after:
        lost = list((before - after).elements())[:3]
        extra = list((after - before).elements())[:3]
        raise Blocked(f"본문 줄 보존 실패 — 사라짐 {lost} / 생김 {extra}")
    fixed_from = {fx["from"] for fx in note.get("heading_fixes", [])}
    old_headings = [l for l in text.split("\n") if HEADING_RE.match(l)]
    new_heading_set = set(l for l in new_text.split("\n") if HEADING_RE.match(l))
    for h in old_headings:
        if h not in new_heading_set and h not in fixed_from:
            raise Blocked(f"헤딩이 사라졌습니다: {h}")
    fm2, _, _ = split_frontmatter(new_text)
    if fm2[:len(fm)] != fm:
        raise Blocked("프론트매터 기존 줄이 바뀌었습니다")
    return new_text, counts


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--only", action="append", default=[], help="이 경로(부분 일치)만")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--approve", default="")
    ap.add_argument("--restore", default="", help="백업 시각 폴더명 — 그 백업으로 되돌린다")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet-diff", action="store_true", help="diff 본문 생략(요약만)")
    args = ap.parse_args(argv)

    plan = json.loads(read_text(Path(args.plan).expanduser()))
    vault = Path(plan["vault"])

    if args.restore:
        if args.approve != "WRITE":
            print(json.dumps({"status": "blocked", "reason": "--restore 는 --approve WRITE 와 함께만"}, ensure_ascii=False))
            return 2
        src = backups_dir() / args.restore
        if not src.is_dir():
            print(json.dumps({"status": "error", "reason": f"백업 폴더 없음: {src}"}, ensure_ascii=False))
            return 1
        restored = []
        for p in sorted(src.rglob("*.md")):
            rel = p.relative_to(src)
            dest = vault / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(dest, read_text(p))
            restored.append(rel.as_posix())
        print(json.dumps({"status": "restored", "count": len(restored), "files": restored}, ensure_ascii=False, indent=2))
        return 0

    if args.write and args.approve != "WRITE":
        print(json.dumps({"status": "blocked", "reason": "--write 는 --approve WRITE 와 함께만 실행 가능"}, ensure_ascii=False))
        return 2

    results = []
    total = Counter()
    for note in plan["notes"]:
        if args.only and not any(nfc(o) in nfc(note["path"]) for o in args.only):
            continue
        full = vault / note["path"]
        entry = {"path": note["path"], "status": "", "counts": {}, "reason": "", "hold": note.get("hold", [])}
        if note.get("blocking"):
            entry["status"] = "hold"
            entry["reason"] = "; ".join(note.get("hold", []))
            results.append(entry)
            total["보류"] += 1
            continue
        try:
            text = read_text(full)
            new_text, counts = transform(text, note)
        except Blocked as e:
            entry["status"] = "blocked"
            entry["reason"] = str(e)
            results.append(entry)
            total["blocked"] += 1
            continue
        entry["counts"] = counts
        if new_text == text:
            entry["status"] = "unchanged"
            results.append(entry)
            total["unchanged"] += 1
            continue
        entry["status"] = "planned"
        entry["diff"] = "".join(difflib.unified_diff(
            text.splitlines(keepends=True), new_text.splitlines(keepends=True),
            fromfile=note["path"], tofile=note["path"] + " (적용 후)", n=2))
        entry["_new"] = new_text
        results.append(entry)
        for k, v in counts.items():
            total[k] += v
        total["changed"] += 1

    backup_root = None
    written = []
    if args.write:
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
        backup_root = backups_dir() / stamp
        for e in results:
            if e["status"] != "planned":
                continue
            full = vault / e["path"]
            dest = backup_root / e["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(full, dest)
            atomic_write(full, e["_new"])
            e["status"] = "written"
            written.append(e["path"])
        manifest = {"status": "written", "plan": str(args.plan), "backup_dir": str(backup_root),
                    "written": written, "blocked": [e["path"] for e in results if e["status"] == "blocked"],
                    "hold": [e["path"] for e in results if e["status"] == "hold"]}
        work_dir().mkdir(parents=True, exist_ok=True)
        (work_dir() / f"apply_{stamp}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    for e in results:
        e.pop("_new", None)
    if args.json:
        print(json.dumps({"status": "written" if args.write else "dry-run", "backup_dir": str(backup_root) if backup_root else "",
                          "totals": dict(total), "results": results}, ensure_ascii=False, indent=2))
        return 0

    mode = "적용 결과" if args.write else "미리보기 (dry-run — 아직 아무것도 바뀌지 않았습니다)"
    print(f"=== {mode} ===")
    for e in results:
        c = e.get("counts") or {}
        tag = {"planned": "변경 예정", "written": "적용됨", "unchanged": "변경 없음", "blocked": "⛔ 차단", "hold": "⏸ 보류"}[e["status"]]
        summary = f"[추가 {c.get('추가', 0)}] [교정 {c.get('교정', 0)}] [이동 {c.get('이동', 0)}] [보류 {c.get('보류', 0)}]" if c else ""
        print(f"\n{tag}  {e['path']}  {summary}")
        if e["reason"]:
            print(f"   사유: {e['reason']}")
        for h in e.get("hold", []):
            print(f"   보류: {h}")
        if e.get("diff") and not args.quiet_diff:
            print(e["diff"].rstrip())
    print(f"\n노트 {len(results)}개 — 변경 {total['changed']} · 변경 없음 {total['unchanged']} · 차단 {total['blocked']} · 보류 {total['보류']}")
    print(f"항목 — 추가 {total['추가']} · 교정 {total['교정']} · 이동 {total['이동']}")
    if args.write:
        print(f"백업: {backup_root}   (되돌리기: --restore {backup_root.name} --approve WRITE)")
    else:
        print("적용하려면: --write --approve WRITE")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 한국어 윈도우 콘솔·파이프에서 한글·✅ 깨짐 방지
    except (AttributeError, ValueError):
        pass
    raise SystemExit(main(sys.argv[1:]))
