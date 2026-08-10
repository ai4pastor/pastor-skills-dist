#!/usr/bin/env python3
"""Build sermon import plan, dry-run preview, and approved writes.

Default mode is dry-run. Actual writes require both:
- --write
- --approve WRITE

Claude(LLM) 분석 결과 주입:
- --fragments fragments.json : prompts/split_fragments.md 결과 (의미 단위 조각)
- --word word.json           : prompts/word_classify.md 결과 (WORD/분류 제안)
둘 다 없으면 결정론 분해로 fallback하고 WORD frontmatter는 비워 둔다.
주입된 doctrine/tags는 config 허용 목록으로 검증하며, 목록 밖 값은 버리고 경고를 남긴다.

This script never modifies source sermon files and never overwrites existing vault notes.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import argparse
import json
import re
import sys
from typing import Any, Iterable

from config_loader import load_config
from extract_text import SUPPORTED, extract as extract_text, extract_cached
from extract_meta import extract_meta
from note_utils import (
    check_title_style,
    collapse_separators,
    compare_key,
    ensure_relative_folder,
    format_frontmatter,
    is_sidecar,
    parse_bullets,
    sanitize_title,
    unique_name,
)

def collect_inputs(input_path: Path, config: dict[str, Any] | None = None) -> list[Path]:
    """Collect sermon files, honouring input.file_types.

    A file named explicitly is always processed; the filter only applies when
    walking a folder.
    """
    if input_path.is_file():
        return [input_path]
    allowed = set(SUPPORTED)
    declared = {f".{str(t).lower().lstrip('.')}" for t in ((config or {}).get("input", {}).get("file_types") or [])}
    if declared:
        allowed &= declared
    return sorted(
        p for p in input_path.rglob("*")
        if p.is_file() and p.suffix.lower() in allowed and not is_sidecar(p)
    )


def split_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+|(?<=다\.)\s+|(?<=요\.)\s+", compact)
    return [p.strip() for p in parts if p.strip()]


def bullets_from_body(body: str, max_bullets: int = 4) -> list[str]:
    sentences = split_sentences(body)
    if not sentences:
        return []
    bullets: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) < 160:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                bullets.append(current)
            current = sentence
        if len(bullets) >= max_bullets:
            break
    if current and len(bullets) < max_bullets:
        bullets.append(current)
    return bullets


def is_noise_fragment(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    if re.fullmatch(r"[-*_\s]{3,}", cleaned):
        return True
    if re.fullmatch(r"\d{6,8}\s+.{1,40}", cleaned):
        return True
    if re.fullmatch(r"[가-힣A-Za-z0-9 .:_-]{1,30}\s*(을|를)?\s*읽습니다\. ?", cleaned):
        return True
    return len(cleaned) < 40


def split_fragments(text: str, sermon_id: str) -> list[dict[str, Any]]:
    """Deterministic fallback splitter using headings/paragraphs and sentence boundaries."""
    normalized = text.strip()
    sections = re.split(r"\n(?=#{1,3}\s+)|\n\s*---\s*\n", normalized)
    fragments: list[dict[str, Any]] = []
    for section in sections:
        lines = [ln.strip() for ln in section.splitlines() if ln.strip()]
        if not lines:
            continue
        has_heading = bool(re.match(r"^#{1,3}\s+", lines[0]))
        heading = re.sub(r"^#{1,3}\s*", "", lines[0]).strip() if has_heading else ""
        body_lines = lines[1:] if has_heading else lines
        body = "\n".join(body_lines).strip()
        if is_noise_fragment(body):
            continue
        if len(body) < 80 and len(sections) > 1:
            continue
        title_seed = heading or (split_sentences(body)[0][:30] if split_sentences(body) else f"{sermon_id} 조각")
        title = sanitize_title(title_seed, "설교 조각")
        bullets = bullets_from_body(body)
        fragments.append({"title": title, "kind": "section" if has_heading else "paragraph", "bullets": bullets or [title]})
    if not fragments:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalized) if p.strip()]
        for idx, paragraph in enumerate(paragraphs[:8], 1):
            if is_noise_fragment(paragraph):
                continue
            title_seed = split_sentences(paragraph)[0][:30] if split_sentences(paragraph) else f"{sermon_id} 조각 {idx:02d}"
            fragments.append({"title": sanitize_title(title_seed), "kind": "paragraph", "bullets": bullets_from_body(paragraph) or [paragraph]})
    if not fragments:
        meaningful = re.sub(r"\s+", " ", normalized).strip()
        if meaningful:
            fragments.append({"title": sanitize_title(f"{sermon_id} 핵심 요약"), "kind": "fallback", "bullets": bullets_from_body(meaningful, max_bullets=5) or [meaningful[:200]]})
    return fragments[:20]


def load_injection(path: str | None, notes: list[str] | None = None) -> dict[str, Any]:
    """Load LLM analysis JSON keyed by source path or file name.

    경로가 폴더면 그 안의 `*.json` 을 파일명 순으로 병합한다 — 대량 import 를
    청크(몇 편씩)로 나눠 분석한 결과를 그대로 받기 위해서다. 같은 소스 키가
    겹치면 나중 파일이 이기고, notes 에 그 사실을 남긴다.
    """
    if not path:
        return {}
    target = Path(path).expanduser()
    files = sorted(target.glob("*.json")) if target.is_dir() else [target]
    merged: dict[str, Any] = {}
    for file in files:
        data = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"injection JSON must be an object keyed by source path or name: {file}")
        for key, value in data.items():
            if key in merged and notes is not None:
                notes.append(f"분석 JSON 중복 키 '{key}' — {file.name} 값을 사용")
            merged[key] = value
    return merged


def lookup_injection(data: dict[str, Any], source: Path) -> Any:
    return data.get(str(source)) or data.get(source.name)


def validate_tags(tags: list[Any], warnings: list[str], where: str) -> list[str]:
    out = []
    for tag in tags:
        cleaned = sanitize_title(str(tag), "")
        if not cleaned:
            continue
        if " " in cleaned:
            fixed = cleaned.replace(" ", "")
            warnings.append(f"{where}: 태그 띄어쓰기 자동 결합 '{cleaned}' → '{fixed}'")
            cleaned = fixed
        out.append(cleaned)
    return list(dict.fromkeys(out))


def validate_allowed(values: list[Any], allowed: list[str], warnings: list[str], where: str, allow_unknown: bool = False) -> list[str]:
    """Filter values against the allow-list, comparing canonically.

    Values the pastor copied out of their own vault arrive NFD-decomposed (macOS)
    or with a stray U+FE0F on the emoji prefix, so a raw string comparison would
    reject every one of them. compare_key() normalizes both sides, and the value
    that gets stored is the allow-list's own spelling — never the LLM's.
    """
    lookup = {compare_key(item): str(item) for item in (allowed or [])}
    out = []
    for value in values:
        raw = str(value).strip()
        if not raw:
            continue
        if lookup:
            hit = lookup.get(compare_key(raw))
            if hit is None and not allow_unknown:
                warnings.append(f"{where}: 허용 목록 밖 값 제외 '{raw}'")
                continue
            raw = hit if hit is not None else raw
        out.append(raw)
    return list(dict.fromkeys(out))


def decorate_values(values: Iterable[Any], wrap: bool) -> list[str]:
    """Optionally wrap classification values in [[...]] at write time.

    Allow-lists store bare values; wikilink syntax is a presentation choice so
    that comparisons stay clean and the pastor's graph still links up.
    """
    out = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        out.append(text if text.startswith("[[") else f"[[{text}]]")
    return out if wrap else [str(v).strip() for v in values if str(v).strip()]


def sanitize_llm_fragments(raw: Any, config: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    cls = config["classification"]
    allowed_doctrine = cls.get("doctrine_values", [])
    allow_unknown = bool(cls.get("allow_unknown_doctrine"))
    fragments: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        raise ValueError("fragments entry must be a list")
    for idx, item in enumerate(raw, 1):
        title = sanitize_title(str(item.get("title", "")), "")
        if not title:
            warnings.append(f"조각 {idx}: 제목 없음 — 제외")
            continue
        bullets = [str(b).strip() for b in item.get("bullets", []) if str(b).strip()]
        if not bullets:
            warnings.append(f"조각 '{title}': 글머리 없음 — 제외")
            continue
        fragment: dict[str, Any] = {
            "title": title,
            "kind": str(item.get("kind", "argument")),
            "bullets": bullets,
        }
        if cls.get("use_word"):
            fragment["doctrine"] = validate_allowed(item.get("doctrine", []), allowed_doctrine, warnings, f"조각 '{title}' doctrine", allow_unknown)
        fragment["tags"] = validate_tags(item.get("tags", []), warnings, f"조각 '{title}'")
        fragments.append(fragment)
    return fragments


def sanitize_word(raw: Any, config: dict[str, Any], warnings: list[str], sermon_kind: str = "") -> dict[str, list[str]]:
    cls = config["classification"]
    if not isinstance(raw, dict):
        raise ValueError("word entry must be an object")
    allow_unknown = bool(cls.get("allow_unknown_doctrine"))
    out = {
        "world": validate_allowed(raw.get("world", []), cls.get("world_values", []), warnings, "world"),
        "outcome": validate_allowed(raw.get("outcome", []), cls.get("outcome_values", []), warnings, "outcome"),
        "route": validate_allowed(raw.get("route", []), cls.get("route_values", []), warnings, "route"),
        "doctrine": validate_allowed(raw.get("doctrine", []), cls.get("doctrine_values", []), warnings, "doctrine", allow_unknown),
    }
    if not out["world"] and sermon_kind:
        # 설교 구분에 짝지어 둔 World 값이 있으면 그것으로 채운다. 목사님이 온보딩에서
        # 확인한 대응이므로, LLM 제안이 허용 목록에서 걸러졌을 때의 안전한 기본값이다.
        mapped = str(((config.get("sermon_kinds") or {}).get("world_by_kind") or {}).get(sermon_kind, "")).strip()
        if mapped:
            out["world"] = validate_allowed([mapped], cls.get("world_values", []), warnings,
                                            f"world({sermon_kind} 기본값)")
    out["tags"] = validate_tags(raw.get("tags", []), warnings, "tags")
    return out


def main_folder_for(vault: Path, config: dict[str, Any], sermon_kind: str) -> Path:
    """구분별 폴더가 지정돼 있으면 그 폴더, 없으면 기본 설교 폴더."""
    routed = str(((config.get("sermon_kinds") or {}).get("folder_by_kind") or {}).get(sermon_kind, "")).strip()
    folder = routed or config["output"]["main_sermon_folder"]
    return vault / ensure_relative_folder(folder)


def apply_pattern(pattern: str, values: dict[str, str]) -> str:
    """Render a note name from the pattern.

    Empty placeholders collapse instead of leaving "260101__제목.md" or the old
    "untitled" filler, so a sermon with no date or no main passage still gets a
    name the pastor recognizes.
    """
    safe_values = {k: sanitize_title(v, "") for k, v in values.items()}
    try:
        name = pattern.format(**safe_values)
    except KeyError as exc:
        raise ValueError(f"unknown naming placeholder: {exc}") from exc
    return sanitize_title(collapse_separators(name.removesuffix(".md"))) + ".md"


def render_main_note(meta: dict[str, Any], text: str, fragments: list[dict[str, Any]], word: dict[str, list[str]] | None, config: dict[str, Any]) -> str:
    now = datetime.now().isoformat(timespec="minutes")
    ok_bible_links = list(dict.fromkeys(r["link"] for r in meta["bible_refs"] if r.get("status") == "ok"))
    bible_key = config["bible"].get("frontmatter_key", "성경구절")
    cls = config["classification"]
    wrap = bool(cls.get("wrap_values_in_wikilink"))
    fields: dict[str, object] = {"created": now, "modified": now}
    if cls.get("use_word"):
        word = word or {}
        fields["world"] = decorate_values(word.get("world", []), wrap)
        fields["outcome"] = decorate_values(word.get("outcome", []), wrap)
        route_values = decorate_values(word.get("route", []), wrap)
        # route holds a single value; emitting a list fails the vault's own check.
        fields["route"] = (route_values[0] if route_values else "") if cls.get("route_scalar") else route_values
        fields["doctrine"] = decorate_values(word.get("doctrine", []), wrap)
    if word and word.get("tags"):
        fields["tags"] = word["tags"]
    kinds = config.get("sermon_kinds") or {}
    kind_key = str(kinds.get("frontmatter_key") or "").strip()
    if kind_key and meta.get("sermon_kind"):
        # 구분을 속성으로 남기면 폴더를 나누지 않아도 검색·Dataview 로 갈라 볼 수 있다.
        fields[kind_key] = meta["sermon_kind"]
    fields[bible_key] = ok_bible_links
    # Provenance fields come after the classification block so the fields the
    # pastor's guideline orders (created → … → 성경구절) stay in that order.
    fields.update({
        "source_file": meta["source_path"],
        "sermon_id": meta["sermon_id"],
        "title": meta["title"],
        "date": meta.get("date", ""),
        "main_passage": meta.get("main_passage", ""),
    })
    body = [format_frontmatter(fields), f"# {meta['title']}", ""]
    for fragment in fragments:
        body.append(f"## [[{fragment['basename']}]]")
        body.extend(f"- {bullet}" for bullet in fragment.get("bullets", []))
        body.append("")
    ambiguous = [r for r in meta["bible_refs"] if r.get("status") != "ok"]
    if ambiguous:
        body.append("## 확인 필요한 성경구절")
        body.extend(f"- {r.get('raw')} — {r.get('note', r.get('status'))}" for r in ambiguous)
        body.append("")
    body.extend(["---", "", "# 원본 설교문", "", text.rstrip(), ""])
    return "\n".join(body)


def render_fragment_note(fragment: dict[str, Any], main_basename: str, config: dict[str, Any]) -> str:
    now = datetime.now().isoformat(timespec="minutes")
    cls = config["classification"]
    wrap = bool(cls.get("wrap_values_in_wikilink"))
    fields: dict[str, object] = {"created": now, "modified": now}
    if cls.get("use_word"):
        # Fragments carry a world value so they show up under the pastor's
        # taxonomy, but no outcome/route — those describe a finished sermon.
        fragment_world = str(cls.get("fragment_world") or "").strip()
        if fragment_world:
            fields["world"] = decorate_values([fragment_world], wrap)
        if fragment.get("doctrine"):
            fields["doctrine"] = decorate_values(fragment["doctrine"], wrap)
    if fragment.get("tags"):
        fields["tags"] = fragment["tags"]
    content = [format_frontmatter(fields)]
    content.extend(f"- {bullet}" for bullet in fragment.get("bullets", []))
    content.extend(["", f"원본 설교: [[{main_basename}]]", ""])
    return "\n".join(content)


def bullet_key(text: Any) -> str:
    return compare_key(re.sub(r"\s+", " ", str(text)).strip())


def plan_merge(path: Path, new_bullets: list[str], main_basename: str) -> dict[str, Any]:
    """Plan an append-only merge into an existing fragment note.

    The pastor's frontmatter is reused byte-for-byte — including `modified` — so
    a merge adds bullets and nothing else. Classification the LLM proposed for
    this fragment is dropped on purpose; changing values the pastor already set
    is the backfill mode's job, not import's.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    frontmatter, existing, trailer = parse_bullets(text)
    seen = {bullet_key(b) for b in existing}
    added: list[str] = []
    duplicate = 0
    for bullet in new_bullets:
        key = bullet_key(bullet)
        if not key:
            continue
        if key in seen:
            duplicate += 1
            continue
        seen.add(key)
        added.append(str(bullet).strip())

    backlink = f"원본 설교: [[{main_basename}]]"
    return {
        "frontmatter": frontmatter,
        "existing": existing,
        "trailer": trailer,
        "added": added,
        "duplicate": duplicate,
        "backlink_present": backlink in text,
    }


