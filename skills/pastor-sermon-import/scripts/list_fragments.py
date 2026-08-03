#!/usr/bin/env python3
"""목사님 볼트에 이미 있는 조각 제목 목록을 출력한다.

    python3 scripts/list_fragments.py --config "{config}" [--limit 500] [--sort mtime|name]

Step 3 앞에서 호출한다. 이 목록이 프롬프트에 들어가야 Claude 가 "의미가 같은
조각은 기존 제목을 글자 그대로 재사용"할 수 있다. 목록 없이 분해하면 같은
생각이 조금 다른 제목으로 두 벌 생긴다.

읽기 전용이다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_config  # noqa: E402
from note_utils import ensure_relative_folder, nfc  # noqa: E402


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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="config JSON path")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--sort", choices=["mtime", "name"], default="name")
    args = parser.parse_args(argv[1:])

    config = load_config(args.config)
    result = collect(config, args.limit, args.sort)
    if result["truncated"]:
        result["note"] = (
            f"조각이 {result['count']}개라 {args.limit}개만 실었습니다. "
            "목록에 없는 조각과 제목이 겹칠 수 있으니 보고에 남기세요."
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
