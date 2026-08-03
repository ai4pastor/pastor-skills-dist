#!/usr/bin/env python3
"""Extract text from supported sermon source files.

MVP support:
- .txt with utf-8/utf-8-sig/cp949/euc-kr fallback
- .md as text
- .docx via pandoc when available, python-docx as fallback

The source file is read-only; this script never modifies it.
"""
from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess
import sys

SUPPORTED = {".docx", ".md", ".txt"}
TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "cp949", "euc-kr")


def read_text_file(path: Path) -> tuple[str, str]:
    last_error = ""
    for enc in TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=enc), enc
        except UnicodeDecodeError as exc:
            last_error = str(exc)
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"failed encodings {TEXT_ENCODINGS}: {last_error}")


def extract_docx_python_docx(path: Path) -> tuple[str, str]:
    try:
        import docx  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "pandoc도 python-docx도 없어 .docx를 읽을 수 없습니다. 아래 중 하나를 하시면 됩니다.\n"
            "  · macOS:   brew install pandoc\n"
            "  · Windows: winget install --id JohnMacFarlane.Pandoc\n"
            "  · 또는:    pip3 install python-docx\n"
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


def extract(path: Path) -> dict[str, object]:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"unsupported file type: {suffix}")
    if suffix in {".md", ".txt"}:
        text, method = read_text_file(path)
    else:
        text, method = extract_docx(path)
    return {
        "path": str(path),
        "name": path.name,
        "suffix": suffix,
        "method": method,
        "text": text,
        "chars": len(text),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: extract_text.py <file>", file=sys.stderr)
        return 2
    path = Path(argv[1]).expanduser()
    if not path.exists() or not path.is_file():
        print(f"not a file: {path}", file=sys.stderr)
        return 1
    try:
        print(json.dumps(extract(path), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"path": str(path), "status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