def render_merged_fragment(merge: dict[str, Any], main_basename: str) -> str:
    """Rebuild the fragment with new bullets appended to the bullet block.

    Appending at end-of-file would put bullets after the backlink line, so the
    note is reassembled as frontmatter / bullets / trailer.
    """
    parts: list[str] = []
    if merge["frontmatter"]:
        parts.append(merge["frontmatter"].rstrip("\n"))
    parts.append("")
    parts.extend(f"- {bullet}" for bullet in merge["existing"])
    parts.extend(f"- {bullet}" for bullet in merge["added"])

    trailer = merge["trailer"].strip("\n")
    backlink = f"원본 설교: [[{main_basename}]]"
    if not merge["backlink_present"]:
        trailer = f"{trailer}\n{backlink}" if trailer else backlink
    if trailer:
        parts.extend(["", trailer])
    return "\n".join(parts) + "\n"


def load_prior_imports(log_folder: Path) -> tuple[set[str], set[str]]:
    """이전 manifest 들에서 이미 편입된 원고의 경로·sermon_id 를 모은다 (resume 용).

    신형 manifest 는 `sources` 배열(source·sermon_id·action)을 갖는다. 충돌로
    건너뛴 원고(`skip_conflict`)는 편입된 것이 아니므로 다음 실행에서 다시 보인다.
    구형 manifest 에는 summary.fragment_modes 의 키가 소스 경로라 그것으로 대신한다
    (구형은 충돌이 있으면 아예 쓰지 못했으므로 전부 편입된 원고다).
    """
    paths: set[str] = set()
    ids: set[str] = set()
    if not log_folder.exists():
        return paths, ids
    for manifest_path in sorted(log_folder.glob("import-manifest-*.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = manifest.get("sources")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict) or row.get("action") == "skip_conflict":
                    continue
                if str(row.get("source") or ""):
                    paths.add(str(row["source"]))
                if str(row.get("sermon_id") or ""):
                    ids.add(str(row["sermon_id"]))
            continue
        modes = (manifest.get("summary") or {}).get("fragment_modes") or {}
        paths.update(str(source) for source in modes)
    return paths, ids


def build_plan(input_path: Path, config: dict[str, Any], llm_fragments: dict[str, Any] | None = None, llm_word: dict[str, Any] | None = None,
               resume: bool = False, use_cache: bool = True) -> dict[str, Any]:
    vault = Path(config["vault"]["path"]).expanduser()
    if not vault.exists():
        raise FileNotFoundError(f"vault not found: {vault}")
    # 구분별 폴더는 파일마다 달라질 수 있어 아래 루프에서 정한다.
    fragment_folder = vault / ensure_relative_folder(config["output"]["fragment_folder"])
    log_folder = vault / ensure_relative_folder(config["output"]["log_folder"])
    # collision_policy 는 메인 노트 전용, fragment_collision_policy 는 조각 전용.
    collision_policy = config["naming"].get("collision_policy", "ask")
    fragment_policy = config["naming"].get("fragment_collision_policy", "skip")
    if fragment_policy == "merge" and "{title}" not in config["naming"].get("fragment_note_pattern", ""):
        # 파일명이 제목과 같지 않으면 같은 조각을 다시 찾을 수 없어 병합이 성립하지 않는다.
        fragment_policy = "skip"
    files = collect_inputs(input_path, config)
    llm_fragments = llm_fragments or {}
    llm_word = llm_word or {}
    used_fragment_names: set[str] = set()
    used_main_names: set[str] = set()
    items = []
    failures = []
    resumed: list[dict[str, Any]] = []
    prior_paths: set[str] = set()
    prior_ids: set[str] = set()
    if resume:
        prior_paths, prior_ids = load_prior_imports(log_folder)
    for source in files:
        if resume and str(source) in prior_paths:
            # 경로가 일치하면 추출(변환)도 하기 전에 건너뛴다.
            resumed.append({"source": str(source), "match": "path"})
            continue
        try:
            warnings: list[str] = []
            extracted = extract_cached(source) if use_cache else extract_text(source)
            text = str(extracted["text"])
            meta = extract_meta(source, text, config)
            if resume and str(meta.get("sermon_id") or "") in prior_ids:
                # 파일이 옮겨지거나 이름이 바뀌어도 같은 설교(sermon_id)면 잡는다.
                resumed.append({"source": str(source), "match": "sermon_id",
                                "sermon_id": str(meta["sermon_id"])})
                continue
            warnings.extend(str(w) for w in (extracted.get("warnings") or []))
            sermon_kind = str(meta.get("sermon_kind") or "")
            main_name = apply_pattern(config["naming"]["main_note_pattern"], {
                "date": meta.get("date", ""),
                "yymmdd": meta.get("yymmdd", ""),
                "title": meta["title"],
                "main_passage": meta.get("main_passage", ""),
                "sermon_id": meta["sermon_id"],
                "target": meta.get("target", ""),
                "kind": sermon_kind,
            })
            main_name = unique_name(main_name.removesuffix(".md"), used_main_names)
            main_path = main_folder_for(vault, config, sermon_kind) / main_name
            if config.get("sermon_kinds", {}).get("enabled") and not sermon_kind:
                warnings.append(f"설교 구분을 알 수 없습니다 — 기본 폴더에 넣습니다: {source.name}")

            raw_fragments = lookup_injection(llm_fragments, source)
            if raw_fragments is not None:
                fragments = sanitize_llm_fragments(raw_fragments, config, warnings)
                fragment_mode = "llm"
            else:
                fragments = split_fragments(text, meta["sermon_id"])
                fragment_mode = "deterministic"
                if llm_fragments:
                    warnings.append("LLM 조각 없음 — 결정론 분해로 fallback")

            word = None
            if config["classification"].get("use_word"):
                raw_word = lookup_injection(llm_word, source)
                if raw_word is not None:
                    word = sanitize_word(raw_word, config, warnings, sermon_kind)
                else:
                    warnings.append("WORD 제안 없음 — 분류 frontmatter를 비워 둠")

            main_basename = main_name.removesuffix(".md")
            main_action = "create"
            if main_path.exists():
                main_action = "skip" if collision_policy == "skip" else "conflict"

            fragment_outputs = []
            for idx, fragment in enumerate(fragments, 1):
                pattern_values = {
                    "sermon_id": meta["sermon_id"],
                    "title": fragment["title"],
                    "index": f"{idx:02d}",
                    "date": meta.get("date", ""),
                    "yymmdd": meta.get("yymmdd", ""),
                    "target": meta.get("target", ""),
                    "kind": sermon_kind,
                }
                frag_name = apply_pattern(config["naming"]["fragment_note_pattern"], pattern_values)
                frag_name = unique_name(frag_name.removesuffix(".md"), used_fragment_names)
                frag_path = fragment_folder / frag_name
                basename = frag_name.removesuffix(".md")
                if fragment_mode == "llm":
                    # 스타일 경고만 남긴다 — 제목을 거부하면 그 조각의 설교 내용이 유실된다.
                    warnings.extend(check_title_style(fragment["title"], fragment.get("kind", "argument")))

                exists = frag_path.exists()
                action = "create"
                merge_info = None
                content = render_fragment_note(fragment, main_basename, config)
                if exists:
                    if fragment_policy == "merge":
                        merge_info = plan_merge(frag_path, fragment.get("bullets", []), main_basename)
                        if merge_info["added"] or not merge_info["backlink_present"]:
                            action = "merge"
                            content = render_merged_fragment(merge_info, main_basename)
                        else:
                            # 추가할 것이 없으면 파일을 건드리지 않는다 (mtime 보존)
                            action = "skip"
                    elif fragment_policy == "skip":
                        action = "skip"
                    else:
                        action = "conflict"

                entry: dict[str, Any] = {
                    "title": fragment["title"],
                    "path": str(frag_path),
                    "basename": basename,
                    "exists": exists,
                    "action": action,
                    "content": content,
                    "bullets": fragment.get("bullets", []),
                }
                if merge_info is not None:
                    entry["merge"] = {
                        "added": merge_info["added"],
                        "added_bullets": len(merge_info["added"]),
                        "duplicate_bullets": merge_info["duplicate"],
                        "existing_bullets": len(merge_info["existing"]),
                    }
                    if merge_info["added"] and fragment.get("doctrine"):
                        warnings.append(
                            f"조각 '{fragment['title']}': 기존 노트에 병합 — 분류 제안은 "
                            "기존 frontmatter 를 보존하기 위해 적용하지 않았습니다"
                        )
                fragment_outputs.append(entry)
            warnings.extend(f"ambiguous bible ref: {r.get('raw')}" for r in meta["bible_refs"] if r.get("status") != "ok")
            items.append({
                "source": str(source),
                "meta": meta,
                "fragment_mode": fragment_mode,
                "word": word,
                "sermon_kind": sermon_kind,
                "main": {
                    "path": str(main_path),
                    "basename": main_basename,
                    "exists": main_path.exists(),
                    "action": main_action,
                    "sermon_kind": sermon_kind,
                    "content": render_main_note(meta, text, fragment_outputs, word, config),
                },
                "fragments": fragment_outputs,
                "warnings": warnings,
            })
        except Exception as exc:
            failures.append({"source": str(source), "error": str(exc), "type": type(exc).__name__})
    return {"created": datetime.now().isoformat(timespec="minutes"), "mode": "dry-run", "vault": str(vault), "log_folder": str(log_folder), "items": items, "failures": failures, "resumed": resumed}


def summarize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    files = []
    conflicts = []
    merges = []
    skips = []
    warnings = []
    by_kind: dict[str, int] = {}
    for item in plan["items"]:
        main = item["main"]
        main_action = main.get("action", "create")
        sermon_kind = str(item.get("sermon_kind") or "")
        by_kind[sermon_kind or "(구분 없음)"] = by_kind.get(sermon_kind or "(구분 없음)", 0) + 1
        files.append({"kind": "main", "path": main["path"], "exists": main["exists"],
                      "action": main_action, "sermon_kind": sermon_kind})
        if main_action == "conflict":
            conflicts.append(main["path"])
        for frag in item["fragments"]:
            action = frag.get("action", "create")
            row: dict[str, Any] = {"kind": "fragment", "path": frag["path"],
                                   "exists": frag["exists"], "action": action}
            if frag.get("merge"):
                row["added_bullets"] = frag["merge"]["added_bullets"]
                row["duplicate_bullets"] = frag["merge"]["duplicate_bullets"]
            files.append(row)
            if action == "conflict":
                conflicts.append(frag["path"])
            elif action == "merge":
                merges.append({"path": frag["path"], "title": frag["title"],
                               "added_bullets": frag["merge"]["added_bullets"],
                               "duplicate_bullets": frag["merge"]["duplicate_bullets"]})
            elif action == "skip":
                skips.append(frag["path"])
        warnings.extend(item.get("warnings", []))
    warnings.extend(plan.get("notes", []))
    return {
        "created": plan["created"],
        "sources": len(plan["items"]),
        "failed_sources": len(plan.get("failures", [])),
        "resumed_sources": len(plan.get("resumed", [])),
        "resumed": plan.get("resumed", []),
        "planned_files": len(files),
        "by_sermon_kind": by_kind,
        "fragment_modes": {item["source"]: item.get("fragment_mode", "") for item in plan["items"]},
        "conflicts": conflicts,
        "merges": merges,
        "skips": skips,
        "warnings": warnings,
        "failures": plan.get("failures", []),
        "files": files,
    }


def write_plan(plan: dict[str, Any], config: dict[str, Any], skip_conflicts: bool = False) -> Path:
    if config["safety"].get("overwrite_existing"):
        raise ValueError("overwrite_existing is forbidden")
    summary = summarize_plan(plan)
    if summary["conflicts"] and not skip_conflicts:
        # 기본값은 지금까지처럼 전체 중단. --skip-conflicts 는 dry-run 미리보기에서
        # 충돌 목록을 승인받은 뒤에만 쓴다 — 충돌 설교만 건너뛰고 나머지를 쓴다.
        raise FileExistsError("existing notes block write: " + "; ".join(summary["conflicts"][:10]))

    written: list[str] = []
    skipped: list[str] = []
    merged: list[str] = []
    files_log: list[dict[str, Any]] = []
    sources_log: list[dict[str, Any]] = []

    for item in plan["items"]:
        main_path = Path(item["main"]["path"])
        sermon_kind = str(item.get("sermon_kind") or "")
        source_row = {"source": item.get("source", ""),
                      "sermon_id": str((item.get("meta") or {}).get("sermon_id") or ""),
                      "main": str(main_path)}
        main_action = item["main"].get("action", "create")
        if main_action == "conflict" and skip_conflicts:
            main_action = "skip_conflict"
        if main_action == "create" and main_path.exists():
            # 계획 이후 나타난 노트 — 승인 없이 덮어쓰지 않는다.
            if not skip_conflicts:
                raise FileExistsError(f"existing note appeared before write: {main_path}")
            main_action = "skip_conflict"
        if main_action in ("skip", "skip_conflict"):
            # Skip the whole sermon so no fragment points at an unchanged main note.
            skipped.append(str(main_path))
            skipped.extend(frag["path"] for frag in item["fragments"])
            files_log.append({"path": str(main_path), "kind": "main", "action": main_action,
                              "sermon_kind": sermon_kind})
            sources_log.append({**source_row, "action": main_action})
            continue
        main_path.parent.mkdir(parents=True, exist_ok=True)
        main_path.write_text(item["main"]["content"], encoding="utf-8")
        written.append(str(main_path))
        files_log.append({"path": str(main_path), "kind": "main", "action": "create",
                          "sermon_kind": sermon_kind})
        sources_log.append({**source_row, "action": "create"})

        for frag in item["fragments"]:
            frag_path = Path(frag["path"])
            action = frag.get("action", "create")
            row: dict[str, Any] = {"path": str(frag_path), "kind": "fragment", "action": action}

            if action == "skip":
                skipped.append(str(frag_path))
                files_log.append(row)
                continue

            if action == "conflict":
                if not skip_conflicts:
                    raise FileExistsError(f"existing fragment blocks write: {frag_path}")
                # 메인 노트의 [[링크]]는 이미 있는 동명 조각을 가리키게 된다.
                skipped.append(str(frag_path))
                files_log.append({**row, "action": "skip_conflict"})
                continue

            if action == "merge":
                before = frag_path.read_text(encoding="utf-8", errors="ignore")
                frag_path.write_text(frag["content"], encoding="utf-8")
                after = frag_path.read_text(encoding="utf-8")
                # 병합은 append-only 다. 기존 frontmatter 와 글머리가 결과에 그대로
                # 남아 있지 않으면 되돌린다 — 목사님이 쓴 것을 고치는 경로는 없다.
                old_fm, old_bullets, _ = parse_bullets(before)
                lost = [b for b in old_bullets if b and b not in after]
                if (old_fm and old_fm not in after) or lost:
                    frag_path.write_text(before, encoding="utf-8")
                    raise ValueError(f"merge가 기존 내용을 보존하지 못해 되돌렸습니다: {frag_path}")
                merged.append(str(frag_path))
                info = frag.get("merge", {})
                row["added_bullets"] = info.get("added_bullets", 0)
                row["duplicate_bullets"] = info.get("duplicate_bullets", 0)
                files_log.append(row)
                continue

            if frag_path.exists():
                skipped.append(str(frag_path))
                files_log.append({**row, "action": "skip"})
                continue
            frag_path.parent.mkdir(parents=True, exist_ok=True)
            frag_path.write_text(frag["content"], encoding="utf-8")
            written.append(str(frag_path))
            files_log.append(row)

    log_folder = Path(plan["log_folder"])
    log_folder.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created": datetime.now().isoformat(timespec="minutes"),
        "written": written,
        "skipped": skipped,
        "merged": merged,
        "files": files_log,
        "sources": sources_log,
        "summary": summary,
    }
    manifest_path = log_folder / f"import-manifest-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="sermon file or folder")
    parser.add_argument("--config", help="config JSON path")
    parser.add_argument("--fragments", help="LLM 조각 분해 결과 JSON — 파일 또는 청크 JSON 폴더 (source 경로/파일명 → 조각 목록)")
    parser.add_argument("--word", help="LLM WORD 분류 제안 JSON — 파일 또는 청크 JSON 폴더 (source 경로/파일명 → 분류 객체)")
    parser.add_argument("--write", action="store_true", help="write files; default is dry-run only")
    parser.add_argument("--approve", default="", help="must be WRITE for --write")
    parser.add_argument("--full", action="store_true", help="include generated content in dry-run JSON")
    parser.add_argument("--resume", action="store_true", help="이전 manifest에 기록된 원고는 건너뛴다 (경로 또는 sermon_id 일치)")
    parser.add_argument("--skip-conflicts", action="store_true", help="충돌 노트만 건너뛰고 나머지를 쓴다 — dry-run에서 충돌 목록 승인 후에만")
    parser.add_argument("--no-cache", action="store_true", help="추출 캐시를 쓰지 않고 매번 다시 변환한다")
    args = parser.parse_args(argv[1:])

    config = load_config(args.config)
    notes: list[str] = []
    llm_fragments = load_injection(args.fragments, notes)
    llm_word = load_injection(args.word, notes)
    plan = build_plan(Path(args.input).expanduser(), config, llm_fragments, llm_word,
                      resume=args.resume, use_cache=not args.no_cache)
    plan["notes"] = notes
    summary = summarize_plan(plan)
    if args.write:
        if args.approve != "WRITE":
            print(json.dumps({"status": "blocked", "reason": "--write requires --approve WRITE", "summary": summary}, ensure_ascii=False, indent=2))
            return 2
        try:
            manifest = write_plan(plan, config, skip_conflicts=args.skip_conflicts)
        except FileExistsError as exc:
            print(json.dumps({"status": "blocked", "reason": str(exc), "summary": summary}, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps({"status": "written", "manifest": str(manifest), "summary": summary}, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(plan if args.full else {"status": "dry-run", "summary": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
