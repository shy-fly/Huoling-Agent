"""解压三个文献 zip 到 knowledge/literature_corpus/。"""
from __future__ import annotations

import errno
import json
import zipfile
from pathlib import Path
from typing import Any

from app.config import settings

AGENT_LITERATURE = settings.knowledge_path.parent / "厌氧agent" / "基础原理知识"
CORPUS_ROOT = settings.knowledge_path / "literature_corpus"

ZIP_SOURCES: list[tuple[str, str]] = [
    ("厌氧智能体-厌氧抑制.zip", "inhibition"),
    ("厌氧智能体-理论书籍与综述.zip", "theory"),
    ("厌氧智能体-生产工艺与工程实践.zip", "engineering"),
]


def _is_valid_pdf(name: str) -> bool:
    lower = name.lower()
    if not lower.endswith(".pdf"):
        return False
    if "__macosx" in lower or "/._" in lower or name.startswith("._"):
        return False
    return True


def extract_literature_zips(force: bool = False) -> dict[str, Any]:
    CORPUS_ROOT.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"ok": True, "extracted": [], "pdf_counts": {}, "errors": []}

    for zip_name, subdir in ZIP_SOURCES:
        zip_path = AGENT_LITERATURE / zip_name
        dest = CORPUS_ROOT / subdir
        if not zip_path.exists():
            report["errors"].append({"zip": zip_name, "error": "not found"})
            continue
        if dest.exists() and any(dest.rglob("*.pdf")) and not force:
            count = len(list(dest.rglob("*.pdf")))
            report["pdf_counts"][subdir] = count
            report["extracted"].append({"zip": zip_name, "dest": str(dest), "skipped": True, "pdfs": count})
            continue
        dest.mkdir(parents=True, exist_ok=True)
        pdfs = 0
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for info in zf.infolist():
                    if info.is_dir() or not _is_valid_pdf(info.filename):
                        continue
                    # 扁平化：仅保留文件名，避免乱码路径过深
                   
                    fileName = Path(info.filename).name
                    if (info.flag_bits & 0x800) == 0:
                        try:
                            recoveredName = fileName.encode("cp437").decode("utf-8")
                            if any("\u4e00" <= char <= "\u9fff" for char in recoveredName):
                                fileName = recoveredName
                        except (UnicodeEncodeError, UnicodeDecodeError):
                            pass
                    if not fileName.lower().endswith(".pdf") or fileName.startswith("._"):
                        continue
                    target = dest / fileName

                    if target.exists() and not force:
                        pdfs += 1
                        continue
                    with zf.open(info) as src, open(target, "wb") as out:
                        out.write(src.read())
                    pdfs += 1
            report["pdf_counts"][subdir] = pdfs
            report["extracted"].append({"zip": zip_name, "dest": str(dest), "pdfs": pdfs})
        except OSError as exc:
            existing = len(list(dest.rglob("*.pdf"))) if dest.exists() else 0
            if exc.errno in (errno.EROFS, errno.EACCES) and existing:
                report["pdf_counts"][subdir] = existing
                report["extracted"].append(
                    {
                        "zip": zip_name,
                        "dest": str(dest),
                        "skipped": True,
                        "reason": "read_only_existing_corpus",
                        "pdfs": existing,
                    }
                )
            else:
                report["errors"].append({"zip": zip_name, "error": str(exc)})
        except Exception as exc:
            report["errors"].append({"zip": zip_name, "error": str(exc)})

    report["total_pdfs"] = sum(report["pdf_counts"].values())
    return report


if __name__ == "__main__":
    print(json.dumps(extract_literature_zips(force=True), ensure_ascii=False, indent=2))
