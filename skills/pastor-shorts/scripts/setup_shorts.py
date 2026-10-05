#!/usr/bin/env python3
"""쇼츠 제작 도구를 점검하고, 스킬 전용 환경에 설치한다. 표준 라이브러리만 쓴다.

    python3 scripts/setup_shorts.py --check        # 전체 점검 (JSON)
    python3 scripts/setup_shorts.py --install-uv   # uv 설치 (공식 설치 명령, 승인 후에만)
    python3 scripts/setup_shorts.py --install      # 전용 파이썬 환경 + 패키지 + 글꼴

설치 계약 (다른 목회자 스킬과 같은 원칙):
- 목사님 시스템 파이썬과 시스템 패키지는 건드리지 않는다. 관리자 권한도 필요 없다.
- uv 가 <홈>/shorts/venv 에 파이썬 3.12 환경을 따로 만든다 (파이썬도 uv 가 받아 온다).
- ffmpeg 은 시스템에 설치하지 않는다 — imageio-ffmpeg 휠에 들어 있는 실행 파일을 쓴다.
- 글꼴은 OFL(자유 글꼴) 공식 배포처에서 <홈>/shorts/fonts 로만 받는다.
- 음성 인식 모델(약 1.5GB)은 첫 대본 만들기 때 자동으로 한 번 받는다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import shorts_env as env  # noqa: E402

UV_INSTALL = {
    "unix": 'curl -LsSf https://astral.sh/uv/install.sh | sh',
    "windows": 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
}

COMMON_PACKAGES = ["pillow>=10", "numpy", "imageio-ffmpeg>=0.5", "yt-dlp[default]", "deno"]
BACKEND_PACKAGES = {"mlx": ["mlx-whisper>=0.4"], "faster": ["faster-whisper>=1.1"]}
MODULES = {"PIL": "pillow", "numpy": "numpy", "imageio_ffmpeg": "imageio-ffmpeg", "yt_dlp": "yt-dlp",
           "yt_dlp_ejs": "yt-dlp-ejs"}
BACKEND_MODULE = {"mlx": "mlx_whisper", "faster": "faster_whisper"}

PRETENDARD = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/"
GOOGLE_FONTS = "https://github.com/google/fonts/raw/main/ofl/"
FONT_FILES = {
    **{f"Pretendard-{w}.otf": f"{PRETENDARD}packages/pretendard/dist/public/static/Pretendard-{w}.otf"
       for w in ("Light", "Regular", "Medium", "SemiBold", "ExtraBold")},
    **{f"NanumMyeongjo-{w}.ttf": f"{GOOGLE_FONTS}nanummyeongjo/NanumMyeongjo-{w}.ttf"
       for w in ("Regular", "Bold", "ExtraBold")},
    "Marcellus-Regular.ttf": f"{GOOGLE_FONTS}marcellus/Marcellus-Regular.ttf",
}
FONT_LICENSES = {
    "LICENSE-Pretendard.txt": f"{PRETENDARD}LICENSE",
    "OFL-NanumMyeongjo.txt": f"{GOOGLE_FONTS}nanummyeongjo/OFL.txt",
    "OFL-Marcellus.txt": f"{GOOGLE_FONTS}marcellus/OFL.txt",
}

FFMPEG_FILTERS = ["silencedetect", "loudnorm", "ebur128", "gblur", "alphamerge", "overlay", "concat", "afade"]


def find_uv() -> str | None:
    found = shutil.which("uv")
    if found:
        return found
    for cand in (Path.home() / ".local/bin/uv", Path.home() / ".cargo/bin/uv",
                 Path.home() / ".local/bin/uv.exe", Path.home() / ".cargo/bin/uv.exe"):
        if cand.exists():
            return str(cand)
    return None


def run(cmd: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    # uv·전용 파이썬의 출력은 UTF-8 로 읽는다. 한국어 윈도우 기본값(cp949)으로 읽으면
    # 사용자 이름(홈 폴더 이름)이 한글일 때 UnicodeDecodeError 로 설치가 멈춘다.
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def venv_probe() -> dict:
    """전용 환경 안에서 모듈·ffmpeg·deno 를 확인한다."""
    py = env.venv_python()
    if not py.exists():
        return {"ready": False}
    backend = env.whisper_backend()
    code = (
        "import importlib.util, json, sys, subprocess, shutil\n"
        f"mods = {json.dumps(list(MODULES) + [BACKEND_MODULE[backend]])}\n"
        "out = {'python': sys.version.split()[0], 'modules': {m: importlib.util.find_spec(m) is not None for m in mods}}\n"
        "try:\n"
        "    import imageio_ffmpeg\n"
        "    exe = imageio_ffmpeg.get_ffmpeg_exe()\n"
        "    out['ffmpeg'] = exe\n"
        "    f = subprocess.run([exe, '-hide_banner', '-filters'], capture_output=True, text=True).stdout\n"
        "    e = subprocess.run([exe, '-hide_banner', '-encoders'], capture_output=True, text=True).stdout\n"
        f"    out['filters_missing'] = [x for x in {json.dumps(FFMPEG_FILTERS)} if (' ' + x + ' ') not in f]\n"
        "    out['libx264'] = ' libx264 ' in e\n"
        "except Exception as exc:\n"
        "    out['ffmpeg_error'] = str(exc)\n"
        "print(json.dumps(out))\n"
    )
    res = run([str(py), "-c", code], timeout=120)
    try:
        info = json.loads(res.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ready": False, "error": (res.stderr or res.stdout)[-400:]}
    deno = env.venv_bin("deno")
    info["deno"] = str(deno) if deno.exists() else None
    info["ready"] = (all(info.get("modules", {}).values()) and bool(info.get("ffmpeg"))
                     and not info.get("filters_missing") and bool(info.get("libx264")) and bool(info["deno"]))
    return info


def font_status() -> dict:
    d = env.fonts_dir()
    missing = [name for name in FONT_FILES if not (d / name).is_file()]
    return {"dir": str(d), "missing": missing, "ready": not missing}


def check() -> dict:
    uv = find_uv()
    venv = venv_probe()
    fonts = font_status()
    needs = []
    if not uv and not venv.get("ready"):
        needs.append("uv")
    if not venv.get("ready"):
        needs.append("venv")
    if not fonts["ready"]:
        needs.append("fonts")
    free_gb = round(shutil.disk_usage(Path.home()).free / 1e9, 1)
    return {
        "ready": not needs,
        "needs": needs,
        "python": str(env.venv_python()),
        "uv": uv,
        "uv_install_command": UV_INSTALL["windows" if os.name == "nt" else "unix"],
        "venv": venv,
        "fonts": fonts,
        "whisper_backend": env.whisper_backend(),
        "disk_free_gb": free_gb,
        "disk_note": "설치 약 1GB + 음성 인식 모델 약 1.5GB(첫 대본 때) + 영상 작업 공간이 필요합니다."
                     if free_gb < 10 else "",
        "platform": f"{platform.system()} {platform.machine()}",
    }


def download(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if curl:
        ok = run([curl, "-fsSL", "--retry", "2", "-o", str(tmp), url], timeout=600).returncode == 0
    else:  # curl 이 없는 드문 환경 — 표준 라이브러리로 받는다
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
            ok = True
        except Exception:
            ok = False
    if ok and tmp.stat().st_size > 1000:
        tmp.replace(dest)
        return True
    if tmp.exists():
        tmp.unlink()
    return False


def install_uv() -> dict:
    if find_uv():
        return {"ok": True, "uv": find_uv(), "note": "이미 설치되어 있습니다."}
    if os.name == "nt":
        cmd = ["powershell", "-ExecutionPolicy", "ByPass", "-c", "irm https://astral.sh/uv/install.ps1 | iex"]
    else:
        cmd = ["sh", "-c", UV_INSTALL["unix"]]
    res = run(cmd, timeout=600)
    return {"ok": bool(find_uv()), "uv": find_uv(), "log": (res.stdout + res.stderr)[-600:]}


def install() -> dict:
    steps = []
    uv = find_uv()
    if not uv:
        return {"ok": False, "needs": ["uv"], "message": "uv 가 없습니다. 먼저 --install-uv 를 승인받아 실행하세요.",
                "uv_install_command": UV_INSTALL["windows" if os.name == "nt" else "unix"]}
    if not env.venv_python().exists():
        res = run([uv, "venv", str(env.venv_dir()), "--python", env.PYTHON_VERSION])
        steps.append({"step": "venv", "ok": res.returncode == 0, "log": (res.stdout + res.stderr)[-400:]})
        if res.returncode != 0:
            return {"ok": False, "steps": steps}
    packages = COMMON_PACKAGES + BACKEND_PACKAGES[env.whisper_backend()]
    res = run([uv, "pip", "install", "--python", str(env.venv_python()), *packages], timeout=3600)
    steps.append({"step": "packages", "ok": res.returncode == 0, "packages": packages,
                  "log": (res.stdout + res.stderr)[-600:]})
    fonts_ok = True
    for name, url in {**FONT_FILES, **FONT_LICENSES}.items():
        dest = env.fonts_dir() / name
        if dest.is_file():
            continue
        if not download(url, dest) and name in FONT_FILES:
            fonts_ok = False
            steps.append({"step": "font", "ok": False, "file": name, "url": url})
    steps.append({"step": "fonts", "ok": fonts_ok, "dir": str(env.fonts_dir())})
    env.cache_dir().mkdir(parents=True, exist_ok=True)
    report = check()
    return {"ok": report["ready"], "steps": steps, "check": report}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--install-uv", action="store_true")
    g.add_argument("--install", action="store_true")
    a = p.parse_args(argv[1:])
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔에서 한글 출력 (sermon_shorts.py 와 같게)
    except (AttributeError, ValueError):
        pass
    out = check() if a.check else install_uv() if a.install_uv else install()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ready", out.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
