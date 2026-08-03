#!/usr/bin/env python3
"""설교 원고가 있을 만한 곳과 옵시디언 볼트를 컴퓨터에서 찾아 준다.

    python3 scripts/find_sources.py --vaults          # 옵시디언 볼트 후보
    python3 scripts/find_sources.py                   # 설교 원고 폴더 후보
    python3 scripts/find_sources.py --root "경로"     # 특정 폴더만 훑기

목사님께 경로를 타이핑하게 하지 않기 위한 스크립트다. 설교 원고는 볼트 안에만
있지 않다 — 구글 드라이브·원드라이브·드롭박스·iCloud·문서·다운로드에 흩어져 있고
형식도 워드·한글·PDF가 섞여 있다. 그래서 폴더마다 형식별 개수와 최근 수정일을 함께
보고한다.

읽기 전용이다. 시간·탐색량 예산을 두고, 예산을 넘기면 truncated 로 알린다.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
import argparse
import json
import os
import platform
import sys
import time

DOC_SUFFIXES = {".docx", ".doc", ".hwp", ".hwpx", ".pdf", ".txt", ".md", ".rtf", ".odt", ".pages"}
READABLE_SUFFIXES = {".docx", ".hwp", ".hwpx", ".pdf", ".txt", ".md"}
SERMON_WORDS = ("설교", "말씀", "주일", "예배", "기도회", "새벽", "수요", "금요", "강해",
                "sermon", "preach", "성경공부", "심방", "집회")
SKIP_NAMES = {"node_modules", "__pycache__", "Library", "Applications", "Movies", "Music",
              "Pictures", "Public", "site-packages", "venv", ".venv", "AppData", "Program Files"}
# 이 이름들은 Library 아래라도 훑는다 (클라우드 동기화 위치)
CLOUD_KEEP = ("CloudStorage", "Mobile Documents")

MAX_DEPTH = 3
VAULT_MAX_DEPTH = 4
DIR_BUDGET = 20_000
TIME_BUDGET_SEC = 20.0


def label_for(path: Path) -> str:
    name = path.name.lower()
    text = str(path).lower()
    if path == Path.home():
        # 홈 폴더 이름은 사용자 계정명이다 — 화면에 계정명을 띄우지 않는다.
        return "홈 폴더"
    if "cloudstorage" in text or "google" in text or "드라이브" in str(path):
        if "onedrive" in text:
            return "원드라이브"
        if "dropbox" in text:
            return "드롭박스"
        return "구글 드라이브"
    if "onedrive" in text:
        return "원드라이브"
    if "dropbox" in text:
        return "드롭박스"
    if "mobile documents" in text or "clouddocs" in text:
        return "iCloud Drive"
    if name in {"documents", "문서"}:
        return "문서"
    if name in {"downloads", "다운로드"}:
        return "다운로드"
    if name in {"desktop", "바탕화면"}:
        return "바탕화면"
    return path.name or str(path)


def search_roots(extra: list[str] | None = None) -> list[Path]:
    """훑을 최상위 폴더들. 없는 경로는 뒤에서 걸러진다."""
    home = Path.home()
    roots: list[Path] = []
    if extra:
        roots += [Path(e).expanduser() for e in extra]
        return roots

    roots += [home / "Documents", home / "Desktop", home / "Downloads"]
    roots += [home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"]
    cloud = home / "Library" / "CloudStorage"
    if cloud.is_dir():
        roots += sorted(p for p in cloud.iterdir() if p.is_dir())
    for pattern in ("Google Drive*", "GoogleDrive*", "OneDrive*", "Dropbox*",
                    "내 드라이브*", "구글 드라이브*", "내 문서*"):
        roots += sorted(home.glob(pattern))
    if os.name == "nt":
        # 구글 드라이브 데스크톱은 보통 별도 드라이브 문자로 붙는다.
        for letter in "DEFGHIJKL":
            for name in ("내 드라이브", "My Drive"):
                roots.append(Path(f"{letter}:/") / name)
    roots.append(home)
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        out.append(root)
    return out


def skip_dir(path: Path, root: Path) -> bool:
    name = path.name
    if name.startswith(".") or name.startswith("~"):
        return True
    if name in SKIP_NAMES:
        # 클라우드 동기화 폴더는 Library 아래에 있어 예외로 둔다.
        return not any(keep in str(path) for keep in CLOUD_KEEP)
    return False


class Budget:
    def __init__(self) -> None:
        self.dirs = 0
        self.started = time.monotonic()
        self.exhausted = False

    def spend(self) -> bool:
        self.dirs += 1
        if self.dirs > DIR_BUDGET or (time.monotonic() - self.started) > TIME_BUDGET_SEC:
            self.exhausted = True
            return False
        return True


def walk(root: Path, max_depth: int, budget: Budget):
    """(폴더, 깊이) 를 너비 우선으로. 예산을 넘기면 멈춘다."""
    if not root.is_dir():
        return
    queue = deque([(root, 0)])
    while queue:
        current, depth = queue.popleft()
        if not budget.spend():
            return
        yield current, depth
        if depth >= max_depth:
            continue
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            child = Path(entry.path)
            if skip_dir(child, root):
                continue
            queue.append((child, depth + 1))


def inspect_folder(folder: Path) -> dict | None:
    """문서 파일 개수·형식·최근 수정일. 문서가 없으면 None."""
    by_suffix: dict[str, int] = {}
    latest = 0.0
    samples: list[str] = []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return None
    for entry in entries:
        try:
            if not entry.is_file(follow_symlinks=False):
                continue
        except OSError:
            continue
        name = entry.name
        if name.startswith(("~$", "._", ".")):
            continue
        suffix = Path(name).suffix.lower()
        if suffix not in DOC_SUFFIXES:
            continue
        by_suffix[suffix] = by_suffix.get(suffix, 0) + 1
        try:
            latest = max(latest, entry.stat().st_mtime)
        except OSError:
            pass
        if len(samples) < 6:
            samples.append(name)
    if not by_suffix:
        return None
    documents = sum(by_suffix.values())
    readable = sum(count for suffix, count in by_suffix.items() if suffix in READABLE_SUFFIXES)
    return {"by_suffix": dict(sorted(by_suffix.items(), key=lambda kv: -kv[1])),
            "documents": documents, "readable": readable, "samples": samples,
            "latest_modified": time.strftime("%Y-%m-%d", time.localtime(latest)) if latest else ""}


def score_folder(folder: Path, info: dict) -> tuple[int, list[str]]:
    why: list[str] = []
    score = 0
    text = str(folder).lower()
    leaf = folder.name.lower()
    for word in SERMON_WORDS:
        if word in leaf:
            score += 6
            why.append(f"폴더 이름에 '{word}'")
            break
    else:
        for word in SERMON_WORDS:
            if word in text:
                score += 3
                why.append(f"상위 폴더 경로에 '{word}'")
                break
    hits = sum(1 for name in info["samples"] if any(word in name.lower() for word in SERMON_WORDS))
    if hits:
        score += 2 * hits
        why.append(f"파일 이름에 설교 관련 단어 {hits}개")
    score += min(info["documents"], 20) // 4
    return score, why


def find_sermon_folders(roots: list[Path], limit: int) -> dict[str, object]:
    budget = Budget()
    candidates: list[dict] = []
    seen: set[Path] = set()
    root_report: list[dict] = []

    for root in roots:
        exists = root.is_dir()
        root_report.append({"path": str(root), "label": label_for(root), "exists": exists})
        if not exists:
            continue
        for folder, _depth in walk(root, MAX_DEPTH, budget):
            if folder in seen:
                continue
            seen.add(folder)
            info = inspect_folder(folder)
            if not info:
                continue
            score, why = score_folder(folder, info)
            # 설교 신호가 없고 문서도 적으면 후보에서 뺀다 — 목록이 길어지면 못 고른다.
            if score < 4 and info["documents"] < 5:
                continue
            candidates.append({"path": str(folder), "where": label_for(root), "score": score,
                               "why": why, **info})

    candidates.sort(key=lambda r: (-r["score"], -r["documents"], r["path"]))
    result: dict[str, object] = {
        "platform": platform.system(),
        "roots": [r for r in root_report if r["exists"]],
        "roots_missing": [r["path"] for r in root_report if not r["exists"]],
        "candidates": candidates[:limit],
        "candidate_count": len(candidates),
        "truncated": budget.exhausted,
        "scanned_folders": budget.dirs,
    }
    if budget.exhausted:
        result["note_truncated"] = ("탐색 예산을 넘겨 일부만 훑었습니다. 원고가 있는 폴더를 아시면 "
                                   "--root 로 그 폴더만 지정해 주세요.")
    if not candidates:
        result["note"] = ("설교 원고 폴더를 찾지 못했습니다. 목사님께 폴더를 여쭤보시고, 클라우드라면 "
                          "먼저 컴퓨터에 동기화(또는 내려받기)되어 있어야 읽을 수 있다고 알려 주세요.")
    return result


def find_vaults(roots: list[Path], limit: int) -> dict[str, object]:
    budget = Budget()
    vaults: list[dict] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for folder, _depth in walk(root, VAULT_MAX_DEPTH, budget):
            marker = folder / ".obsidian"
            if not marker.is_dir() or folder in seen:
                continue
            seen.add(folder)
            try:
                notes = sum(1 for p in folder.rglob("*.md") if p.is_file())
            except OSError:
                notes = 0
            vaults.append({"path": str(folder), "where": label_for(root), "notes": notes,
                           "has_templates_setting": (marker / "templates.json").is_file()})
    vaults.sort(key=lambda r: -r["notes"])
    result: dict[str, object] = {
        "platform": platform.system(),
        "vaults": vaults[:limit],
        "vault_count": len(vaults),
        "truncated": budget.exhausted,
        "scanned_folders": budget.dirs,
    }
    if not vaults:
        result["note"] = ("옵시디언 볼트를 찾지 못했습니다. 옵시디언에서 볼트 이름을 오른쪽 클릭 → "
                          "'Reveal in Finder'(윈도우: '탐색기에서 보기')로 경로를 확인해 여쭤보세요.")
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="설교 원고 폴더·옵시디언 볼트 탐색")
    parser.add_argument("--vaults", action="store_true", help="옵시디언 볼트를 찾는다")
    parser.add_argument("--root", action="append", default=[], help="이 폴더만 훑는다 (여러 번 지정 가능)")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv[1:])

    roots = search_roots(args.root or None)
    result = find_vaults(roots, args.limit) if args.vaults else find_sermon_folders(roots, args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
