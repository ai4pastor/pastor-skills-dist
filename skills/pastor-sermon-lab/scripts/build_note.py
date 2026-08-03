#!/usr/bin/env python3
"""Render one pastor-sermon-lab note (research / diagnose / enrich) from an LLM result JSON.

Default mode is dry-run. Actual writes require both:
- --write
- --approve WRITE

사용 흐름: 노트 내용을 목사님께 보여주고, 저장할 폴더를 확인받은 뒤
--folder로 넘겨 실행한다. vault 경로는 --vault 또는 memory.json에서 읽는다.

역할 분담: LLM은 내용(result JSON)을 만들고, 이 스크립트가 결정론적으로
frontmatter 구성·성경구절 추출·등급 집계·파일명·충돌 검사·쓰기를 수행한다.

결정론 보장:
- frontmatter의 검증등급 개수는 LLM 주장이 아니라 본문 이모지 실측으로 계산한다.
- '## 검증 요약' 섹션도 스크립트가 실측값으로 생성한다 (본문에 직접 쓰면 거부).
- 진단 점수는 고정 6차원 키 전부, 1~5 정수만 허용한다. 약점은 6차원 키의 부분집합만.
- 성경구절 wikilink는 extract_bible_refs가 본문에서 추출한다. LLM이 링크를 지어내지 않는다.

This script never modifies source sermon files and never overwrites existing vault notes.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import argparse
import json
import sys
from typing import Any

from config_loader import DIAGNOSIS_DIMENSIONS, LOG_DIR, default_config, load_memory
from extract_bible_refs import extract as extract_refs
from note_utils import format_frontmatter, sanitize_title

MODES = {
    "research": {"note_type": "연구노트", "pattern": "{date}_연구_{topic}"},
    "diagnose": {"note_type": "진단노트", "pattern": "{date}_진단_{title}"},
    "enrich": {"note_type": "보강노트", "pattern": "{date}_보강_{title}"},
}

GRADE_EMOJIS = {"✅": "확인됨", "🟡": "개연", "⚠️": "논쟁중", "❓": "불확실", "🚫": "사용금지"}


def count_grades(body: str) -> dict[str, int]:
    return {emoji: body.count(emoji) for emoji in GRADE_EMOJIS}


def grade_summary(counts: dict[str, int]) -> str:
    return " ".join(f"{emoji}{n}" for emoji, n in counts.items())


def validate_tags(tags: list[Any], warnings: list[str]) -> list[str]:
    out = []
    for tag in tags:
        cleaned = sanitize_title(str(tag), "")
        if not cleaned:
            continue
        if " " in cleaned:
            fixed = cleaned.replace(" ", "")
            warnings.append(f"태그 띄어쓰기 자동 결합 '{cleaned}' → '{fixed}'")
            cleaned = fixed
        out.append(cleaned)
    return list(dict.fromkeys(out))


def validate_scores(result: dict[str, Any]) -> tuple[dict[str, int], list[str], str]:
    scores_raw = result.get("scores")
    if not isinstance(scores_raw, dict):
        raise ValueError("diagnose result에는 scores 객체가 필수")
    scores: dict[str, int] = {}
    for dim in DIAGNOSIS_DIMENSIONS:
        value = scores_raw.get(dim)
        if not isinstance(value, int) or not (1 <= value <= 5):
            raise ValueError(f"scores.{dim}: 1~5 정수 필수 (현재 {value!r})")
        scores[dim] = value
    unknown = set(scores_raw) - set(DIAGNOSIS_DIMENSIONS)
    if unknown:
        raise ValueError(f"scores에 허용되지 않은 차원: {sorted(unknown)} — 6차원은 고정")
    weaknesses = [w for w in result.get("weaknesses", []) if w in DIAGNOSIS_DIMENSIONS]
    dropped = [w for w in result.get("weaknesses", []) if w not in DIAGNOSIS_DIMENSIONS]
    if dropped:
        raise ValueError(f"weaknesses에 6차원 밖 값: {dropped}")
    focus = str(result.get("focus", "")).strip()
    if focus and focus not in DIAGNOSIS_DIMENSIONS:
        raise ValueError(f"focus는 6차원 키 중 하나여야 함: '{focus}'")
    return scores, weaknesses, focus


def wikilink(name: str) -> str:
    return f"[[{name.removesuffix('.md')}]]"


def render_note(mode: str, result: dict[str, Any], config: dict[str, Any], warnings: list[str]) -> tuple[str, dict[str, Any]]:
    body = str(result.get("body", "")).rstrip()
    if not body:
        raise ValueError("result.body가 비어 있음")
    if "## 검증 요약" in body:
        raise ValueError("body에 '## 검증 요약' 섹션 금지 — 스크립트가 실측값으로 생성한다")
    now = datetime.now().isoformat(timespec="minutes")
    date = str(result.get("date", "")).strip() or datetime.now().strftime("%Y-%m-%d")
    title = sanitize_title(str(result.get("title", "")), "")
    if not title:
        raise ValueError("result.title이 비어 있음")

    refs = extract_refs(body, config)
    ok_links = list(dict.fromkeys(r["link"] for r in refs if r.get("status") == "ok"))
    ambiguous = [r for r in refs if r.get("status") != "ok"]
    counts = count_grades(body)

    fields: dict[str, object] = {
        "created": now,
        "modified": now,
        "note_type": MODES[mode]["note_type"],
        "skill": "pastor-sermon-lab",
        "title": title,
        "date": date,
    }
    if result.get("main_passage"):
        fields["main_passage"] = str(result["main_passage"]).strip()

    scores: dict[str, int] = {}
    weaknesses: list[str] = []
    if mode == "diagnose":
        scores, weaknesses, focus = validate_scores(result)
        for dim in DIAGNOSIS_DIMENSIONS:
            fields[f"점수_{dim}"] = str(scores[dim])
        fields["약점"] = weaknesses
        if focus:
            fields["집중점검"] = focus
    else:
        fields["검증상태"] = str(result.get("verification_status", "")).strip() or "미기재"

    links = result.get("links") or {}
    for key in ("설교노트", "관련연구"):
        if links.get(key):
            fields[key] = wikilink(str(links[key]))

    fields["검증등급"] = grade_summary(counts)
    tags = validate_tags(result.get("tags", []), warnings)
    if tags:
        fields["tags"] = tags
    fields[config["bible"].get("frontmatter_key", "성경구절")] = ok_links

    parts = [format_frontmatter(fields), f"# {MODES[mode]['note_type'].removesuffix('노트')}: {title}", "", body, ""]
    if ambiguous:
        parts.append("## 확인 필요한 성경구절")
        parts.extend(f"- {r.get('raw')} — {r.get('note', r.get('status'))}" for r in ambiguous)
        parts.append("")
    if mode != "diagnose":
        search_count = result.get("search_count")
        search_note = f" · 검색 {search_count}회 사용" if isinstance(search_count, int) else ""
        parts.extend(["## 검증 요약", "", f"- {grade_summary(counts)}{search_note}", ""])
    meta = {
        "grade_counts": counts,
        "bible_links": ok_links,
        "ambiguous_refs": [r.get("raw") for r in ambiguous],
        "scores": scores,
        "weaknesses": weaknesses,
    }
    return "\n".join(parts), meta


def resolve_folder(vault: Path, folder: str) -> Path:
    """vault 상대 폴더만 허용. 절대경로·상위 탈출 차단."""
    candidate = Path(folder)
    if candidate.is_absolute():
        candidate = candidate.expanduser()
        try:
            candidate.relative_to(vault)
        except ValueError:
            raise ValueError(f"저장 폴더가 vault 밖입니다: {folder}")
        return candidate
    if ".." in candidate.parts:
        raise ValueError(f"상위 폴더 탈출 금지: {folder}")
    return vault / candidate


def build_plan(mode: str, result: dict[str, Any], vault_path: str, folder: str) -> dict[str, Any]:
    vault = Path(vault_path).expanduser()
    if not vault_path or not vault.exists():
        raise FileNotFoundError(f"vault not found: {vault_path or '(미설정)'} — 목사님께 vault 위치를 여쭤보세요")
    target = resolve_folder(vault, folder)
    config = default_config()

    warnings: list[str] = []
    content, meta = render_note(mode, result, config, warnings)
    date = str(result.get("date", "")).strip() or datetime.now().strftime("%Y-%m-%d")
    values = {
        "date": date,
        "title": sanitize_title(str(result.get("title", ""))),
        "topic": sanitize_title(str(result.get("topic", result.get("title", "")))),
    }
    name = sanitize_title(MODES[mode]["pattern"].format(**values)) + ".md"
    note_path = target / name

    warnings.extend(f"ambiguous bible ref: {raw}" for raw in meta["ambiguous_refs"])
    return {
        "created": datetime.now().isoformat(timespec="minutes"),
        "mode": mode,
        "vault": str(vault),
        "note": {"path": str(note_path), "basename": name.removesuffix(".md"), "exists": note_path.exists(), "content": content},
        "meta": meta,
        "warnings": warnings,
    }


def summarize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    note = plan["note"]
    return {
        "created": plan["created"],
        "mode": plan["mode"],
        "planned_file": note["path"],
        "conflict": note["exists"],
        "grade_counts": plan["meta"]["grade_counts"],
        "bible_links": len(plan["meta"]["bible_links"]),
        "scores": plan["meta"]["scores"],
        "weaknesses": plan["meta"]["weaknesses"],
        "warnings": plan["warnings"],
    }


def write_plan(plan: dict[str, Any]) -> Path:
    note = plan["note"]
    note_path = Path(note["path"])
    if note_path.exists():
        raise FileExistsError(f"existing note blocks write: {note_path}")
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(note["content"], encoding="utf-8")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created": datetime.now().isoformat(timespec="minutes"),
        "mode": plan["mode"],
        "vault": plan["vault"],
        "written": [str(note_path)],
        "skipped": [],
        "summary": summarize_plan(plan),
    }
    manifest_path = LOG_DIR / f"lab-manifest-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=sorted(MODES))
    parser.add_argument("--result", required=True, help="LLM 결과 JSON 경로 (~/.pastor-sermon-lab/work/<mode>.json)")
    parser.add_argument("--folder", required=True, help="저장할 vault 내 폴더 (목사님께 확인받은 값)")
    parser.add_argument("--vault", help="vault 경로 (생략 시 memory.json)")
    parser.add_argument("--memory", help="memory.json 경로 (테스트용)")
    parser.add_argument("--write", action="store_true", help="write file; default is dry-run only")
    parser.add_argument("--approve", default="", help="must be WRITE for --write")
    parser.add_argument("--full", action="store_true", help="include generated content in dry-run JSON")
    args = parser.parse_args(argv[1:])

    vault = args.vault or load_memory(args.memory)["vault"]
    result = json.loads(Path(args.result).expanduser().read_text(encoding="utf-8"))
    plan = build_plan(args.mode, result, vault, args.folder)
    summary = summarize_plan(plan)
    if args.write:
        if args.approve != "WRITE":
            print(json.dumps({"status": "blocked", "reason": "--write requires --approve WRITE", "summary": summary}, ensure_ascii=False, indent=2))
            return 2
        try:
            manifest = write_plan(plan)
        except FileExistsError as exc:
            print(json.dumps({"status": "blocked", "reason": str(exc), "summary": summary}, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps({"status": "written", "manifest": str(manifest), "summary": summary}, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(plan if args.full else {"status": "dry-run", "summary": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
