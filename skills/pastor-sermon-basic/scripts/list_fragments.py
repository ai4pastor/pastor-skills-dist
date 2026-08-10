#!/usr/bin/env python3
"""목사님 볼트에 이미 있는 조각 제목 목록을 출력한다.

    python3 scripts/list_fragments.py --config "{config}" [--limit 500] [--sort mtime|name]
    python3 scripts/list_fragments.py --config "{config}" --match-file draft.json \
        [--match "제목 초안"]... [--top 5] [--extra "{fragments_dir}"]

기본 모드는 제목 전체 목록 — 조각이 적은 볼트에서 그대로 프롬프트에 넣는다.

매치 모드(--match/--match-file)는 새로 지으려는 제목 초안마다 **근접 후보 상위
몇 개만** 돌려준다. 볼트가 커지면 수백 개 목록을 통째로 대조하는 것보다 이쪽이
빠르고 정확하다 — Claude 는 후보 몇 개에 대해서만 "의미가 같은가"를 판단하면 된다.
--extra 는 이번 배치의 앞 청크가 이미 지은 제목(fragments 형식 JSON 파일/폴더)을
대조 대상에 포함시킨다. --match-file 은 {"titles": [...]} 또는 제목 배열을 받는다.

읽기 전용이다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import difflib
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_config  # noqa: E402
from note_utils import compare_key, ensure_relative_folder, nfc  # noqa: E402


def collect(config: dict, limit: int, sort: str) -> dict:
    vault = Path(config["vault"]["path"]).expanduser()
    folder = vault / ensure_relative_folder(config["output"]["fragment_folder"])
    if not folder.exists():
        return {"folder": str(folder), "exists": False, "count": 0, "truncated": False, "titles": []}

    paths = [p for p in folder.rglob("*.md") if p.is_file()]
    if sort == "mtime":
        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    else:
        paths.sort(key=lambda p: nfc(p.stem))

    titles = [nfc(p.stem) for p in paths]
    truncated = len(titles) > limit
    return {
        "folder": str(folder),
        "exists": True,
        "count": len(titles),
        "truncated": truncated,
        "sort": sort,
        "titles": titles[:limit],
    }


def token_set(value: str) -> set[str]:
    """비교용 토큰 — 한글·영문·숫자 연속 2자 이상만 남긴다."""
    return set(re.findall(r"[0-9A-Za-z가-힣]{2,}", compare_key(value)))


def similarity(a: str, b: str) -> float:
    """문자열 유사도와 단어 겹침 중 큰 쪽.

    한국어 제목은 어순이 바뀌어도 같은 생각인 경우가 많아(`믿음과 순종` ↔
    `순종과 믿음`) 글자 순서 기반 SequenceMatcher 만으로는 놓친다. 토큰
    자카드가 그 경우를 잡는다.
    """
    ratio = difflib.SequenceMatcher(None, compare_key(a), compare_key(b)).ratio()
    ta, tb = token_set(a), token_set(b)
    jaccard = len(ta & tb) / len(ta | tb) if (ta or tb) else 0.0
    return max(ratio, jaccard)


def extra_titles(path: Path) -> list[str]:
    """fragments 형식 JSON(파일 또는 폴더)에서 이번 배치가 이미 지은 제목을 모은다."""
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    titles: list[str] = []
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        for entries in data.values():
            if not isinstance(entries, list):
                continue
            for item in entries:
                if isinstance(item, dict) and str(item.get("title") or "").strip():
                    titles.append(nfc(str(item["title"]).strip()))
    return titles


def load_drafts(match_file: str | None, inline: list[str]) -> list[str]:
    drafts = [nfc(d.strip()) for d in inline if d.strip()]
    if match_file:
        data = json.loads(Path(match_file).expanduser().read_text(encoding="utf-8"))
        raw = data.get("titles") if isinstance(data, dict) else data
        if not isinstance(raw, list):
            raise ValueError('match file must be {"titles": [...]} or a JSON array of titles')
        drafts.extend(nfc(str(t).strip()) for t in raw if str(t).strip())
    return list(dict.fromkeys(drafts))


def match(config: dict, drafts: list[str], top: int, threshold: float, extra: str | None) -> dict:
    base = collect(config, limit=1_000_000, sort="name")
    corpus = list(base["titles"])
    extra_count = 0
    if extra:
        added = extra_titles(Path(extra).expanduser())
        extra_count = len(added)
        corpus.extend(added)
    corpus = list(dict.fromkeys(corpus))

    matches: dict[str, list[dict]] = {}
    for draft in drafts:
        scored = sorted(((similarity(draft, title), title) for title in corpus),
                        key=lambda pair: pair[0], reverse=True)
        matches[draft] = [
            {"title": title, "score": round(score, 3),
             "exact": compare_key(title) == compare_key(draft)}
            for score, title in scored[:top] if score >= threshold
        ]
    return {
        "folder": base["folder"],
        "corpus": len(corpus),
        "extra_titles": extra_count,
        "threshold": threshold,
        "matches": matches,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="config JSON path")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--sort", choices=["mtime", "name"], default="name")
    parser.add_argument("--match", action="append", default=[],
                        help="제목 초안 — 근접 후보만 반환 (반복 가능)")
    parser.add_argument("--match-file", help='제목 초안 JSON — {"titles": [...]} 또는 배열')
    parser.add_argument("--top", type=int, default=5, help="초안당 후보 수 (매치 모드)")
    parser.add_argument("--threshold", type=float, default=0.55, help="후보 최소 유사도 (매치 모드)")
    parser.add_argument("--extra", help="이번 배치 청크 JSON(파일/폴더)의 제목도 대조에 포함")
    args = parser.parse_args(argv[1:])

    config = load_config(args.config)
    if args.match or args.match_file:
        drafts = load_drafts(args.match_file, args.match)
        if not drafts:
            print("no draft titles to match", file=sys.stderr)
            return 2
        print(json.dumps(match(config, drafts, args.top, args.threshold, args.extra),
                         ensure_ascii=False, indent=2))
        return 0

    result = collect(config, args.limit, args.sort)
    if result["truncated"]:
        result["note"] = (
            f"조각이 {result['count']}개라 {args.limit}개만 실었습니다. "
            "이럴 때는 목록 대신 매치 모드(--match-file)를 쓰세요 — 전체와 대조합니다."
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
