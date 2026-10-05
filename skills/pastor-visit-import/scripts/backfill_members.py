#!/usr/bin/env python3
"""5단계 — 성도 노트 소급 반영. 심방일지마다 성도 노트에 `심방 기록` 줄과 임베드 블록을 붙이고 일지에 `반영: true` 를 적는다.

    python3 scripts/backfill_members.py --vault "<볼트>" --member-folder "성도" --visit-folder "심방" [--create-missing]
    python3 scripts/backfill_members.py ... --write --approve WRITE

- 플러그인의 planSync 와 글자 단위로 같은 줄을 쓴다(visit_lib.plan_sync). 이미 링크가 있으면 건너뛴다(멱등).
- 성도 노트가 없으면 --create-missing 일 때만 최소 노트를 만든다(type·이름·심방상태: 완료 + 두 섹션). 기존 성도 노트는 끝에 섹션만 추가된다.
- 기존 줄은 어떤 경우에도 고치지 않는다. 쓰기 전 원본은 <설정 홈>/visit-import/backups/<시각>/ 에 복사.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import argparse
import json
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from visit_env import backups_dir, work_dir  # noqa: E402
from visit_lib import (  # noqa: E402
    MEMBER_EMBEDS, MEMBER_VISIT_LOG, NOTE_TYPE_MEMBER, NOTE_TYPE_VISIT, PLACEHOLDER_EMBED, PLACEHOLDER_LOG,
    atomic_write, extract_summary, fm_get, fm_has, iter_md, join_note, nfc, plan_sync, read_text,
    resolve_anchors, split_frontmatter, wikilink_target, yaml_scalar,
)


def member_skeleton(name: str) -> str:
    fm = ["---", f"created: {date.today().isoformat()}", f"type: {NOTE_TYPE_MEMBER}", f"이름: {yaml_scalar(name)}",
          "심방상태: 완료", "created_via: pastor-visit-import", "---"]
    body = ["", f"# {name}", "", MEMBER_VISIT_LOG, "", PLACEHOLDER_LOG, "", MEMBER_EMBEDS, "", PLACEHOLDER_EMBED, ""]
    return "\n".join(fm + body)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", required=True)
    ap.add_argument("--member-folder", required=True)
    ap.add_argument("--visit-folder", required=True)
    ap.add_argument("--create-missing", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--approve", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.write and args.approve != "WRITE":
        print(json.dumps({"status": "blocked", "reason": "--write 는 --approve WRITE 와 함께만 실행 가능"}, ensure_ascii=False))
        return 2
    vault = Path(args.vault).expanduser().resolve()
    mroot = vault / args.member_folder
    vroot = vault / args.visit_folder
    for r in (mroot, vroot):
        if not r.is_dir():
            print(json.dumps({"status": "error", "reason": f"폴더 없음: {r}"}, ensure_ascii=False))
            return 1

    members: dict[str, Path] = {nfc(p.stem): p for p in iter_md(mroot)}
    contents: dict[str, str] = {}
    created: dict[str, Path] = {}
    visits = []
    skipped = []
    for p in iter_md(vroot):
        text = read_text(p)
        fm, _, _ = split_frontmatter(text)
        if fm_get(fm, "type") != NOTE_TYPE_VISIT:
            continue
        name = wikilink_target(fm_get(fm, "성도"))
        d = fm_get(fm, "날짜") or ""
        if not name:
            skipped.append((p, "성도 링크 없음"))
            continue
        if len(d) != 10 or d[4] != "-" or d[7] != "-":
            skipped.append((p, f"날짜 형식 오류: {d!r}"))
            continue
        visits.append({"path": p, "text": text, "fm": fm, "name": name, "date": d,
                       "type": fm_get(fm, "심방유형") or "심방", "basename": nfc(p.stem), "synced": bool(fm_get(fm, "반영"))})
    visits.sort(key=lambda v: (v["date"], v["basename"]))

    actions = []
    for v in visits:
        name = v["name"]
        mpath = members.get(name)
        if mpath is None:
            if not args.create_missing:
                actions.append({"visit": v, "status": "hold", "reason": f"성도 노트 없음: {name} (--create-missing 로 생성 가능)"})
                continue
            mpath = mroot / f"{name}.md"
            members[name] = mpath
            created[name] = mpath
            contents[name] = member_skeleton(name)
        if name not in contents:
            contents[name] = read_text(mpath)
        summary = extract_summary(v["text"], v["type"], v["date"])
        anchors = resolve_anchors(v["text"])
        plan = plan_sync(contents[name], v["basename"], v["date"], v["type"], summary, anchors)
        flag_needed = not v["synced"]
        if plan["nothing_to_do"] and not flag_needed:
            actions.append({"visit": v, "status": "unchanged", "member": mpath})
            continue
        if not plan["nothing_to_do"]:
            contents[name] = plan["content"]
        actions.append({"visit": v, "status": "planned", "member": mpath, "member_new": name in created,
                        "log_line": plan["log_line"] if not plan["nothing_to_do"] else "", "embed": plan["embed_block"] if not plan["nothing_to_do"] else [],
                        "warnings": plan["warnings"], "flag": flag_needed})

    touched_members = {a["member"] for a in actions if a["status"] == "planned" and a.get("log_line")}
    touched_members |= {members[n] for n in created}
    backup_root = None
    if args.write:
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
        backup_root = backups_dir() / stamp
        for mpath in sorted(touched_members):
            if mpath.exists():
                dest = backup_root / mpath.relative_to(vault)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(mpath, dest)
            atomic_write(mpath, contents[nfc(mpath.stem)])
        for a in actions:
            if a["status"] == "planned" and a.get("flag"):
                v = a["visit"]
                dest = backup_root / v["path"].relative_to(vault)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(v["path"], dest)
                fm, body, has_fm = split_frontmatter(v["text"])
                if not fm_has(fm, "반영"):
                    fm = fm + ["반영: true"]
                atomic_write(v["path"], join_note(fm, body, has_fm))
            if a["status"] == "planned":
                a["status"] = "written"
        work_dir().mkdir(parents=True, exist_ok=True)
        (work_dir() / f"backfill_{stamp}.json").write_text(json.dumps({
            "backup_dir": str(backup_root),
            "members_written": [str(m.relative_to(vault)) for m in sorted(touched_members)],
            "visits_flagged": [str(a["visit"]["path"].relative_to(vault)) for a in actions if a["status"] == "written" and a.get("flag")],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps({
            "status": "written" if args.write else "dry-run",
            "backup_dir": str(backup_root) if backup_root else "",
            "actions": [{"visit": str(a["visit"]["path"].relative_to(vault)), "status": a["status"], "member": str(a.get("member", "")) and str(Path(a["member"]).relative_to(vault)),
                         "member_new": a.get("member_new", False), "log_line": a.get("log_line", ""), "embed": a.get("embed", []), "flag": a.get("flag", False),
                         "warnings": a.get("warnings", []), "reason": a.get("reason", "")} for a in actions],
            "skipped": [{"path": str(p.relative_to(vault)), "reason": r} for p, r in skipped],
        }, ensure_ascii=False, indent=2))
        return 0

    print("=== 성도 노트 소급 반영 " + ("결과" if args.write else "미리보기 (dry-run)") + " ===")
    for a in actions:
        v = a["visit"]
        rel = v["path"].relative_to(vault)
        if a["status"] in ("hold",):
            print(f"\n⏸ {rel}: {a['reason']}")
            continue
        if a["status"] == "unchanged":
            print(f"\n= {rel}: 이미 반영됨")
            continue
        mrel = Path(a["member"]).relative_to(vault)
        print(f"\n{'✓' if a['status'] == 'written' else '→'} {rel} → {mrel}{' (새로 만듦)' if a.get('member_new') else ''}")
        if a.get("log_line"):
            print(f"   + {a['log_line']}")
            for line in a["embed"]:
                print(f"   + {line}")
        else:
            print("   = 성도 노트에는 이미 있음")
        if a.get("flag"):
            print("   + 일지 프론트매터 반영: true")
        for w in a.get("warnings", []):
            print(f"   ! {w}")
    for p, r in skipped:
        print(f"\n(건너뜀) {p.relative_to(vault)}: {r}")
    n_planned = sum(1 for a in actions if a["status"] in ("planned", "written"))
    print(f"\n일지 {len(visits)}건 — 반영 {'완료' if args.write else '예정'} {n_planned} · 이미 반영 {sum(1 for a in actions if a['status'] == 'unchanged')} · 보류 {sum(1 for a in actions if a['status'] == 'hold')}"
          + (f" · 새 성도 노트 {len(created)}" if created else ""))
    if args.write:
        print(f"백업: {backup_root}")
    else:
        print("적용하려면: --write --approve WRITE")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 한국어 윈도우 콘솔·파이프에서 한글·✅ 깨짐 방지
    except (AttributeError, ValueError):
        pass
    raise SystemExit(main(sys.argv[1:]))
