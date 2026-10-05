#!/usr/bin/env python3
"""6단계 — 변환 결과 검증 + 플러그인 설정값 출력. 읽기 전용.

    python3 scripts/verify_visits.py --vault "<볼트>" --member-folder "성도" --visit-folder "심방"

검사: 일지마다 7개 헤딩 커버리지(n/7)·임베드 앵커 3종 존재·성도 링크 해석·날짜 형식·반영 여부와 성도 노트 링크 일치·
비표준 심방유형. 성도 노트는 type·두 섹션 유무. 끝에 플러그인 설정(성도 노트 폴더 / 심방일지 폴더)에 넣을 값을 그대로 보여 준다.
심각 문제(성도 미해석·날짜 오류·앵커 섹션 없음·반영 표시인데 링크 없음)가 있으면 종료코드 1.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from visit_lib import (  # noqa: E402
    ANCHOR_KEYS, MEMBER_EMBEDS, MEMBER_VISIT_LOG, NOTE_TYPE_MEMBER, NOTE_TYPE_VISIT, SECTION_ORDER, VISIT_SECTIONS,
    VISIT_TYPES, find_section_range, fm_get, iter_md, nfc, read_text, split_frontmatter, visit_basename,
    wikilink_target,
)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", required=True)
    ap.add_argument("--member-folder", required=True)
    ap.add_argument("--visit-folder", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    vault = Path(args.vault).expanduser().resolve()
    mroot, vroot = vault / args.member_folder, vault / args.visit_folder

    members = {}
    for p in iter_md(mroot) if mroot.is_dir() else []:
        text = read_text(p)
        fm, _, _ = split_frontmatter(text)
        if fm_get(fm, "type") != NOTE_TYPE_MEMBER:
            continue
        lines = text.split("\n")
        members[nfc(p.stem)] = {
            "path": p, "text": text,
            "has_log": bool(find_section_range(lines, MEMBER_VISIT_LOG)),
            "has_embeds": bool(find_section_range(lines, MEMBER_EMBEDS)),
        }

    rows, hard, soft, nonstandard = [], [], [], set()
    n_visit_type_notes = 0
    for p in iter_md(vroot) if vroot.is_dir() else []:
        text = read_text(p)
        fm, _, _ = split_frontmatter(text)
        if fm_get(fm, "type") != NOTE_TYPE_VISIT:
            continue
        n_visit_type_notes += 1
        rel = nfc(p.relative_to(vault).as_posix())
        lines = text.split("\n")
        covered = [k for k in SECTION_ORDER if find_section_range(lines, VISIT_SECTIONS[k])]
        missing_anchor = [VISIT_SECTIONS[k] for k in ANCHOR_KEYS if k not in covered]
        name = wikilink_target(fm_get(fm, "성도"))
        d = fm_get(fm, "날짜") or ""
        vt = fm_get(fm, "심방유형") or ""
        synced = bool(fm_get(fm, "반영"))
        problems = []
        if not name:
            problems.append("성도 링크 없음"); hard.append(f"{rel}: 성도 링크 없음")
        elif name not in members:
            problems.append(f"성도 노트 없음({name})"); hard.append(f"{rel}: 성도 노트 없음 {name}")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            problems.append(f"날짜 형식({d!r})"); hard.append(f"{rel}: 날짜 형식 오류 {d!r}")
        if missing_anchor:
            problems.append("앵커 섹션 없음 " + ",".join(missing_anchor)); hard.append(f"{rel}: 앵커 섹션 없음 {missing_anchor}")
        if vt and vt not in VISIT_TYPES:
            nonstandard.add(vt)
        if name in members:
            linked = f"[[{nfc(p.stem)}" in members[name]["text"]
            if synced and not linked:
                problems.append("반영 표시인데 성도 노트에 링크 없음"); hard.append(f"{rel}: 반영: true 인데 {name}.md 에 링크 없음")
            if not synced and not linked:
                soft.append(f"{rel}: 아직 성도 노트에 반영되지 않음 (backfill 또는 플러그인 '반영')")
        expected = visit_basename(d, name or "")
        if expected and expected != nfc(p.stem):
            soft.append(f"{rel}: 파일명이 플러그인 규칙({expected}.md)과 다름 — 동작에는 지장 없음")
        rows.append({"path": rel, "coverage": f"{len(covered)}/7", "name": name or "", "date": d, "type": vt, "synced": synced, "problems": problems})

    members_wo_sections = [n for n, m in members.items() if not (m["has_log"] and m["has_embeds"])]
    report = {
        "status": "ok" if not hard else "problems",
        "vault": str(vault),
        "member_folder": args.member_folder, "visit_folder": args.visit_folder,
        "members": len(members), "visits": n_visit_type_notes,
        "coverage_full": sum(1 for r in rows if r["coverage"] == "7/7"),
        "hard": hard, "soft": soft, "nonstandard_visit_types": sorted(nonstandard),
        "members_without_sections": members_wo_sections, "rows": rows,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not hard else 1

    print(f"=== 검증 — 성도 노트 {len(members)}개 · 심방일지 {n_visit_type_notes}개 ===")
    print(f"{'커버':<5} {'반영':<4} {'성도':<8} {'날짜':<11} {'유형':<8} 경로")
    for r in rows:
        print(f"{r['coverage']:<5} {'✓' if r['synced'] else '·':<4} {r['name']:<8} {r['date']:<11} {r['type']:<8} {r['path']}" + (f"  ⚠ {'; '.join(r['problems'])}" if r["problems"] else ""))
    print(f"\n7개 헤딩 모두 있는 일지 {report['coverage_full']}/{len(rows)} (플러그인은 📝 대화내용·🙏 기도제목·💡 후속조치 3개만 있어도 동작)")
    if members_wo_sections:
        print(f"심방 기록·임베드 섹션이 아직 없는 성도 노트 {len(members_wo_sections)}개 — 첫 '반영' 때 플러그인이 끝에 만듭니다: {', '.join(members_wo_sections[:8])}{' …' if len(members_wo_sections) > 8 else ''}")
    if hard:
        print(f"\n⛔ 고쳐야 할 것 {len(hard)}건")
        for h in hard:
            print(f"  - {h}")
    if soft:
        print(f"\n참고 {len(soft)}건")
        for s in soft[:12]:
            print(f"  - {s}")
        if len(soft) > 12:
            print(f"  … 외 {len(soft) - 12}건")
    print("\n플러그인 설정(a4p-pastoral-visit → 폴더 경로)에 붙여넣을 값")
    print(f"  성도 노트 폴더: {args.member_folder}")
    print(f"  심방일지 폴더: {args.visit_folder}")
    if nonstandard:
        print(f"  심방 유형 목록에 추가: {', '.join(sorted(nonstandard))}")
    print("설정에서 [검증] 을 누르고, 왼쪽 리본의 심방 아이콘으로 대시보드를 여십시오.")
    return 0 if not hard else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 한국어 윈도우 콘솔·파이프에서 한글·✅ 깨짐 방지
    except (AttributeError, ValueError):
        pass
    raise SystemExit(main(sys.argv[1:]))
