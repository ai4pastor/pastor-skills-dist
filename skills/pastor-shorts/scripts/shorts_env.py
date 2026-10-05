#!/usr/bin/env python3
"""쇼츠 스킬의 경로 계약. 표준 라이브러리만 쓴다 (시스템 python3 3.8+ 에서도 import 가능).

설정 홈은 다른 목회자 스킬과 같은 곳(~/.pastor-sermon-import, PASTOR_SERMON_IMPORT_HOME
으로 재정의)을 쓰고, 쇼츠 전용 파일은 그 아래 shorts/ 에 모은다.

    <홈>/shorts/venv/    스킬 전용 파이썬 환경 (uv 가 만든다 — 시스템 파이썬 무오염)
    <홈>/shorts/fonts/   OFL 글꼴 (Pretendard·나눔명조·Marcellus)
    <홈>/shorts/cache/   설교 대본 캐시 (영상 sha256 기준)
    <홈>/shorts_rules.md 나만의 규칙 (업데이트에 안전)
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import HOME_ENV_VAR, home  # noqa: E402

PYTHON_VERSION = "3.12"


def shorts_home() -> Path:
    return home() / "shorts"


def venv_dir() -> Path:
    return shorts_home() / "venv"


def venv_python() -> Path:
    if os.name == "nt":
        return venv_dir() / "Scripts" / "python.exe"
    return venv_dir() / "bin" / "python"


def venv_bin(name: str) -> Path:
    if os.name == "nt":
        return venv_dir() / "Scripts" / (name + ".exe")
    return venv_dir() / "bin" / name


def fonts_dir() -> Path:
    return shorts_home() / "fonts"


def cache_dir() -> Path:
    return shorts_home() / "cache"


def rules_path() -> Path:
    return home() / "shorts_rules.md"


def default_work_root() -> Path:
    """작업 폴더 기본값 — 맥은 '동영상(Movies)', 윈도우·리눅스는 Videos 폴더 아래."""
    user = Path.home()
    if platform.system() == "Darwin":
        return user / "Movies" / "설교쇼츠"
    return user / "Videos" / "설교쇼츠"


def whisper_backend() -> str:
    """애플실리콘 맥은 mlx-whisper(빠름), 그 밖은 faster-whisper(CPU/GPU 공용)."""
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "mlx"
    return "faster"


def describe() -> dict:
    return {
        "home": str(home()),
        "shorts_home": str(shorts_home()),
        "venv_python": str(venv_python()),
        "venv_ready": venv_python().exists(),
        "fonts_dir": str(fonts_dir()),
        "cache_dir": str(cache_dir()),
        "shorts_rules": str(rules_path()),
        "shorts_rules_exists": rules_path().exists(),
        "default_work_root": str(default_work_root()),
        "whisper_backend": whisper_backend(),
        "platform": f"{platform.system()} {platform.machine()}",
        "env_var": HOME_ENV_VAR,
        "overridden": bool(os.environ.get(HOME_ENV_VAR)),
    }


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔에서 한글 출력 (sermon_shorts.py 와 같게)
    except (AttributeError, ValueError):
        pass
    print(json.dumps(describe(), ensure_ascii=False, indent=2))
