#!/usr/bin/env python3
"""Verify pastor-sermon-import output manifest.

Checks:
- written/merged files exist, no duplicates in manifest
- all written paths stay inside the configured vault
- file names avoid Obsidian-forbidden characters
- main note fragment wikilinks resolve to written/existing fragment notes
- WORD(world/outcome/route/doctrine) values stay within config allowlists
- route is a scalar when classification.route_scalar is on
- a sermon note carries exactly one world when classification.single_world is on
- classification values keep their emoji prefix (classification.require_value_prefix)
- tags contain no whitespace
- configured Bible link style is respected
- Bible links without a note are reported as warnings (bible.note_folder)

frontmatter는 YAML 파서 대신 정규식으로 읽는다 — 표준 파서는 "[[...]]" 값을 훼손할 수 있다.

병합(merged)된 조각의 frontmatter 위반은 issue 가 아니라 warning 이다. 그 값은
이번 import 가 만든 것이 아니라 목사님 볼트의 기존 상태이고, 그것을 고치는 것은
보충(backfill) 작업의 일이다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import sys

from config_loader import load_config
from note_utils import FORBIDDEN_FILENAME_CHARS, compare_key, strip_vs, strip_wikilink

WIKILINK_RE = re.compile(r"^## \[\[(?P<name>[^\]]+)\]\]", re.MULTILINE)
FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?)\n---(?:\n|\Z)", re.DOTALL)
MAIN_NOTE_MARKER = "# 원본 설교문"


def bad_filename(path: Path) -> list[str]:
    return [ch for ch in path.name if ch in FORBIDDEN_FILENAME_CHARS]


def parse_frontmatter(text: str) -> dict[str, dict]:
    """정규식 frontmatter 리더. 키마다 {"scalar": bool, "values": [...]} 를 준다.

    스칼라와 리스트를 구분해야 route 검사가 성립한다. 스칼라를 리스트로 감싸
    돌려주면 `route: "[[📝완료]]"` 와 `route:\\n  - "[[📝완료]]"` 가 구별되지 않는다.
    """
    m = FRONTMATTER_RE.match(text)
    fields: dict[str, dict] = {}
    if not m:
        return fields
    current: str | None = None
    for line in m.group("body").splitlines():
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")):
            kv = re.match(r"^(?P<key>[^:]+):\s*(?P<value>.*)$", line)
            if not kv:
                current = None
                continue
            key = kv.group("key").strip()
            value = kv.group("value").strip()
            if value == "[]":
                fields[key] = {"scalar": False, "values": []}
                current = None
            elif value:
                fields[key] = {"scalar": True, "values": [value.strip('"')]}
                current = None
            else:
                fields[key] = {"scalar": False, "values": []}
                current = key
        elif current:
            item = re.match(r"^\s+-\s+(?P<value>.*)$", line)
            if item:
                fields[current]["values"].append(item.group("value").strip().strip('"'))
    return fields


def parse_frontmatter_lists(text: str) -> dict[str, list[str]]:
    """하위 호환 wrapper — 값만 필요할 때."""
    return {key: entry["values"] for key, entry in parse_frontmatter(text).items()}


def allowlists_for(config: dict) -> dict[str, list[str]]:
    cls = config["classification"]
    lists = {
        "world": list(cls.get("world_values", [])),
        "outcome": list(cls.get("outcome_values", [])),
        "route": list(cls.get("route_values", [])),
        "doctrine": list(cls.get("doctrine_values", [])),
    }
    # 조각 world 는 config 에서 직접 지정하므로 world_values 에 없어도 허용값이다.
    fragment_world = str(cls.get("fragment_world") or "").strip()
    if fragment_world and lists["world"]:
        lists["world"].append(fragment_world)
    return lists


def check_classification(path: Path, fields: dict[str, dict], config: dict, sink: list[str]) -> None:
    cls = config["classification"]
    if not cls.get("use_word"):
        return
    allow_unknown = bool(cls.get("allow_unknown_doctrine"))
    for key, allowed in allowlists_for(config).items():
        if key not in fields or not allowed:
            continue
        if key == "doctrine" and allow_unknown:
            continue
        # build_notes 와 같은 정규화. 안 그러면 build 는 통과하고 verify 만 실패한다.
        lookup = {compare_key(item) for item in allowed}
        for value in fields[key]["values"]:
            if compare_key(value) not in lookup:
                sink.append(f"{key} 허용 목록 밖 값 '{value}': {path}")


def check_word_shape(path: Path, fields: dict[str, dict], config: dict, is_main: bool, sink: list[str]) -> None:
    cls = config["classification"]
    if not cls.get("use_word"):
        return
    if cls.get("route_scalar") and "route" in fields and not fields["route"]["scalar"]:
        sink.append(f"route 가 리스트입니다 (스칼라여야 함): {path}")
    if cls.get("single_world") and is_main and "world" in fields:
        count = len(fields["world"]["values"])
        if count != 1:
            sink.append(f"설교 노트의 world 가 {count}개입니다 (1개여야 함): {path}")
    for key, prefixes in (cls.get("require_value_prefix") or {}).items():
        if key not in fields or not prefixes:
            continue
        for value in fields[key]["values"]:
            bare = strip_vs(strip_wikilink(value))
            if not any(bare.startswith(strip_vs(str(p))) for p in prefixes):
                sink.append(f"{key} 값에 접두어({', '.join(prefixes)})가 없습니다 '{value}': {path}")


def check_tags(path: Path, fields: dict[str, dict], sink: list[str]) -> None:
    for tag in fields.get("tags", {}).get("values", []):
        if re.search(r"\s", tag):
            sink.append(f"태그에 띄어쓰기 '{tag}': {path}")


def manifest_entries(manifest: dict) -> list[dict]:
    """검사 대상 파일 목록. files[] 가 있으면 그것으로 종류를 판정한다."""
    rows = manifest.get("files") or []
    if rows:
        return [{"path": Path(r["path"]), "kind": r.get("kind"), "action": r.get("action", "create")}
                for r in rows if r.get("action") in {"create", "merge"}]
    entries = [{"path": Path(p), "kind": None, "action": "create"} for p in manifest.get("written", [])]
    entries += [{"path": Path(p), "kind": None, "action": "merge"} for p in manifest.get("merged", [])]
    return entries


def verify_manifest(manifest_path: Path, config_path: str | None = None) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config = load_config(config_path) if config_path else None
    vault = Path(config["vault"]["path"]).expanduser().resolve() if config else None
    fragment_folder = None
    if config:
        fragment_folder = Path(config["vault"]["path"]).expanduser() / config["output"]["fragment_folder"]

    issues: list[str] = []
    warnings: list[str] = []

    seen: set[str] = set()
    for raw_path in list(manifest.get("written", [])) + list(manifest.get("merged", [])):
        if raw_path in seen:
            issues.append(f"duplicate path in manifest: {raw_path}")
        seen.add(raw_path)

    entries = manifest_entries(manifest)
    for entry in entries:
        path = entry["path"]
        if vault and not path.resolve().is_relative_to(vault):
            issues.append(f"vault 밖 경로가 생성됨: {path}")
        if not path.exists():
            issues.append(f"missing file: {path}")
            continue
        bad = bad_filename(path)
        if bad:
            issues.append(f"forbidden filename chars {bad}: {path}")

    present = [e for e in entries if e["path"].exists() and e["path"].suffix == ".md"]
    for entry in present:
        if entry["kind"] is None:
            text = entry["path"].read_text(encoding="utf-8", errors="ignore")
            entry["kind"] = "main" if MAIN_NOTE_MARKER in text else "fragment"

    main_files = [e["path"] for e in present if e["kind"] == "main"]
    fragment_stems = {e["path"].stem for e in present if e["kind"] == "fragment"}
    all_stems = {e["path"].stem for e in present}

    for main in main_files:
        text = main.read_text(encoding="utf-8")
        for match in WIKILINK_RE.finditer(text):
            name = match.group("name")
            if name in fragment_stems or name in all_stems:
                continue
            sibling = (fragment_folder / f"{name}.md") if fragment_folder else (main.parent.parent / f"{name}.md")
            if not sibling.exists():
                issues.append(f"fragment wikilink does not resolve: {main} -> [[{name}]]")

    if config:
        style = config["bible"]["link_style"]
        if "{normalized}" not in style:
            issues.append("invalid config link_style")

        for entry in present:
            fields = parse_frontmatter(entry["path"].read_text(encoding="utf-8", errors="ignore"))
            # 병합된 조각의 frontmatter 는 목사님이 예전에 쓴 것이다 — 경고로만 남긴다.
            sink = warnings if entry["action"] == "merge" else issues
            prefix = "(기존 노트) " if entry["action"] == "merge" else ""
            local: list[str] = []
            check_classification(entry["path"], fields, config, local)
            check_word_shape(entry["path"], fields, config, entry["kind"] == "main", local)
            check_tags(entry["path"], fields, local)
            sink.extend(prefix + msg for msg in local)

        note_folder = str(config["bible"].get("note_folder") or "").strip()
        if note_folder:
            folder = Path(config["vault"]["path"]).expanduser() / note_folder
            if folder.exists():
                existing = {compare_key(p.stem) for p in folder.rglob("*.md")}
                bible_key = config["bible"].get("frontmatter_key", "성경구절")
                unresolved: set[str] = set()
                for main in main_files:
                    fields = parse_frontmatter(main.read_text(encoding="utf-8", errors="ignore"))
                    for link in fields.get(bible_key, {}).get("values", []):
                        key = compare_key(link)
                        if key and key not in existing:
                            unresolved.add(key)
                if unresolved:
                    sample = ", ".join(sorted(unresolved)[:8])
                    warnings.append(
                        f"성경구절 노트가 없는 링크 {len(unresolved)}개 — "
                        f"옵시디언에서 빨간 링크로 보입니다: {sample}"
                    )
            else:
                warnings.append(f"bible.note_folder 경로가 없습니다: {folder}")

    return {
        "status": "ok" if not issues else "blocked",
        "manifest": str(manifest_path),
        "files_checked": len(entries),
        "merged_files": len(manifest.get("merged", [])),
        "issues": issues,
        "warnings": warnings,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--config")
    args = parser.parse_args(argv[1:])
    result = verify_manifest(Path(args.manifest).expanduser(), args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
