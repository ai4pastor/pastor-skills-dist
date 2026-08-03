#!/usr/bin/env python3
"""설교 원고 형식별 변환 도구를 점검하고, 스킬 전용 폴더에 설치한다.

    python3 scripts/ensure_tools.py --check            # 전체 점검 (JSON)
    python3 scripts/ensure_tools.py --check pdf,hwp    # 형식만 골라 점검
    python3 scripts/ensure_tools.py --install pdf,hwp  # 격리 설치
    python3 scripts/ensure_tools.py --explain          # 계약 설명

설치는 `pip install --target <home>/tools/pylibs` 로만 한다. 목사님 시스템
파이썬을 건드리지 않고 관리자 권한도 필요 없다(윈도우 포함). `--prefer-binary` 로
가능하면 휠을 받고, 실패하면 형식별 수동 방법(한글에서 .txt 저장 등)을 안내한다.

시스템 도구(pandoc·poppler)는 **설치하지 않는다.** 있으면 품질이 더 좋아 먼저 쓰고,
없으면 파이썬 대안으로 우회한다. 목사님 컴퓨터에 시스템 패키지를 밀어 넣는 일은
스킬이 할 일이 아니다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import importlib.util
import json
import platform
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import pylibs_dir  # noqa: E402

# 형식별 계약. command = 있으면 먼저 쓰는 시스템 도구, module = pip 로 넣을 수 있는 대안.
FORMATS: dict[str, dict[str, object]] = {
    "md": {
        "label": ".md (마크다운)",
        "commands": [],
        "modules": [],
        "pip": [],
        "builtin": True,
    },
    "txt": {
        "label": ".txt (서식 없는 텍스트)",
        "commands": [],
        "modules": [],
        "pip": [],
        "builtin": True,
    },
    "hwpx": {
        "label": ".hwpx (한글 표준 문서)",
        "commands": [],
        "modules": [],
        "pip": [],
        "builtin": True,
    },
    "docx": {
        "label": ".docx (워드)",
        "commands": ["pandoc"],
        "modules": ["docx"],
        "pip": ["python-docx"],
        "manual": "워드에서 그 설교를 열고 '다른 이름으로 저장 → 서식 없는 텍스트(*.txt)'로 "
                  "저장해 주세요. .txt는 추가 도구 없이 바로 읽습니다.",
    },
    "pdf": {
        "label": ".pdf",
        "commands": ["pdftotext"],
        "modules": ["pypdf"],
        "pip": ["pypdf"],
        "manual": "PDF를 열고 본문을 복사해 메모장에 붙여 .txt로 저장해 주셔도 됩니다.",
    },
    "hwp": {
        "label": ".hwp (한글)",
        "commands": [],
        "modules": ["hwp5"],
        # six 를 함께 적는 이유: pyhwp 0.1b15 는 런타임에 six 를 import 하면서
        # 의존성으로는 선언하지 않는다. 빼면 설치는 성공하고 실행만 실패한다.
        "pip": ["pyhwp", "six"],
        "manual": "한글에서 그 설교를 열고 '다른 이름으로 저장 → 텍스트 문서(*.txt)'로 "
                  "저장해 주세요. .hwpx로 저장하셔도 추가 도구 없이 읽습니다.",
    },
}

BUILTIN_NOTE = "추가 도구가 필요하지 않습니다."


def activate_pylibs() -> Path:
    """격리 설치 폴더를 import 경로 앞에 둔다.

    시스템 파이썬에 아무것도 설치하지 않고도 pypdf·pyhwp 를 쓰기 위한 장치다.
    폴더가 없으면 아무 일도 하지 않는다(경로만 알려준다).
    """
    target = pylibs_dir()
    path = str(target)
    if target.is_dir() and path not in sys.path:
        sys.path.insert(0, path)
    return target


def module_available(name: str) -> bool:
    activate_pylibs()
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def install_hint(keys: list[str]) -> str:
    return f"python3 scripts/ensure_tools.py --install {','.join(keys)}"


def check(keys: list[str]) -> dict[str, object]:
    pylibs = activate_pylibs()
    formats: dict[str, object] = {}
    needs: list[str] = []

    for key in keys:
        spec = FORMATS[key]
        if spec.get("builtin"):
            formats[key] = {"label": spec["label"], "available": True, "via": "표준 기능",
                            "missing": [], "note": BUILTIN_NOTE}
            continue

        via = ""
        for command in spec.get("commands", []):  # type: ignore[union-attr]
            if shutil.which(str(command)):
                via = f"{command} (설치되어 있음)"
                break
        if not via:
            for module in spec.get("modules", []):  # type: ignore[union-attr]
                if module_available(str(module)):
                    via = f"{module} (파이썬 모듈)"
                    break

        available = bool(via)
        if not available:
            needs.append(key)
        formats[key] = {
            "label": spec["label"],
            "available": available,
            "via": via,
            "missing": [] if available else list(spec.get("pip", [])),  # type: ignore[arg-type]
            "manual_fallback": spec.get("manual", ""),
        }

    result: dict[str, object] = {
        "python": sys.executable,
        "platform": platform.system(),
        "pylibs": str(pylibs),
        "pylibs_exists": pylibs.is_dir(),
        "pip_available": pip_available(),
        "formats": formats,
        "needs_install": needs,
    }
    if needs:
        result["install_cmd"] = install_hint(needs)
        packages = sorted({p for key in needs for p in FORMATS[key].get("pip", [])})  # type: ignore[union-attr]
        result["packages"] = packages
        result["ask"] = ("설교 원고를 읽기 위해 " + " · ".join(str(FORMATS[k]["label"]) for k in needs)
                         + " 변환 도구가 필요합니다. 스킬 전용 폴더에만 설치하고 "
                           "목사님 컴퓨터의 다른 설정은 건드리지 않습니다. 설치할까요?")
    else:
        result["ask"] = ""
    if not result["pip_available"]:
        result["pip_note"] = ("이 파이썬에는 pip 가 없어 자동 설치를 할 수 없습니다. "
                              "형식별 수동 방법(manual_fallback)을 안내해 주세요.")
    return result


def pip_available() -> bool:
    try:
        proc = subprocess.run([sys.executable, "-m", "pip", "--version"],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def install(keys: list[str]) -> dict[str, object]:
    packages = sorted({str(p) for key in keys for p in FORMATS[key].get("pip", [])})  # type: ignore[union-attr]
    target = pylibs_dir()
    if not packages:
        return {"status": "nothing_to_do", "formats": keys,
                "note": "이 형식들은 추가 도구 없이 읽습니다."}
    if not pip_available():
        return {"status": "error", "error": "pip_missing", "packages": packages,
                "note": "이 파이썬에는 pip 가 없습니다. 형식별 수동 방법을 안내해 주세요.",
                "manual": {key: FORMATS[key].get("manual", "") for key in keys}}

    target.mkdir(parents=True, exist_ok=True)
    # --prefer-binary: 휠이 있으면 휠을 쓴다(컴파일 없음). pyhwp 는 휠을 배포하지
    # 않아 --only-binary 로 막으면 아예 설치가 안 되므로, 금지가 아니라 선호로 둔다.
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-input",
           "--disable-pip-version-check", "--prefer-binary",
           "--target", str(target), *packages]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "timeout", "cmd": cmd, "packages": packages,
                "note": "설치가 10분을 넘겨 중단했습니다. 인터넷 연결을 확인해 주세요."}

    after = check(keys)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-8:])
        return {"status": "error", "error": "pip_failed", "returncode": proc.returncode,
                "packages": packages, "target": str(target), "stderr_tail": tail,
                "manual": {key: FORMATS[key].get("manual", "") for key in keys},
                "check": after}
    return {"status": "ok", "packages": packages, "target": str(target),
            "installed_into_system_python": False, "check": after}


def parse_keys(raw: str | None) -> list[str]:
    """형식 목록 파싱. 모르는 형식은 stdout 으로 오류 JSON 을 내고 종료한다.

    다른 스크립트와 같은 규약이다 — 스킬은 stdout 만 읽으므로, 오류를 stderr 로
    보내면 Claude 쪽에서 그냥 "빈 응답"으로 보인다.
    """
    if not raw:
        return list(FORMATS)
    keys = [k.strip().lower().lstrip(".") for k in raw.split(",") if k.strip()]
    unknown = [k for k in keys if k not in FORMATS]
    if unknown:
        print(json.dumps({"status": "error", "error": f"unknown formats: {', '.join(unknown)}",
                          "known": list(FORMATS)}, ensure_ascii=False))
        raise SystemExit(2)
    return keys


EXPLAIN = {
    "설치 위치": "<PASTOR_SERMON_IMPORT_HOME 또는 ~/.pastor-sermon-import>/tools/pylibs",
    "설치 방법": "pip install --target <위 폴더> — 시스템 파이썬·사용자 site-packages 를 건드리지 않는다",
    "설치하지 않는 것": "pandoc·poppler 등 시스템 도구. 있으면 먼저 쓰고, 없으면 파이썬 대안으로 우회한다",
    "형식별 경로": {key: {"먼저": spec.get("commands") or "표준 기능",
                          "대안": spec.get("modules") or "-",
                          "pip": spec.get("pip") or "-"} for key, spec in FORMATS.items()},
    "승인": "스킬은 --check 결과의 ask 문구로 목사님께 먼저 여쭙고, 승인 뒤에만 --install 을 실행한다",
}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="설교 원고 변환 도구 점검·설치")
    parser.add_argument("--check", nargs="?", const="", metavar="형식목록")
    parser.add_argument("--install", metavar="형식목록")
    parser.add_argument("--explain", action="store_true")
    args = parser.parse_args(argv[1:])

    if args.explain:
        print(json.dumps(EXPLAIN, ensure_ascii=False, indent=2))
        return 0
    if args.install:
        result = install(parse_keys(args.install))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") in {"ok", "nothing_to_do"} else 1

    result = check(parse_keys(args.check))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
