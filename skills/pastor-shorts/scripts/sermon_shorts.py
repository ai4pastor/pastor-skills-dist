#!/usr/bin/env python3
"""설교 영상 → 유튜브 쇼츠 제작 도구. 스킬 전용 파이썬(setup_shorts.py 가 알려 주는 python)으로 실행한다.

    PY scripts/sermon_shorts.py fetch <유튜브 주소> [--root 폴더]
    PY scripts/sermon_shorts.py use <영상 파일> [--root 폴더] [--title 제목]
    PY scripts/sermon_shorts.py transcribe --project 폴더 [--model turbo|small|medium]
    PY scripts/sermon_shorts.py transcript --project 폴더 [--from 12:30 --to 14:00] [--words]
    PY scripts/sermon_shorts.py pauses --project 폴더 --from 24:24 --to 25:37 [--remove "뺄 말" ...]
    PY scripts/sermon_shorts.py frame --project 폴더 --at 25:15 [--grid]
    PY scripts/sermon_shorts.py preview --clip 폴더/clips/01.json
    PY scripts/sermon_shorts.py render --clip 폴더/clips/01.json --design 1|2|3|4|all
    PY scripts/sermon_shorts.py compare --clip 폴더/clips/01.json
    PY scripts/sermon_shorts.py validate --video 결과.mp4 [--title ...] [--hashtags "#a #b"] [--has-music]

원본 영상은 읽기만 한다. 결과 파일은 덮어쓰지 않는다(같은 이름이면 _2, _3 …). 출력은 JSON.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

import os  # noqa: E402

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")  # 모델 받기 진행 표시줄이 JSON 출력에 섞이지 않게
os.environ.setdefault("TQDM_DISABLE", "1")

import shorts_env as env  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔에서 한글 출력
except (AttributeError, ValueError):
    pass

MODELS = {
    "mlx": {"turbo": "mlx-community/whisper-large-v3-turbo", "small": "mlx-community/whisper-small-mlx",
            "medium": "mlx-community/whisper-medium-mlx"},
    "faster": {"turbo": "turbo", "small": "small", "medium": "medium"},
}
SHORTS_MAX_SECONDS = 180  # 2024-10-15 이후 세로·정사각형 3분 이하 = 쇼츠 (YouTube 도움말, 2026-10-02 확인)


# ---------- 공통 ----------
def out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ff(args: list[str]) -> None:
    res = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args],
                         capture_output=True, text=True, errors="replace")
    if res.returncode != 0:
        raise RuntimeError("ffmpeg 실패: " + res.stderr[-800:])


def probe(path: Path) -> dict:
    res = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                         errors="replace")
    err = res.stderr
    info = {"path": str(path)}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if m:
        info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.search(r"Video:.*?, (\d{2,5})x(\d{2,5})[ ,\[]", err)
    if m:
        info["width"], info["height"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"Video:.*?(\d+(?:\.\d+)?) fps", err)
    if m:
        info["fps"] = float(m.group(1))
    m = re.search(r"Video: (\w+)", err)
    info["video_codec"] = m.group(1) if m else None
    m = re.search(r"Audio: (\w+)", err)
    info["audio_codec"] = m.group(1) if m else None
    info["size_bytes"] = path.stat().st_size if path.exists() else 0
    return info


def seconds(text: str) -> float:
    """'25:37' · '1:02:03' · '1537.2' 를 초로."""
    text = str(text).strip()
    if ":" not in text:
        return float(text)
    parts = [float(p) for p in text.split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def mmss(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def unique(path: Path, replace: bool = False) -> Path:
    if replace or not path.exists():
        return path
    n = 2
    while True:
        cand = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not cand.exists():
            return cand
        n += 1


def slug(text: str, limit: int = 40) -> str:
    text = re.sub(r"[\\/:*?\"<>|\[\]#]", " ", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:limit].strip("-") or "설교"


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def project_dirs(project: Path) -> None:
    for sub in ("source", "transcript", "clips", "designs", "work", "shorts"):
        (project / sub).mkdir(parents=True, exist_ok=True)


def project_info(project: Path) -> dict:
    p = project / "project.json"
    if not p.exists():
        raise SystemExit(f"project.json 이 없습니다: {project} — 먼저 fetch 또는 use 를 실행하세요.")
    return load_json(p)


# ---------- 가져오기 ----------
def cmd_fetch(a) -> None:
    root = Path(a.root).expanduser() if a.root else env.default_work_root()
    tmp = root / f"_받는중_{int(time.time())}"
    project_dirs(tmp)
    deno = env.venv_bin("deno")
    cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist", "--ffmpeg-location", ffmpeg(),
           "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b",
           "--merge-output-format", "mp4", "--write-info-json", "-o", str(tmp / "source" / "sermon.%(ext)s")]
    if deno.exists():
        cmd[3:3] = ["--js-runtimes", f"deno:{deno}"]
    res = subprocess.run(cmd + [a.url], capture_output=True, text=True, errors="replace")
    if res.returncode != 0:
        out({"ok": False, "error": res.stderr[-1200:], "hint": "교회 미디어 담당께 원본 파일을 받거나, 채널 관리자라면 "
             "YouTube 스튜디오에서 다운로드한 파일로 `use` 를 쓰세요."})
        raise SystemExit(1)
    meta = load_json(tmp / "source" / "sermon.info.json")
    date = meta.get("upload_date") or time.strftime("%Y%m%d")
    date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    project = unique(root / f"{date}_{slug(meta.get('title', '설교'))}")
    tmp.rename(project)
    info = {"source_type": "youtube", "url": a.url, "source": str(project / "source" / "sermon.mp4"),
            "title": meta.get("title"), "channel": meta.get("channel"), "upload_date": date,
            "duration": meta.get("duration")}
    save_json(project / "project.json", info)
    out({"ok": True, "project": str(project), **info, "video": probe(Path(info["source"]))})


def cmd_use(a) -> None:
    src = Path(a.file).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"파일이 없습니다: {src}")
    root = Path(a.root).expanduser() if a.root else env.default_work_root()
    title = a.title or src.stem
    project = unique(root / f"{time.strftime('%Y-%m-%d')}_{slug(title)}")
    project_dirs(project)
    info = {"source_type": "file", "source": str(src), "title": title}
    save_json(project / "project.json", info)
    out({"ok": True, "project": str(project), **info, "video": probe(src),
         "note": "원본 파일은 옮기거나 복사하지 않고 그 자리에서 읽기만 합니다."})


# ---------- 대본 ----------
def load_audio(path: Path, start: float | None = None, dur: float | None = None, sr: int = 16000):
    import numpy as np
    cmd = [ffmpeg(), "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{max(0.0, start):.3f}"]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def whisper(audio, model: str, prompt: str | None) -> dict:
    """음성 인식. hallucination_silence_threshold 는 쓰지 않는다 — 실제로 한 말을 통째로 지우는
    경우가 확인됐다(2026-10-02). 반복 환각은 condition_on_previous_text=False 로 막는다."""
    backend = env.whisper_backend()
    name = MODELS[backend].get(model, model)
    if backend == "mlx":
        import mlx_whisper
        res = mlx_whisper.transcribe(audio, path_or_hf_repo=name, language="ko", word_timestamps=True,
                                     condition_on_previous_text=False, initial_prompt=prompt, verbose=None)
        segs = [{"start": s["start"], "end": s["end"], "text": s["text"],
                 "words": [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in s.get("words", [])]}
                for s in res["segments"]]
    else:
        from faster_whisper import WhisperModel
        wm = WhisperModel(name, device="auto", compute_type="int8")
        it, _ = wm.transcribe(audio, language="ko", word_timestamps=True, condition_on_previous_text=False,
                              vad_filter=True, initial_prompt=prompt)
        segs = [{"start": s.start, "end": s.end, "text": s.text,
                 "words": [{"word": w.word, "start": w.start, "end": w.end} for w in (s.words or [])]}
                for s in it]
    return {"backend": backend, "model": name, "language": "ko", "segments": segs,
            "text": "".join(s["text"] for s in segs)}


def cmd_transcribe(a) -> None:
    project = Path(a.project).expanduser()
    info = project_info(project)
    src = Path(info["source"])
    key = f"{sha256(src)[:20]}_{env.whisper_backend()}_{a.model}"
    cached = env.cache_dir() / f"{key}.json"
    t0 = time.time()
    if cached.exists() and not a.force:
        result = load_json(cached)
        from_cache = True
    else:
        prompt = a.prompt or "주일 설교입니다. 하나님, 예수님, 성경, 말씀, 은혜, 성도."
        result = whisper(load_audio(src), a.model, prompt)
        save_json(cached, result)
        from_cache = False
    save_json(project / "transcript" / "sermon.json", result)
    lines = [f"[{mmss(s['start'])}] {s['text'].strip()}" for s in result["segments"]]
    (project / "transcript" / "sermon.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    out({"ok": True, "from_cache": from_cache, "seconds": round(time.time() - t0, 1),
         "segments": len(result["segments"]), "words": sum(len(s["words"]) for s in result["segments"]),
         "backend": result["backend"], "model": result["model"],
         "transcript_txt": str(project / "transcript" / "sermon.txt")})


def transcript_words(project: Path) -> list[dict]:
    t = load_json(project / "transcript" / "sermon.json")
    return [w for s in t["segments"] for w in s.get("words", [])]


def cmd_transcript(a) -> None:
    project = Path(a.project).expanduser()
    t = load_json(project / "transcript" / "sermon.json")
    lo = seconds(a.from_) if a.from_ else 0.0
    hi = seconds(a.to) if a.to else 1e9
    if a.words:
        for w in transcript_words(project):
            if lo <= w["start"] <= hi:
                print(f"{w['start']:.2f}-{w['end']:.2f} {w['word'].strip()}")
        return
    for s in t["segments"]:
        if lo - 1 <= s["start"] <= hi:
            print(f"[{mmss(s['start'])}] {s['text'].strip()}")


# ---------- 쉼 분석 → 남길 구간 ----------
def envelope(audio, sr=16000, hop=0.02):
    import numpy as np
    n = int(sr * hop)
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9)


def quiet_runs(db, t0, hop=0.02, min_len=0.15):
    import numpy as np
    floor, loud = np.percentile(db, 10), np.percentile(db, 90)
    thr = floor + 0.35 * (loud - floor)
    quiet = db < thr
    runs, start = [], None
    for i, q in enumerate(list(quiet) + [False]):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * hop >= min_len:
                runs.append((round(t0 + start * hop, 2), round(t0 + i * hop, 2)))
            start = None
    return runs, float(thr)


def norm(s: str) -> str:
    return re.sub(r"[\s\"'“”‘’.,?!·…~\-]", "", s)


def find_phrase(words, phrase):
    """뺄 말을 대본 단어 열에서 찾아 (첫 단어 시작, 끝 단어 끝)을 돌려준다."""
    target = norm(phrase)
    chars, owner = "", []
    for i, w in enumerate(words):
        t = norm(w["word"])
        chars += t
        owner += [i] * len(t)
    pos = chars.find(target)
    if pos < 0 or not target:
        return None
    first, last = owner[pos], owner[pos + len(target) - 1]
    return words[first]["start"], words[last]["end"]


def nearest_run(runs, t, before=True, window=1.2):
    """t 직전(끝나는)·직후(시작하는) 쉼. Whisper 단어 시간은 실제보다 최대 1초 가까이 어긋나므로 넉넉히 본다."""
    cands = [r for r in runs if t - window <= r[1] <= t + 1.0] if before else \
            [r for r in runs if t - 0.6 <= r[0] <= t + window]
    if not cands:
        return None
    return max(cands, key=lambda r: r[1]) if before else min(cands, key=lambda r: r[0])


def quietest(db, t0, lo, hi, hop=0.02):
    """lo~hi 사이에서 음량이 가장 낮은 순간 (짧은 숨 고르기 자리). 3칸 이동평균으로 잡음을 누른다."""
    import numpy as np
    i0, i1 = max(0, int((lo - t0) / hop)), min(len(db), int((hi - t0) / hop) + 1)
    if i1 - i0 < 3:
        return None
    seg = np.convolve(db[i0:i1], np.ones(3) / 3, mode="same")
    return round(t0 + (i0 + int(seg.argmin())) * hop, 2)


def cmd_pauses(a) -> None:
    project = Path(a.project).expanduser()
    info = project_info(project)
    lo, hi = seconds(a.from_), seconds(a.to)
    words = [w for w in transcript_words(project) if lo - 0.5 <= w["start"] <= hi + 0.5]
    if not words:
        raise SystemExit("그 구간에 대본 단어가 없습니다. 시간을 확인하세요.")
    t0 = max(0.0, lo - 2.0)
    audio = load_audio(Path(info["source"]), t0, (hi - lo) + 4.0)
    db = envelope(audio)
    runs, thr = quiet_runs(db, t0)
    keep_half = a.keep_pause / 2
    first, last = words[0], words[-1]
    r = nearest_run(runs, first["start"], before=True)
    start = max(r[0], r[1] - 0.12) if r else first["start"] - 0.15
    r = nearest_run(runs, last["end"], before=False)
    end = min(r[1], r[0] + 0.35) if r else last["end"] + 0.3
    start = max(0.0, start)
    end = min(end, probe(Path(info["source"])).get("duration", end))
    cuts, notes = [], []
    for phrase in a.remove or []:
        span = find_phrase(words, phrase)
        if not span:
            notes.append({"phrase": phrase, "found": False})
            continue
        left = nearest_run(runs, span[0], before=True)
        right = nearest_run(runs, span[1], before=False)
        # 쉼이 없으면 가장 조용한 순간에서 자른다 (단어 중간을 자르지 않도록)
        c0 = left[0] + keep_half if left else quietest(db, t0, span[0] - 0.8, span[0] + 0.3)
        c1 = right[1] - keep_half if right else quietest(db, t0, span[1] - 0.3, span[1] + 0.8)
        c0 = c0 if c0 is not None else span[0] - 0.05
        c1 = c1 if c1 is not None else span[1] + 0.05
        cuts.append((c0, c1, f"말 빼기: {phrase}"))
        notes.append({"phrase": phrase, "found": True, "cut": [round(c0, 2), round(c1, 2)],
                      "left": "쉼" if left else "가장 조용한 순간", "right": "쉼" if right else "가장 조용한 순간"})
    for r0, r1 in runs:
        if r1 - r0 > a.max_pause and start < r0 and r1 < end and not any(r1 >= c0 and r0 <= c1 for c0, c1, _ in cuts):
            cuts.append((r0 + keep_half, r1 - keep_half, f"쉼 줄이기 {r1 - r0:.2f}s→{a.keep_pause:.2f}s"))
    cuts.sort()
    keep, cur = [], start
    for c0, c1, _ in cuts:
        if c0 > cur:
            keep.append([round(cur, 2), round(c0, 2)])
        cur = max(cur, c1)
    keep.append([round(cur, 2), round(end, 2)])
    kept_text = " ".join(w["word"].strip() for w in words
                         if any(s - 0.1 <= (w["start"] + w["end"]) / 2 <= e + 0.1 for s, e in keep))
    out({"ok": True, "keep": keep, "duration": round(sum(e - s for s, e in keep), 2),
         "removed": [{"from": round(c0, 2), "to": round(c1, 2), "why": why} for c0, c1, why in cuts],
         "phrases": notes, "quiet_threshold_db": round(thr, 1), "kept_text": kept_text})


# ---------- 화면 ----------
def extract_frame(src: Path, at: float, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    run_ff(["-ss", f"{at:.3f}", "-i", str(src), "-frames:v", "1", str(dest)])
    return dest


def cmd_frame(a) -> None:
    from PIL import Image, ImageDraw
    import shorts_design as sd
    at = seconds(a.at)
    if a.video:  # 결과 영상 확인용
        src = Path(a.video).expanduser()
        dest = Path(a.out) if a.out else src.with_name(f"{src.stem}_frame_{at:g}.png")
    else:
        if not a.project:
            raise SystemExit("--project 또는 --video 가 필요합니다.")
        project = Path(a.project).expanduser()
        src = Path(project_info(project)["source"])
        dest = Path(a.out) if a.out else project / "designs" / f"frame_{int(at)}{'_grid' if a.grid else ''}.png"
    extract_frame(src, at, dest)
    if a.grid:
        im = Image.open(dest).convert("RGB")
        d = ImageDraw.Draw(im)
        step = 100 if im.width <= 2000 else 200
        f = sd.font("sans_sb", 26 if im.width <= 2000 else 48)
        for x in range(0, im.width, step):
            d.line([(x, 0), (x, im.height)], fill=(255, 220, 0), width=2)
            d.text((x + 4, 4), str(x), fill=(255, 220, 0), font=f)
        for y in range(0, im.height, step):
            d.line([(0, y), (im.width, y)], fill=(255, 220, 0), width=2)
            d.text((4, y + 4), str(y), fill=(255, 220, 0), font=f)
        im.save(dest)
    v = probe(src)
    out({"ok": True, "frame": str(dest), "source_size": [v.get("width"), v.get("height")],
         "note": "격자 숫자는 원본 픽셀 좌표입니다. 얼굴 중심을 clip 의 focus 로 적으세요." if a.grid else ""})


def clip_paths(clip_path: Path):
    clip = load_json(clip_path)
    project = clip_path.parent.parent if clip_path.parent.name == "clips" else clip_path.parent
    return clip, project


def cmd_preview(a) -> None:
    from PIL import Image
    import shorts_design as sd
    clip_path = Path(a.clip).expanduser()
    clip, project = clip_paths(clip_path)
    src = Path(clip["source"])
    s, e = clip["keep"][0]
    at = seconds(a.at) if a.at else (s + e) / 2
    frame = Image.open(extract_frame(src, at, project / "work" / clip["id"] / "preview_frame.png")).convert("RGB")
    sample = a.caption or (clip.get("cues") or ["자막 예시 문장입니다"])[0]
    stills, labels = [], []
    for key, (short, label) in sd.DESIGNS.items():
        img = sd.compose_still(key, frame, clip["meta"], clip["focus"], sample, clip.get("highlight", []),
                               clip.get("window_height_ratio", 0.555))
        dest = project / "designs" / f"{clip['id']}_시안{key}_{short}.png"
        img.convert("RGB").save(dest)
        stills.append(img)
        labels.append(f"시안 {key} · {label}")
    plain = project / "designs" / f"{clip['id']}_시안비교.png"
    ui = project / "designs" / f"{clip['id']}_시안비교_유튜브화면.png"
    sd.sheet(stills, labels, plain)
    sd.sheet([sd.shorts_ui(x, title=clip["meta"].get("title", "")) for x in stills],
             [x + " (유튜브 화면)" for x in labels], ui)
    out({"ok": True, "comparison": str(plain), "comparison_with_youtube_ui": str(ui),
         "each": [str(project / "designs" / f"{clip['id']}_시안{k}_{v[0]}.png") for k, v in sd.DESIGNS.items()]})


# ---------- 렌더 ----------
def keep_hash(clip) -> str:
    return hashlib.sha256(json.dumps([clip["source"], clip["keep"]]).encode()).hexdigest()[:16]


def render_master(clip, work: Path) -> Path:
    master, stamp = work / "master.mp4", work / "master.json"
    if master.exists() and stamp.exists() and load_json(stamp).get("hash") == keep_hash(clip):
        return master
    src = Path(clip["source"])
    fps = probe(src).get("fps") or 30
    pre = max(0.0, clip["keep"][0][0] - 2.0)
    v, au, n = [], [], len(clip["keep"])
    for i, (s, e) in enumerate(clip["keep"]):
        s0, e0 = s - pre, e - pre
        v.append(f"[0:v]trim=start={s0:.3f}:end={e0:.3f},setpts=PTS-STARTPTS[v{i}]")
        au.append(f"[0:a]atrim=start={s0:.3f}:end={e0:.3f},asetpts=PTS-STARTPTS,"
                  f"afade=t=in:d=0.012,afade=t=out:st={e - s - 0.012:.3f}:d=0.012[a{i}]")
    graph = ";".join(v + au) + ";" + "".join(f"[v{i}][a{i}]" for i in range(n)) + \
        f"concat=n={n}:v=1:a=1[vc][ac];[ac]loudnorm=I=-14:TP=-1.5:LRA=11[ao]"
    run_ff(["-ss", f"{pre:.3f}", "-i", str(src), "-filter_complex", graph, "-map", "[vc]", "-map", "[ao]",
            "-r", f"{fps:g}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(master)])
    save_json(stamp, {"hash": keep_hash(clip), "fps": fps})
    return master


def align(cues: list[str], words: list[dict]):
    chars = []
    for w in words:
        t = norm(w["word"])
        if not t:
            continue
        step = (w["end"] - w["start"]) / len(t)
        chars += [(c, w["start"] + k * step, w["start"] + (k + 1) * step) for k, c in enumerate(t)]
    heard = "".join(c for c, _, _ in chars)
    script = "".join(norm(c) for c in cues)
    sm = difflib.SequenceMatcher(None, script, heard, autojunk=False)
    mapping = {}
    for a0, b0, size in sm.get_matching_blocks():
        for k in range(size):
            mapping[a0 + k] = b0 + k
    timed, pos = [], 0
    for cue in cues:
        n = len(norm(cue))
        idx = [mapping[i] for i in range(pos, pos + n) if i in mapping]
        pos += n
        timed.append({"text": cue, "start": chars[idx[0]][1] if idx else None,
                      "end": chars[idx[-1]][2] if idx else None, "matched": round(len(idx) / max(1, n), 2)})
    for i, c in enumerate(timed):
        if c["start"] is None:
            prev = timed[i - 1]["end"] if i else 0.0
            nxt = next((t["start"] for t in timed[i + 1:] if t["start"] is not None), prev + 1.5)
            c["start"], c["end"] = prev, nxt
    for i, c in enumerate(timed):
        c["start"] = max(0.0, c["start"] - 0.08)
        nxt = timed[i + 1]["start"] - 0.08 if i + 1 < len(timed) else c["end"] + 0.5
        c["end"] = nxt if nxt - c["end"] < 0.5 else c["end"] + 0.25
        c["end"] = max(c["end"], c["start"] + 0.6)
    diffs = [{"자막": script[a1:a2], "들린말": heard[b1:b2]} for op, a1, a2, b1, b2 in sm.get_opcodes() if op != "equal"]
    return timed, round(sm.ratio(), 3), diffs


def words_through_keep(words, keep):
    """원본 대본 단어 시간을 잘라 붙인 타임라인 시간으로 옮긴다 (--no-recheck 용)."""
    out_words, offset = [], 0.0
    for s, e in keep:
        for w in words:
            if s - 0.05 <= w["start"] and w["end"] <= e + 0.05:
                out_words.append({"word": w["word"], "start": w["start"] - s + offset, "end": w["end"] - s + offset})
        offset += e - s
    return out_words


def render_design(key, clip, master, cues, work, dest):
    from PIL import Image, ImageDraw
    import shorts_design as sd
    L = sd.layers(key, clip["meta"])
    tdir = work / f"t{key}"
    tdir.mkdir(parents=True, exist_ok=True)
    mv = probe(master)
    dur, fps = mv["duration"], mv.get("fps") or 30
    src_w, src_h = mv["width"], mv["height"]
    inputs, graph, idx = ["-i", str(master)], [], 1

    def add_png(img, loop=False):
        nonlocal idx
        p = tdir / f"layer_{idx}.png"
        img.save(p)
        inputs.extend((["-loop", "1", "-t", f"{dur:.3f}"] if loop else []) + ["-i", str(p)])
        idx += 1
        return idx - 1

    bounds, t = [], 0.0
    for s, e in clip["keep"]:
        bounds.append((t, t + (e - s)))
        t += e - s
    win, focus = L["win"], clip["focus"]
    ratio = clip.get("window_height_ratio", 0.555)
    crops = sd.window_crops(src_w, src_h, win["w"], win["h"], focus, ratio) if win else \
        sd.fullbleed_crops(src_w, src_h, focus)
    tw, th = (win["w"], win["h"]) if win else (sd.W, sd.H)
    n = len(bounds)
    graph.append(f"[0:v]split={n + (1 if L['moving_bg'] else 0)}" + "".join(f"[s{i}]" for i in range(n)) +
                 ("[sbg]" if L["moving_bg"] else ""))
    for i, (a0, b0) in enumerate(bounds):
        cw, ch, cx, cy = crops[i % 2]
        graph.append(f"[s{i}]trim=start={a0:.3f}:end={b0:.3f},setpts=PTS-STARTPTS,crop={cw}:{ch}:{cx}:{cy},"
                     f"scale={tw}:{th}:flags=lanczos,setsar=1[w{i}]")
    graph.append("".join(f"[w{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[win]")
    if L["bg"] is not None:
        b = add_png(L["bg"])
        graph.append(f"color=c=black:s={sd.W}x{sd.H}:r={fps:g}:d={dur:.3f}[base];[base][{b}:v]overlay=0:0[bg]")
        last = "bg"
    elif L["moving_bg"]:
        cw, ch, cx, cy = sd.fullbleed_crops(src_w, src_h, focus)[0]
        graph.append(f"[sbg]crop={cw}:{ch}:{cx}:{cy},scale=270:480,gblur=sigma=11,scale={sd.W}:{sd.H},"
                     f"eq=brightness=-0.05:saturation=0.85,setsar=1[blur]")
        last = "blur"
        if L["under"] is not None:
            u = add_png(L["under"])
            graph.append(f"[blur][{u}:v]overlay=0:0[under]")
            last = "under"
    else:
        last = "win"
    if win:
        srcv = "win"
        if win["r"] > 0:
            mask = Image.new("L", (win["w"], win["h"]), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, win["w"] - 1, win["h"] - 1], radius=win["r"], fill=255)
            mk = add_png(mask, loop=True)
            graph.append(f"[win]format=yuva420p[wa];[{mk}:v]format=gray[mk];[wa][mk]alphamerge[winA]")
            srcv = "winA"
        graph.append(f"[{last}][{srcv}]overlay={win['x']}:{win['y']}[v1]")
        last = "v1"
    o = add_png(L["over"])
    graph.append(f"[{last}][{o}:v]overlay=0:0[v2]")
    last = "v2"
    for k, c in enumerate(cues):
        p = tdir / f"cap_{k:02d}.png"
        sd.caption_image(c["text"], clip.get("highlight", []), L["cap"]).save(p)
        inputs += ["-i", str(p)]
        graph.append(f"[{last}][{idx}:v]overlay=0:0:enable='between(t,{c['start']:.3f},{c['end']:.3f})'[c{k}]")
        last = f"c{k}"
        idx += 1
    run_ff([*inputs, "-filter_complex", ";".join(graph), "-map", f"[{last}]", "-map", "0:a", "-t", f"{dur:.3f}",
            "-r", f"{fps:g}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart", str(dest)])


def loudness(path: Path) -> dict:
    res = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True, errors="replace")
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", res.stderr)
    pk = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", res.stderr)
    return {"integrated_lufs": float(i[-1]) if i else None, "true_peak_dbfs": float(pk[-1]) if pk else None}


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def cmd_render(a) -> None:
    import shorts_design as sd
    clip_path = Path(a.clip).expanduser()
    clip, project = clip_paths(clip_path)
    for key in ("id", "source", "keep", "focus", "meta", "cues", "output_name"):
        if key not in clip:
            raise SystemExit(f"clip 에 '{key}' 가 없습니다.")
    work = project / "work" / clip["id"]
    work.mkdir(parents=True, exist_ok=True)
    master = render_master(clip, work)
    if a.no_recheck:
        words = words_through_keep(transcript_words(project), clip["keep"])
        recheck = "원본 대본 시간으로 추정 (재인식 생략)"
    else:
        words = [w for s in whisper(load_audio(master), "turbo", None)["segments"] for w in s["words"]]
        recheck = "완성 구간 재인식"
    cues, ratio, diffs = align(clip["cues"], words)
    save_json(work / "alignment.json", {"ratio": ratio, "diffs": diffs, "cues": cues, "method": recheck})
    keys = list(sd.DESIGNS) if a.design == "all" else [d.strip() for d in a.design.split(",")]
    shorts = project / "shorts"
    results = []
    for key in keys:
        short = sd.DESIGNS[key][0]
        dest = unique(shorts / f"{clip['output_name']}_시안{key}_{short}.mp4", a.replace)
        render_design(key, clip, master, cues, work, dest)
        results.append(str(dest))
    srt = unique(shorts / f"{clip['output_name']}.srt", a.replace)
    with open(srt, "w", encoding="utf-8") as f:
        for i, c in enumerate(cues, start=1):
            f.write(f"{i}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n\n")
    mv = probe(Path(results[0]))
    out({"ok": True, "outputs": results, "srt": str(srt), "duration": round(mv.get("duration", 0), 2),
         "size": [mv.get("width"), mv.get("height")], "loudness": loudness(Path(results[0])),
         "caption_match_ratio": ratio, "recheck": recheck,
         "low_match_cues": [c["text"] for c in cues if c["matched"] < 0.8], "differences": diffs[:20]})


def cmd_compare(a) -> None:
    from PIL import Image, ImageDraw
    import shorts_design as sd
    clip_path = Path(a.clip).expanduser()
    clip, project = clip_paths(clip_path)
    files, labels = [], []
    for key, (short, label) in sd.DESIGNS.items():
        found = sorted((project / "shorts").glob(f"{clip['output_name']}_시안{key}_{short}*.mp4"),
                       key=lambda p: p.stat().st_mtime)
        if found:
            files.append(found[-1])
            labels.append(f"시안 {key} · {label}")
    if len(files) < 2:
        raise SystemExit("비교할 시안이 둘 이상 있어야 합니다. render --design all 을 먼저 실행하세요.")
    lab = Image.new("RGB", (540 * len(files), 70), (236, 233, 228))
    d = ImageDraw.Draw(lab)
    f = sd.font("sans_sb", 30)
    for i, text in enumerate(labels):
        d.text((i * 540 + (540 - d.textlength(text, font=f)) / 2, 18), text, font=f, fill=(40, 36, 32))
    lab_path = project / "work" / clip["id"] / "compare_labels.png"
    lab.save(lab_path)
    ins = sum((["-i", str(p)] for p in files), []) + ["-i", str(lab_path)]
    n = len(files)
    graph = ";".join(f"[{i}:v]scale=540:960[s{i}]" for i in range(n)) + ";" + \
        "".join(f"[s{i}]" for i in range(n)) + f"hstack=inputs={n}[top];[top][{n}:v]vstack=inputs=2[v]"
    dest = unique(project / "shorts" / f"{clip['output_name']}_시안비교.mp4", a.replace)
    run_ff([*ins, "-filter_complex", graph, "-map", "[v]", "-map", "0:a", "-shortest", "-c:v", "libx264",
            "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
            str(dest)])
    out({"ok": True, "comparison_video": str(dest), "designs": labels})


# ---------- 업로드 전 점검 ----------
def cmd_validate(a) -> None:
    v = probe(Path(a.video).expanduser())
    errors, warnings = [], []
    w, h, dur = v.get("width"), v.get("height"), v.get("duration", 0)
    if not w or not h or w >= h:
        errors.append("세로 영상이 아닙니다 — 쇼츠는 세로(9:16) 또는 정사각형이어야 합니다.")
    elif (w, h) != (1080, 1920):
        warnings.append(f"해상도 {w}x{h} — 1080x1920 을 권장합니다.")
    if dur > SHORTS_MAX_SECONDS:
        errors.append(f"길이 {dur:.1f}초 — 쇼츠는 3분(180초) 이하여야 합니다.")
    elif dur > 60:
        warnings.append(f"길이 {dur:.1f}초 — 60초를 넘으면 저작권 음악 클레임 시 전 세계 차단 대상이 됩니다(아래 참고).")
    if a.has_music and dur > 60:
        errors.append("음악(찬양 등)이 들어간 60초 초과 쇼츠는 Content ID 클레임이 걸리면 전 세계에서 차단됩니다. "
                      "찬양 구간을 빼거나 60초 이하로 줄이세요.")
    title = a.title or ""
    if len(title) > 100:
        errors.append(f"제목 {len(title)}자 — 100자 이하여야 합니다.")
    desc = Path(a.description_file).read_text(encoding="utf-8") if a.description_file else ""
    if len(desc) > 5000:
        errors.append(f"설명 {len(desc)}자 — 5000자 이하여야 합니다.")
    tags = [t for t in re.split(r"\s+", a.hashtags or "") if t.startswith("#")]
    if len(tags) > 3:
        warnings.append(f"해시태그 {len(tags)}개 — 3개 이내를 권합니다(가장 앞의 몇 개만 눈에 띕니다).")
    lo = loudness(Path(a.video).expanduser())
    if lo["integrated_lufs"] is not None and not -16.5 <= lo["integrated_lufs"] <= -11.5:
        warnings.append(f"음량 {lo['integrated_lufs']} LUFS — 약 -14 LUFS 를 권합니다.")
    out({"ok": not errors, "errors": errors, "warnings": warnings, "video": v, "loudness": lo,
         "title_chars": len(title), "description_chars": len(desc), "hashtags": tags,
         "facts_checked": "YouTube 도움말 '3분 쇼츠'(2026-10-02 확인): 3분 이하 세로·정사각형=쇼츠, "
                          "1분 넘는 쇼츠에 Content ID 클레임이 있으면 전 세계 차단."})


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("fetch"); s.add_argument("url"); s.add_argument("--root")
    s = sub.add_parser("use"); s.add_argument("file"); s.add_argument("--root"); s.add_argument("--title")
    s = sub.add_parser("transcribe"); s.add_argument("--project", required=True)
    s.add_argument("--model", default="turbo", choices=["turbo", "small", "medium"])
    s.add_argument("--prompt"); s.add_argument("--force", action="store_true")
    s = sub.add_parser("transcript"); s.add_argument("--project", required=True)
    s.add_argument("--from", dest="from_"); s.add_argument("--to"); s.add_argument("--words", action="store_true")
    s = sub.add_parser("pauses"); s.add_argument("--project", required=True)
    s.add_argument("--from", dest="from_", required=True); s.add_argument("--to", required=True)
    s.add_argument("--remove", action="append"); s.add_argument("--max-pause", type=float, default=0.6)
    s.add_argument("--keep-pause", type=float, default=0.38)
    s = sub.add_parser("frame"); s.add_argument("--project"); s.add_argument("--video"); s.add_argument("--at", required=True)
    s.add_argument("--grid", action="store_true"); s.add_argument("--out")
    s = sub.add_parser("preview"); s.add_argument("--clip", required=True); s.add_argument("--at")
    s.add_argument("--caption")
    s = sub.add_parser("render"); s.add_argument("--clip", required=True); s.add_argument("--design", default="all")
    s.add_argument("--no-recheck", action="store_true"); s.add_argument("--replace", action="store_true")
    s = sub.add_parser("compare"); s.add_argument("--clip", required=True); s.add_argument("--replace", action="store_true")
    s = sub.add_parser("validate"); s.add_argument("--video", required=True); s.add_argument("--title")
    s.add_argument("--description-file"); s.add_argument("--hashtags"); s.add_argument("--has-music", action="store_true")
    a = p.parse_args(argv[1:])
    handlers = {"fetch": cmd_fetch, "use": cmd_use, "transcribe": cmd_transcribe, "transcript": cmd_transcript,
                "pauses": cmd_pauses, "frame": cmd_frame, "preview": cmd_preview, "render": cmd_render,
                "compare": cmd_compare, "validate": cmd_validate}
    handlers[a.cmd](a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
