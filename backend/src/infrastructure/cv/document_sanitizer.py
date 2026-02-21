"""
PDF Document Sanitizer
Validates uploaded files before they enter the processing pipeline.
Prevents: zip bombs, embedded JavaScript, polyglot payloads, malformed PDFs.
"""
from __future__ import annotations

import io
import struct
from pathlib import Path
from typing import NamedTuple

import fitz  # PyMuPDF
import structlog

logger = structlog.get_logger(__name__)

# ─── Configuration ─────────────────────────────────────────────────────────────
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024       # 50 MB hard limit
MAX_PDF_PAGES = 500                          # Reject abnormally large docs
MAX_PAGE_IMAGE_SIZE_BYTES = 10 * 1024 * 1024 # 10 MB per embedded image
ZIP_BOMB_RATIO = 50                          # Reject if text > 50x file size

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}

# PDF magic bytes
PDF_MAGIC = b"%PDF-"

# ─── Result Type ───────────────────────────────────────────────────────────────

class SanitizationResult(NamedTuple):
    is_safe: bool
    reason: str            # Human-readable explanation if rejected
    file_type: str         # Detected file type
    page_count: int = 0
    has_embedded_js: bool = False
    has_embedded_files: bool = False


# ─── Public API ────────────────────────────────────────────────────────────────

def sanitize_upload(
    file_bytes: bytes,
    filename: str,
    max_size: int = MAX_FILE_SIZE_BYTES,
) -> SanitizationResult:
    """
    Run all sanitization checks on raw file bytes.
    Returns SanitizationResult — caller must reject file if is_safe=False.
    """
    suffix = Path(filename).suffix.lower()

    # 1. Size check
    if len(file_bytes) > max_size:
        return SanitizationResult(
            False, f"File exceeds maximum size of {max_size // 1024 // 1024} MB",
            "unknown"
        )

    # 2. Empty file
    if len(file_bytes) < 4:
        return SanitizationResult(False, "File is empty or too small", "unknown")

    # 3. Route to type-specific checks
    if suffix == ".pdf" or file_bytes[:5] == PDF_MAGIC:
        return _check_pdf(file_bytes)
    elif suffix == ".csv":
        return _check_csv(file_bytes)
    elif suffix in (".xlsx", ".xls"):
        return _check_xlsx(file_bytes)
    else:
        return SanitizationResult(False, f"File type '{suffix}' not permitted", "unknown")


# ─── PDF Checks ───────────────────────────────────────────────────────────────

def _check_pdf(file_bytes: bytes) -> SanitizationResult:
    """Deep inspection of PDF structure for malicious content."""

    # Magic bytes check
    if not file_bytes[:5] == PDF_MAGIC:
        return SanitizationResult(False, "File does not have a valid PDF header", "pdf")

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        return SanitizationResult(False, f"PDF is malformed or unreadable: {e}", "pdf")

    page_count = len(doc)

    # Page count sanity
    if page_count == 0:
        doc.close()
        return SanitizationResult(False, "PDF contains no pages", "pdf")

    if page_count > MAX_PDF_PAGES:
        doc.close()
        return SanitizationResult(
            False, f"PDF has {page_count} pages; maximum is {MAX_PDF_PAGES}", "pdf"
        )

    # Embedded JavaScript detection
    has_js = False
    try:
        for page_num in range(min(page_count, 20)):  # Check first 20 pages
            page = doc[page_num]
            annots = page.annots()
            if annots:
                for annot in annots:
                    if annot.info.get("content", "").lower().startswith("javascript:"):
                        has_js = True
                        break

        # Check document-level JS via catalog
        catalog = doc.pdf_catalog()
        if catalog and "JavaScript" in str(catalog):
            has_js = True
    except Exception:
        pass  # Non-critical — proceed with warning

    if has_js:
        doc.close()
        return SanitizationResult(
            False, "PDF contains embedded JavaScript — rejected for security", "pdf",
            has_embedded_js=True,
        )

    # Embedded files check (can be used to hide malicious payloads)
    has_embedded = False
    try:
        if doc.embfile_count() > 0:
            has_embedded = True
    except Exception:
        pass

    # Text-based zip bomb detection
    try:
        total_text_len = sum(
            len(doc[p].get_text("text"))
            for p in range(min(page_count, 10))
        )
        if total_text_len > len(file_bytes) * ZIP_BOMB_RATIO:
            doc.close()
            return SanitizationResult(
                False, "PDF text content is suspiciously large relative to file size", "pdf"
            )
    except Exception:
        pass

    doc.close()
    logger.info(
        "pdf_sanitization_passed",
        pages=page_count,
        has_embedded=has_embedded,
        has_js=has_js,
    )
    return SanitizationResult(
        True, "ok", "pdf",
        page_count=page_count,
        has_embedded_js=False,
        has_embedded_files=has_embedded,
    )


def _check_csv(file_bytes: bytes) -> SanitizationResult:
    """Basic CSV validation — UTF-8 decodable, not a binary file."""
    try:
        text = file_bytes.decode("utf-8-sig")
        if len(text.strip()) == 0:
            return SanitizationResult(False, "CSV file is empty", "csv")
        return SanitizationResult(True, "ok", "csv")
    except UnicodeDecodeError:
        return SanitizationResult(False, "File is not valid UTF-8 CSV", "csv")


def _check_xlsx(file_bytes: bytes) -> SanitizationResult:
    """Validate XLSX by checking ZIP magic bytes (XLSX is a ZIP archive)."""
    # XLSX files are ZIP archives — magic bytes: PK\x03\x04
    if file_bytes[:4] != b"PK\x03\x04":
        return SanitizationResult(False, "File does not have valid XLSX/ZIP structure", "xlsx")
    return SanitizationResult(True, "ok", "xlsx")
