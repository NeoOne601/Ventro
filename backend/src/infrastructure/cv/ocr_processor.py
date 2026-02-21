"""
Multilingual OCR Processor
Handles scanned/image-only PDF pages using Tesseract OCR with language detection.
Supports 100+ scripts: Latin, Arabic, Devanagari, CJK, Cyrillic, Hebrew, etc.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import structlog

logger = structlog.get_logger(__name__)

# Tesseract language pack mapping for common scripts
# One-time download: apt-get install tesseract-ocr-[lang]
TESSERACT_LANG_PACKS = {
    "latin":      "eng+fra+deu+spa+por+ita+nld",   # Latin-script European
    "arabic":     "ara",
    "hindi":      "hin",
    "japanese":   "jpn",
    "chinese_s":  "chi_sim",
    "chinese_t":  "chi_tra",
    "korean":     "kor",
    "russian":    "rus",
    "greek":      "ell",
    "hebrew":     "heb",
    "thai":       "tha",
    "default":    "eng+ara+hin+chi_sim+jpn+kor+rus",  # broad multilingual
}

# Pixel threshold below which a page is considered "image-only" (scanned)
TEXT_DENSITY_THRESHOLD = 50  # characters per page


def is_page_scanned(page: fitz.Page) -> bool:
    """
    Determine if a PDF page is scanned (image-only) vs digitally generated.
    Uses character count heuristic — scanned pages yield very little extractable text.
    """
    text = page.get_text("text")
    char_count = len(text.strip().replace("\n", "").replace(" ", ""))
    return char_count < TEXT_DENSITY_THRESHOLD


def render_page_to_image(page: fitz.Page, dpi: int = 300) -> bytes:
    """
    Render a PDF page to a high-resolution PNG image for OCR.
    300 DPI is the recommended minimum for accurate Tesseract recognition.
    """
    mat = fitz.Matrix(dpi / 72, dpi / 72)  # 72 DPI is PyMuPDF default
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")


def ocr_page_with_tesseract(
    page_image_bytes: bytes,
    lang: str = TESSERACT_LANG_PACKS["default"],
    config: str = "--psm 3",  # Fully automatic page segmentation
) -> tuple[str, list[dict[str, Any]]]:
    """
    Run Tesseract OCR on a rendered page image.
    Returns (full_text, word_level_bbox_list).
    
    Each bbox dict: {text, x0, y0, x1, y1, confidence, page_width, page_height}
    Set lang='default' to use the broad multilingual model.
    """
    try:
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(page_image_bytes))
        img_width, img_height = image.size

        # Full-page text
        full_text: str = pytesseract.image_to_string(image, lang=lang, config=config)

        # Word-level data for bounding boxes
        data = pytesseract.image_to_data(
            image, lang=lang, config=config,
            output_type=pytesseract.Output.DICT
        )

        bboxes: list[dict[str, Any]] = []
        n = len(data["text"])
        for i in range(n):
            word = str(data["text"][i]).strip()
            conf = int(data["conf"][i])
            if not word or conf < 30:  # skip low-confidence junk
                continue

            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            bboxes.append({
                "text": word,
                "confidence": conf / 100.0,
                # normalized to [0,1]
                "x0": round(x / img_width, 4),
                "y0": round(y / img_height, 4),
                "x1": round((x + w) / img_width, 4),
                "y1": round((y + h) / img_height, 4),
            })

        logger.debug(
            "tesseract_ocr_complete",
            words=len(bboxes),
            text_len=len(full_text),
            lang=lang,
        )
        return full_text, bboxes

    except ImportError:
        logger.error("pytesseract_not_installed", hint="pip install pytesseract")
        return "", []
    except Exception as e:
        logger.error("tesseract_ocr_failed", error=str(e))
        return "", []


def ocr_pdf_pages(
    pdf_doc: fitz.Document,
    lang: str = TESSERACT_LANG_PACKS["default"],
    dpi: int = 300,
    force_ocr: bool = False,
) -> dict[int, dict[str, Any]]:
    """
    Process all pages in a PDF, applying OCR only to scanned pages.
    Returns {page_num: {text, bboxes, was_ocr_applied}}.
    """
    results: dict[int, dict[str, Any]] = {}

    for page_num in range(len(pdf_doc)):
        page = pdf_doc[page_num]
        scanned = force_ocr or is_page_scanned(page)

        if scanned:
            logger.info("page_requires_ocr", page=page_num)
            image_bytes = render_page_to_image(page, dpi=dpi)
            text, bboxes = ocr_page_with_tesseract(image_bytes, lang=lang)
            results[page_num] = {
                "text": text,
                "bboxes": bboxes,
                "was_ocr_applied": True,
                "ocr_lang": lang,
            }
        else:
            # Use native PyMuPDF extraction (already done upstream, this is a no-op marker)
            results[page_num] = {
                "text": page.get_text("text"),
                "bboxes": [],
                "was_ocr_applied": False,
                "ocr_lang": None,
            }

    return results
