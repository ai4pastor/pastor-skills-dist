#!/usr/bin/env python3
"""Verify pastor-sermon-lab output manifest.

Checks:
- written files exist, no duplicates, stay inside the configured vault
- file names avoid Obsidian-forbidden characters
- note_type frontmatter is one of 연구노트/진단노트/보강노트
- frontmatter 검증등급 counts match a recount of the note body
  (frontmatter·'## 검증 요약' 섹션 제외 후 실측)
- diagnose notes: 점수_{6차원} 전부 존재·1~5, 약점 값이 6차원 안
- tags contain no whitespace
- vault 경로는 manifest에 기록된 값을 쓴다 (별도 설정 파일 불필요)

frontmatter는 YAML 파서 대신 정규식으로 읽는다 — 표준 파서는 "[[...]]" 값을 훼손할 수 있다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import sys

from config_loader import DIAGNOSIS_DIMENSIONS
from note_utils import FORBIDDEN_FILENAME_CHARS

FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?)\n---(?:\n|\Z)", re.DOTALL)
NOTE_TYPES = {"연구노트", "진단노트", "보강노트"}
GRADE_EMOJIS = ("✅", "🟡", "⚠️", "❓", "🚫")


def parse_frontmatter_lists(text: str) -> dict[str, list[str]]:
    """Regex-based frontmatter reader: returns every key as a list of string values."""
    m = FRONTMATTER_RE.match(text)
    fields: dict[str, list[str]] = {}
    if not m:
        return fields
    current: str | None = None
    for line in m.group("body").splitlines():
        if not line.strip() or line.strip() == "[]":
            continue
        if not line.startswith((" ", "\t")):
            kv = re.match(r"^(?P<key>[^:]+):\s*(?P<value>.*)$", line)
            if not kv:
                current = None
                continue
            key = kv.group("key").strip()
            value = kv.group("value").strip()
            if value:
                fields[key] = [value.strip('"')]
                current = None
            else:
                fields[key] = []
                current = key
        elif current:
            item = re.match(r"^\s+-\s+(?P<value>.*)$", line)
            if item:
                fields[current].append(item.group("value").strip().strip('"'))
    return fields


def body_without_summary(text: str) -> str:
    """frontmatter와 '## 검증 요약' 섹션을 제외한 본문 (등급 재실측 대상)."""
    m = FRONTMATTER_RE.match(text)
    body = text[m.end():] if m else text
    lines = []
    skipping = False
    for line in body.splitlines():
        if line.startswith("## "):
            skipping = "검증 요약" in line
        if not skipping:
            lines.append(line)
    return "\n".join(lines)


def recount_grades(text: str) -> str:
    body = body_without_summary(text)
    return " ".join(f"{e}{body.count(e)}" for e in GRADE_EMOJIS)


def check_note(path: Path, issues: list[str]) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    fields = parse_frontmatter_lists(text)
    note_type = (fields.get("note_type") or [""])[0]
    if note_type not in NOTE_TYPES:
        issues.append(f"note_type 누락/비정상 '{note_type}': {path}")
        return
    declared = (fields.get("검증등급") or [""])[0]
    if declared:
        actual = recount_grades(text)
        if declared != actual:
            issues.append(f"검증등급 불일치 (선언 '{declared}' vs 실측 '{actual}'): {path}")
    if note_type == "진단노트":
        for dim in DIAGNOSIS_DIMENSIONS:
            raw = (fields.get(f"점수_{dim}") or [""])[0]
            if not raw.isdigit() or not (1 <= int(raw) <= 5):
                issues.append(f"점수_{dim} 누락/범위 밖 '{raw}': {path}")
        for weakness in fields.get("약점", []):
            if weakness not in DIAGNOSIS_DIMENSIONS:
                issues.append(f"약점에 6차원 밖 값 '{weakness}': {path}")
    for tag in fields.get("tags", []):
        if re.search(r"\s", tag):
            issues.append(f"태그에 띄어쓰기 '{tag}': {path}")


def verify_manifest(manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    vault_raw = str(manifest.get("vault", ""))
    if not vault_raw:
        return {"status": "blocked", "manifest": str(manifest_path), "files_checked": 0,
                "issues": ["manifest에 vault 경로가 없음"]}
    vault = Path(vault_raw).expanduser().resolve()
    issues: list[str] = []
    seen: set[str] = set()
    for raw_path in manifest.get("written", []):
        if raw_path in seen:
            issues.append(f"duplicate written path in manifest: {raw_path}")
        seen.add(raw_path)
    written = [Path(p) for p in manifest.get("written", [])]
    for path in written:
        if not path.resolve().is_relative_to(vault):
            issues.append(f"vault 밖 경로가 생성됨: {path}")
        if not path.exists():
            issues.append(f"missing file: {path}")
            continue
        bad = [ch for ch in path.name if ch in FORBIDDEN_FILENAME_CHARS]
        if bad:
            issues.append(f"forbidden filename chars {bad}: {path}")
        if path.suffix == ".md":
            check_note(path, issues)
    return {
        "status": "ok" if not issues else "blocked",
        "manifest": str(manifest_path),
        "files_checked": len(written),
        "issues": issues,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    args = parser.parse_args(argv[1:])
    result = verify_manifest(Path(args.manifest).expanduser())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
