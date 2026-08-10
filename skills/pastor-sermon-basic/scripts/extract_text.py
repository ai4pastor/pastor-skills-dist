#!/usr/bin/env python3
"""Extract text from supported sermon source files.

Supported:
- .txt / .md with utf-8/utf-8-sig/cp949/euc-kr fallback
- .docx via pandoc when available, python-docx as fallback
- .pdf  via pdftotext when available, pypdf as fallback
- .hwpx with the standard library only (OWPML = zip + section XML)
- .hwp  via pyhwp (hwp5txt)

목회 현장의 원고는 워드만이 아니다. 한글(.hwp/.hwpx)과 PDF가 그만큼 많고, 클라우드에서
받은 파일은 형식이 섞여 있다. 없는 도구는 `ensure_tools.py --install` 이 스킬 전용
폴더에만 넣는다 — 시스템 파이썬은 건드리지 않는다.

The source file is read-only; this script never modifies it.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import work_dir  # noqa: E402
from ensure_tools import activate_pylibs  # noqa: E402

SUPPORTED = {".docx", ".md", ".txt", ".pdf", ".hwpx", ".hwp"}
TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "cp949", "euc-kr")
# 페이지당 이만큼도 안 나오면 글자가 없는 스캔 이미지로 본다.
SCANNED_CHARS_PER_PAGE = 20
# 설교 한 편이 이보다 짧으면 추출이 반쯤 실패한 것으로 보고 알린다.
SHORT_TEXT_CHARS = 200


def read_text_file(path: Path) -> tuple[str, str]:
    last_error = ""
    for enc in TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=enc), enc
        except UnicodeDecodeError as exc:
            last_error = str(exc)
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"failed encodings {TEXT_ENCODINGS}: {last_error}")


def extract_docx_python_docx(path: Path) -> tuple[str, str]:
    activate_pylibs()
    try:
        import docx  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "pandoc도 python-docx도 없어 .docx를 읽을 수 없습니다. 아래 중 하나를 하시면 됩니다.\n"
            "  · 스킬이 설치: python3 scripts/ensure_tools.py --install docx\n"
            "  · macOS:   brew install pandoc\n"
            "  · Windows: winget install --id JohnMacFarlane.Pandoc\n"
            "  · 설치가 어려우시면 워드에서 그 설교를 열고 "
            "'다른 이름으로 저장 → 서식 없는 텍스트(*.txt)'로 저장해 주세요. .txt는 바로 읽습니다."
        ) from exc
    document = docx.Document(str(path))
    lines = []
    for para in document.paragraphs:
        text = para.text.rstrip()
        style = (para.style.name or "").lower() if para.style else ""
        if style.startswith("heading") and text:
            try:
                level = min(int(style.split()[-1]), 3)
            except ValueError:
                level = 2
            lines.append("#" * level + " " + text)
        else:
            lines.append(text)
    return "\n".join(lines), "python-docx"


def extract_docx(path: Path) -> tuple[str, str]:
    pandoc = shutil.which("pandoc")
    if not pandoc:
        return extract_docx_python_docx(path)
    # gfm keeps headings/lists better than plain text, which improves fragment splitting.
    result = subprocess.run([pandoc, "-t", "gfm", str(path)], check=True, text=True, capture_output=True)
    return result.stdout, "pandoc-gfm"


def extract_pdf(path: Path) -> tuple[str, str, int]:
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        # -layout keeps the manuscript's own line breaks, which the fragment
        # splitter reads as structure.
        result = subprocess.run([pdftotext, "-layout", "-enc", "UTF-8", str(path), "-"],
                                text=True, capture_output=True, timeout=300)
        if result.returncode == 0:
            return result.stdout, "pdftotext", pdf_page_count(result.stdout, path)

    activate_pylibs()
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "PDF를 읽을 도구가 없습니다. 아래 중 하나를 하시면 됩니다.\n"
            "  · 스킬이 설치: python3 scripts/ensure_tools.py --install pdf\n"
            "  · macOS:   brew install poppler\n"
            "  · PDF를 열어 본문을 복사해 메모장에 붙이고 .txt로 저장해 주셔도 됩니다."
        ) from exc
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n\n".join(pages), "pypdf", max(1, len(pages))


def pdf_page_count(text: str, path: Path) -> int:
    """페이지 수 — pdftotext 는 페이지 **끝마다** 폼피드를 붙인다.

    그래서 폼피드 개수가 곧 페이지 수다. 마지막 폼피드 뒤에 글자가 남아 있을 때만
    한 쪽을 더한다. (`count + 1` 로 세면 1쪽 PDF가 2쪽이 되어 스캔본 판정이 무너진다.)
    """
    if "\f" in text:
        tail = text.rpartition("\f")[2]
        return max(1, text.count("\f") + (1 if tail.strip() else 0))
    try:
        return max(1, len(re.findall(rb"/Type\s*/Page\b", path.read_bytes())))
    except OSError:
        return 1


def local_name(tag: str) -> str:
    return tag.rpartition("}")[2]


def hwpx_section_text(data: bytes) -> str:
    """OWPML 섹션 XML에서 문단 단위로 글자를 모은다.

    이름공간 URI가 한글 버전마다 달라 접두어(hp:)를 그대로 믿지 않고 태그의
    지역명(p, t)으로만 판정한다.
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(data)
    lines: list[str] = []
    for element in root.iter():
        if local_name(element.tag) != "p":
            continue
        parts = ["".join(node.itertext()) for node in element.iter() if local_name(node.tag) == "t"]
        lines.append("".join(parts).strip())
    return "\n".join(lines)


