#!/usr/bin/env python3
"""설교 원본 파일을 스캔하고, 읽으려면 무엇이 필요한지 알려 준다.

    python3 scripts/scan_inputs.py <파일 또는 폴더> [--config config.json]

목회 현장의 원고 폴더는 형식이 섞여 있다 — 워드·한글·PDF·스캔본, 그리고 워드
잠금 파일이나 구글 드라이브 링크 파일처럼 설교가 아닌 것들. 어느 것을 읽을 수 있고,
어느 것은 왜 건너뛰며, 무엇을 설치해야 하는지를 한 번에 보고한다.

읽기 전용이다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_config  # noqa: E402
from ensure_tools import FORMATS, check as check_tools  # noqa: E402
from extract_text import SUPPORTED  # noqa: E402
from note_utils import sidecar_reason  # noqa: E402

SKIP_LABELS = {
    "lock_file": "워드가 문서를 열어 둔 동안 만드는 임시 파일입니다",
    "mac_metadata": "macOS가 남긴 메타데이터 파일입니다",
    "hidden": "숨김 파일입니다",
    "google_stub": "구글 드라이브 링크 파일입니다 — 실제 문서가 아니라 주소 한 줄입니다. "
                   "드라이브에서 '다운로드 → Word(.docx)' 로 내려받아 주세요",
    "empty_or_cloud_placeholder": "0바이트입니다 — 클라우드에서 아직 내려오지 않았을 수 있습니다. "
                                  "파일을 한 번 열어 내려받은 뒤 다시 시도해 주세요",
    "unreadable": "파일 정보를 읽을 수 없습니다",
}


def declared_types(config: dict | None) -> set[str]:
    raw = ((config or {}).get("input", {}) or {}).get("file_types") or []
    return {f".{str(t).lower().lstrip('.')}" for t in raw}


def scan(path: Path, config: dict | None = None) -> dict[str, object]:
    candidates = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
    declared = declared_types(config)

    files: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    by_suffix: dict[str, int] = {}
    undeclared: dict[str, int] = {}

    for p in sorted(candidates):
        suffix = p.suffix.lower()
        reason = sidecar_reason(p)
        if reason:
            skipped.append({"path": str(p), "name": p.name, "reason": reason,
                            "note": SKIP_LABELS.get(reason, "")})
            continue
        if suffix not in SUPPORTED:
            skipped.append({"path": str(p), "name": p.name, "reason": "unsupported_type",
                            "note": f"{suffix or '확장자 없음'} 은 아직 읽지 못합니다. "
                                    ".docx / .hwp / .hwpx / .pdf / .txt / .md 중 하나로 저장해 주세요"})
            continue

        by_suffix[suffix] = by_suffix.get(suffix, 0) + 1
        in_scope = (not declared) or suffix in declared
        if not in_scope:
            undeclared[suffix] = undeclared.get(suffix, 0) + 1
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        files.append({"path": str(p), "name": p.name, "suffix": suffix,
                      "supported": True, "in_config_scope": in_scope, "size": size})

    result: dict[str, object] = {
        "input": str(path),
        "count": len(files) + len(skipped),
        "supported": len(files),
        "by_suffix": dict(sorted(by_suffix.items(), key=lambda kv: -kv[1])),
        "declared_file_types": sorted(s.lstrip(".") for s in declared) if declared else [],
        "skipped": skipped,
        "files": files,
    }

    if undeclared:
        labels = " · ".join(f"{suffix}({count}편)" for suffix, count in undeclared.items())
        result["undeclared_found"] = {suffix.lstrip("."): count for suffix, count in undeclared.items()}
        result["ask_undeclared"] = (f"설정에는 없지만 {labels} 파일이 있습니다. 이 형식도 함께 "
                                    "가져올까요? (설정의 input.file_types 에 추가합니다)")

    # 실제로 발견된 형식만 도구를 점검한다 — 없는 형식 때문에 설치를 권하지 않는다.
    keys = sorted({s.lstrip(".") for s in by_suffix} & set(FORMATS))
    if keys:
        tools = check_tools(keys)
        info: dict[str, object] = {"formats": tools["formats"], "needs_install": tools["needs_install"],
                                   "pylibs": tools["pylibs"], "pip_available": tools["pip_available"]}
        if tools["needs_install"]:
            info["install_cmd"] = tools.get("install_cmd", "")
            result["ask_install"] = tools.get("ask", "")
        result["tools"] = info

    if not files:
        result["note"] = "읽을 수 있는 설교 파일을 찾지 못했습니다. 건너뛴 목록(skipped)의 이유를 확인해 주세요."
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="설교 원본 스캔")
    parser.add_argument("input")
    parser.add_argument("--config", help="config.json 경로 (input.file_types 범위 판정용)")
    args = parser.parse_args(argv[1:])

    path = Path(args.input).expanduser()
    if not path.exists():
        print(json.dumps({"error": f"경로를 찾을 수 없습니다: {path}"}, ensure_ascii=False))
        return 1
    config = load_config(args.config) if args.config else None
    print(json.dumps(scan(path, config), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
