#!/usr/bin/env python3
"""Claims ledger gate for pastor-sermon-lab.

주장 원장(claims.json)의 등급이 증거 수준과 정합한지 결정론적으로 검사한다.
LLM이 "확인했다"고 말하는 것만으로는 ✅가 불가능한 구조를 만든다.

claims.json 스키마:
{
  "mode": "research|enrich|diagnose",
  "web_available": true,
  "searches_used": 3,
  "claims": [
    {
      "id": "C1",
      "text": "주장 문장",
      "type": "T1|T2|T3|T4|T5|기타",
      "load_bearing": true,
      "grade": "확인됨|개연|논쟁중|불확실|사용금지",
      "source": "script|web|trained|inference",
      "evidence": [{"url": "...", "domain": "...", "agrees": true}],
      "both_sides": "논쟁중일 때 양 진영 요약"
    }
  ]
}

--plan: 검증해야 할 claim을 예산 안에서 우선순위순으로 뽑아준다 (검색 전 사용).
기본: 등급-증거 정합 게이트 (검색 후·노트 작성 전 사용). 실패 시 exit 1.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
import argparse
import json
import sys
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

GRADES = {"확인됨", "개연", "논쟁중", "불확실", "사용금지"}
SOURCES = {"script", "web", "trained", "inference"}
ALWAYS_VERIFY = {"T1", "T2", "T4"}          # 유물·학자 인용·직접 인용문: 항상 검증
LOAD_BEARING_VERIFY = {"T3", "T5"}          # 통계·연대: 핵심 논지일 때 검증
IDENTIFIER_TYPES = {"T1", "T2", "T4"}       # 존재 확인 실패 시 🚫 대상 (구체 식별자)


def load_domains() -> dict[str, Any]:
    return json.loads((DATA_DIR / "institutional_domains.json").read_text(encoding="utf-8"))


def domain_of(entry: dict[str, Any]) -> str:
    domain = str(entry.get("domain", "")).strip().lower()
    if not domain and entry.get("url"):
        domain = (urlparse(str(entry["url"])).hostname or "").lower()
    return domain.removeprefix("www.")


def is_institutional(domain: str, table: dict[str, Any]) -> bool:
    if any(domain == d or domain.endswith("." + d) for d in table.get("domains", [])):
        return True
    return any(domain.endswith(suffix) for suffix in table.get("suffixes", []))


def is_wiki(domain: str, table: dict[str, Any]) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in table.get("wiki_domains", []))


def needs_verification(claim: dict[str, Any]) -> bool:
    ctype = str(claim.get("type", "기타"))
    if ctype in ALWAYS_VERIFY:
        return True
    return ctype in LOAD_BEARING_VERIFY and bool(claim.get("load_bearing"))


def check_claim(claim: dict[str, Any], web_available: bool, table: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    cid = str(claim.get("id", "?"))
    grade = str(claim.get("grade", ""))
    source = str(claim.get("source", ""))
    ctype = str(claim.get("type", "기타"))
    if grade not in GRADES:
        return [f"{cid}: grade는 {sorted(GRADES)} 중 하나여야 함 ('{grade}')"]
    if source not in SOURCES:
        return [f"{cid}: source는 {sorted(SOURCES)} 중 하나여야 함 ('{source}')"]

    evidence = claim.get("evidence") or []
    agreeing = [e for e in evidence if e.get("agrees") is True]
    refuting = [e for e in evidence if e.get("agrees") is False]
    agreeing_domains = {domain_of(e) for e in agreeing if domain_of(e)}
    non_wiki_domains = {d for d in agreeing_domains if not is_wiki(d, table)}
    institutional = [d for d in non_wiki_domains if is_institutional(d, table)]

    if grade == "확인됨" and source != "script":
        if len(non_wiki_domains) < 2:
            issues.append(f"{cid}: ✅확인됨은 서로 다른 비위키 도메인 2개 이상 필요 (현재 {sorted(non_wiki_domains)})")
        if not institutional:
            issues.append(f"{cid}: ✅확인됨은 기관 도메인 1개 이상 필요 (현재 {sorted(non_wiki_domains)})")
    if refuting and not agreeing and grade != "사용금지":
        issues.append(f"{cid}: 반박 출처만 존재 — 🚫사용금지여야 함")
    if claim.get("both_sides", "") == "" and grade == "논쟁중":
        issues.append(f"{cid}: ⚠️논쟁중은 both_sides(양 진영 요약) 필수")
    if needs_verification(claim) and not evidence:
        if not web_available:
            if grade == "확인됨" and source != "script":
                issues.append(f"{cid}: 오프라인에서는 ✅ 불가 — 🟡 상한")
        elif grade in ("확인됨", "개연"):
            hint = "🚫(구체 식별자)" if ctype in IDENTIFIER_TYPES else "❓"
            issues.append(f"{cid}: 검증 대상({ctype})인데 evidence 없음 — 검색하거나 {hint}로 강등")
    return issues


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("claims", help="claims.json 경로")
    parser.add_argument("--plan", action="store_true", help="검증해야 할 claim 목록만 출력 (검색 전)")
    args = parser.parse_args(argv[1:])

    data = json.loads(Path(args.claims).expanduser().read_text(encoding="utf-8"))
    claims = data.get("claims", [])
    mode = str(data.get("mode", "research"))
    web_available = bool(data.get("web_available", True))
    table = load_domains()

    from config_loader import SEARCH_BUDGET
    budget = SEARCH_BUDGET.get(mode)

    if args.plan:
        todo = [c for c in claims if needs_verification(c) and not c.get("evidence")]
        todo.sort(key=lambda c: (not c.get("load_bearing"), str(c.get("id"))))
        if budget is not None:
            todo = todo[:budget]
        print(json.dumps({
            "status": "plan",
            "mode": mode,
            "budget": budget,
            "to_verify": [{"id": c.get("id"), "type": c.get("type"), "text": c.get("text")} for c in todo],
            "skipped_over_budget": max(0, len([c for c in claims if needs_verification(c) and not c.get("evidence")]) - len(todo)),
        }, ensure_ascii=False, indent=2))
        return 0

    issues: list[str] = []
    seen_ids: set[str] = set()
    for claim in claims:
        cid = str(claim.get("id", ""))
        if cid in seen_ids:
            issues.append(f"claim id 중복: {cid}")
        seen_ids.add(cid)
        issues.extend(check_claim(claim, web_available, table))
    searches_used = data.get("searches_used", 0)
    if budget is not None and isinstance(searches_used, int) and searches_used > budget:
        issues.append(f"검색 {searches_used}회 사용 — 예산 {budget}회 초과")

    result = {
        "status": "ok" if not issues else "blocked",
        "mode": mode,
        "claims_checked": len(claims),
        "issues": issues,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