def extract_hwpx(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            sections = sorted((n for n in names if re.search(r"section\d+\.xml$", n, re.I)),
                              key=lambda n: int(re.search(r"section(\d+)", n, re.I).group(1)))
            if sections:
                chunks = [hwpx_section_text(archive.read(name)) for name in sections]
                text = "\n".join(chunk for chunk in chunks if chunk.strip())
                if text.strip():
                    return text, "hwpx"
            preview = next((n for n in names if n.lower().endswith("prvtext.txt")), "")
            if preview:
                raw = archive.read(preview)
                for enc in ("utf-16", "utf-8", "cp949"):
                    try:
                        return raw.decode(enc), "hwpx-preview"
                    except UnicodeDecodeError:
                        continue
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise RuntimeError(
            f".hwpx 파일을 열 수 없습니다({exc}). 한글에서 파일을 열고 다시 저장해 보시거나, "
            "'다른 이름으로 저장 → 텍스트 문서(*.txt)'로 저장해 주세요."
        ) from exc
    raise RuntimeError(
        ".hwpx 안에서 본문을 찾지 못했습니다. 한글에서 열고 '다른 이름으로 저장 → "
        "텍스트 문서(*.txt)'로 저장해 주시면 바로 읽습니다."
    )


def hwp5txt_candidates() -> list[tuple[list[str], str]]:
    """hwp5txt 를 실행할 방법들. 앞의 것부터 시도한다.

    콘솔 스크립트(bin/hwp5txt)를 모듈 호출(-m)보다 먼저 둔다. pyhwp 0.1b15 의
    `hwp5.hwp5txt` 모듈에는 `__main__` 진입점이 없어 `-m` 은 아무것도 출력하지 않고
    정상 종료한다(실측). 실행은 콘솔 스크립트로 하고, 그 스크립트가 pylibs 를 못 찾는
    문제는 PYTHONPATH 로 해결한다.
    """
    out: list[tuple[list[str], str]] = []
    found = shutil.which("hwp5txt")
    if found:
        out.append(([found], "hwp5txt"))
    pylibs = activate_pylibs()
    for sub in ("bin", "Scripts"):
        candidate = pylibs / sub / ("hwp5txt.exe" if sub == "Scripts" else "hwp5txt")
        if candidate.exists():
            out.append(([str(candidate)], f"hwp5txt({sub})"))
    out.append(([sys.executable, "-m", "hwp5.hwp5txt"], "pyhwp"))
    return out


def extract_hwp(path: Path) -> tuple[str, str]:
    pylibs = activate_pylibs()
    env = dict(os.environ)
    if pylibs.is_dir():
        env["PYTHONPATH"] = os.pathsep.join([str(pylibs), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    errors: list[str] = []
    for command, method in hwp5txt_candidates():
        try:
            result = subprocess.run([*command, str(path)], text=True, capture_output=True,
                                    timeout=300, env=env)
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"{method}: {exc}")
            continue
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout, method
        errors.append(f"{method}: rc={result.returncode} {(result.stderr or '').strip()[:200]}")
    raise RuntimeError(
        ".hwp(한글) 파일을 읽을 도구가 없습니다. 아래 중 하나를 하시면 됩니다.\n"
        "  · 스킬이 설치: python3 scripts/ensure_tools.py --install hwp\n"
        "  · 한글에서 그 설교를 열고 '다른 이름으로 저장 → 텍스트 문서(*.txt)' 또는 "
        ".hwpx로 저장해 주세요. 둘 다 추가 도구 없이 읽습니다.\n"
        f"  시도한 방법: {' | '.join(errors)}"
    )


def extract(path: Path) -> dict[str, object]:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"unsupported file type: {suffix}")
    warnings: list[str] = []
    pages = 0

    if suffix in {".md", ".txt"}:
        text, method = read_text_file(path)
    elif suffix == ".docx":
        text, method = extract_docx(path)
    elif suffix == ".pdf":
        text, method, pages = extract_pdf(path)
        text = text.replace("\f", "\n")
    elif suffix == ".hwpx":
        text, method = extract_hwpx(path)
        if method == "hwpx-preview":
            warnings.append("미리보기 텍스트만 읽었습니다 — 본문이 잘렸을 수 있습니다. "
                            "한글에서 .txt로 저장하시면 전문을 읽습니다.")
    else:
        text, method = extract_hwp(path)

    if suffix == ".pdf" and pages and len(text.strip()) / pages < SCANNED_CHARS_PER_PAGE:
        warnings.append(f"scanned_pdf: 글자가 거의 없습니다({pages}쪽에 {len(text.strip())}자). "
                        "스캔 이미지 PDF로 보입니다 — 원고 파일(.docx/.hwp/.txt)이 있으면 그것을 쓰는 편이 낫습니다.")
    elif len(text.strip()) < SHORT_TEXT_CHARS:
        # 추출은 성공했는데 내용이 거의 없는 경우가 실제로 있다(표·개체 안에 글이
        # 들어 있는 한글 문서 등). 빈 설교 노트가 조용히 생기는 것을 막는다.
        warnings.append(f"short_text: 읽어낸 본문이 {len(text.strip())}자뿐입니다. "
                        "설교 원고가 맞는지, 글이 표·상자 안에 있지 않은지 확인해 주세요.")

    result: dict[str, object] = {
        "path": str(path),
        "name": path.name,
        "suffix": suffix,
        "method": method,
        "text": text,
        "chars": len(text),
    }
    if pages:
        result["pages"] = pages
    if warnings:
        result["warnings"] = warnings
    return result


def cache_dir() -> Path:
    """추출 캐시 폴더 — 같은 원고를 dry-run·write가 다시 변환하지 않게 한다."""
    return work_dir() / "extracted"


def cache_key(path: Path) -> str:
    """파일 **내용** 기준 키 — 원고가 한 글자라도 바뀌면 캐시가 자연히 빗나간다."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_cached(path: Path, refresh: bool = False) -> dict[str, object]:
    """extract() 결과를 내용 해시로 캐시한다.

    hwp/pdf/docx 변환은 파일마다 서브프로세스를 띄우는 비싼 일이라, 한 import 안에서
    추출(Step 2)·dry-run·write 가 같은 변환을 세 번 반복하지 않도록 여기서 한 번만 한다.
    실패한 추출은 캐시하지 않는다 — 도구를 설치하고 다시 돌리면 곧바로 재시도된다.
    """
    entry = cache_dir() / f"{cache_key(path)}.json"
    if not refresh and entry.is_file():
        try:
            cached = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = None
        if isinstance(cached, dict) and "text" in cached:
            # 내용이 같은 파일이 다른 이름·경로로 올 수 있다 — 위치 정보만 현재 값으로.
            cached["path"] = str(path)
            cached["name"] = path.name
            cached["cache"] = "hit"
            return cached
    result = extract(path)
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    result["cache"] = "miss"
    return result


def main(argv: list[str]) -> int:
    flags = {a for a in argv[1:] if a.startswith("--")}
    positional = [a for a in argv[1:] if not a.startswith("--")]
    if len(positional) != 1 or not flags <= {"--no-cache", "--refresh"}:
        print("usage: extract_text.py <file> [--no-cache] [--refresh]", file=sys.stderr)
        return 2
    path = Path(positional[0]).expanduser()
    if not path.exists() or not path.is_file():
        print(f"not a file: {path}", file=sys.stderr)
        return 1
    try:
        if "--no-cache" in flags:
            result = extract(path)
        else:
            result = extract_cached(path, refresh="--refresh" in flags)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"path": str(path), "status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
