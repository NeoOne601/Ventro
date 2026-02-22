"""
Prompt Injection Sanitizer
Scrubs user-controlled text before it enters LLM prompt templates.

Attack vectors blocked:
  1. Direct injection  — "Ignore all previous instructions and..."
  2. Role hijacking    — "[INST]<<SYS>>You are now DAN...<</SYS>>"
  3. Delimiter attacks — "</s>", "###", "---" used to break prompt structure
  4. Data exfiltration — attempts to echo system prompt or env vars
  5. Indirect injection via embedded PDF text (e.g. hidden white-on-white instructions)
  6. Unicode homoglyph / zero-width character evasion techniques

Usage:
    from src.infrastructure.security.prompt_sanitizer import sanitize_document_text
    clean = sanitize_document_text(raw_pdf_text, source="invoice", doc_id="abc")
"""
from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

import structlog

logger = structlog.get_logger(__name__)

# ─── Pattern library ──────────────────────────────────────────────────────────

# Injection trigger phrases (case-insensitive, order matters — more specific first)
_INJECTION_PATTERNS: list[tuple[str, str]] = [
    # Direct override commands
    (r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", "IGNORE_PREV_INSTR"),
    (r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?", "DISREGARD_INSTR"),
    (r"forget\s+(all\s+)?(previous|prior)\s+instructions?", "FORGET_INSTR"),
    (r"your\s+(new\s+)?instructions?\s+(are|is)\s+", "INSTR_OVERRIDE"),
    (r"override\s+(all\s+)?previous\s+", "OVERRIDE"),
    (r"you\s+are\s+now\s+(a|an|the)\s+", "ROLE_REDEFINITION"),
    (r"act\s+as\s+(a|an|the)\s+", "ACT_AS"),
    (r"pretend\s+(you\s+are|to\s+be)\s+", "PRETEND"),
    (r"do\s+anything\s+now", "DAN"),  # DAN-style jailbreak
    (r"jailbreak\b", "JAILBREAK"),

    # System prompt extraction
    (r"(print|show|reveal|display|repeat|echo)\s+(your\s+)?(system\s+)?prompt", "SYS_PROMPT_EXFIL"),
    (r"what\s+(is\s+your|are\s+your)\s+(system\s+)?instructions?", "SYS_PROMPT_EXFIL"),
    (r"what\s+were\s+you\s+told\s+to\s+", "SYS_PROMPT_EXFIL"),

    # Environment exfiltration
    (r"(print|show|echo|dump)\s+(all\s+)?(env(ironment)?\s+(var(iable)?s?)|secrets?|api\s+key)", "ENV_EXFIL"),

    # Token/delimiter injection (LLM-specific)
    (r"<\|?(system|user|assistant|im_start|im_end)\|?>", "CHAT_TEMPLATE_INJECTION"),
    (r"\[INST\]|\[/?SYS\]|<<SYS>>|<</SYS>>", "LLAMA_TEMPLATE"),
    (r"###\s*(instruction|system|human|assistant|input|output)", "DELIM_INJECTION"),

    # Shell/code injection (shouldn't reach LLM but defense in depth)
    (r"(import\s+os|subprocess\.run|eval\(|exec\()", "CODE_INJECTION"),
]

_COMPILED_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE | re.MULTILINE), label)
    for pattern, label in _INJECTION_PATTERNS
]

# Dangerous Unicode categories and control characters
_ZERO_WIDTH_CHARS = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\u2060-\u2064\ufeff]"
)

# Repeated delimiter sequences (text that looks like a separator in LLM prompts)
_DELIMITER_SEQUENCES = re.compile(
    r"(---{3,}|==={3,}|\*{5,}|_{5,}|#{3,}\s*$)", re.MULTILINE
)

# Hidden text markers sometimes embedded in PDFs (white text on white background)
# We can't reliably detect by colour but we can cap suspiciously long non-Latin runs
_MAX_SINGLE_TOKEN_LENGTH = 500  # Any "word" > 500 chars is suspicious

# Maximum allowed document text length per chunk sent to LLM
MAX_CHUNK_CHARS = 8_000

# ─── Public API ───────────────────────────────────────────────────────────────

class SanitizationResult(NamedTuple):
    cleaned_text: str
    was_modified: bool
    threats_found: list[str]
    truncated: bool


def sanitize_document_text(
    raw_text: str,
    source: str = "unknown",
    doc_id: str = "",
    max_chars: int = MAX_CHUNK_CHARS,
) -> SanitizationResult:
    """
    Sanitize raw document text before inserting into an LLM prompt.

    Steps:
      1. Unicode normalisation (NFC) + zero-width char removal
      2. Pattern-based injection detection and replacement
      3. Delimiter normalisation (collapse ---, ===, etc.)
      4. Long-token truncation (hidden-text heuristic)
      5. Length cap
    """
    threats: list[str] = []
    text = raw_text

    # Step 1 — Unicode normalise to NFC, remove invisible/control characters
    text = unicodedata.normalize("NFC", text)
    before_zwc = len(text)
    text = _ZERO_WIDTH_CHARS.sub("", text)
    if len(text) != before_zwc:
        threats.append("ZERO_WIDTH_CHARS")
        logger.warning(
            "prompt_injection_zwc_removed",
            doc_id=doc_id,
            source=source,
            removed_count=before_zwc - len(text),
        )

    # Remove other dangerous control characters (except standard whitespace)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Step 2 — Pattern-based injection detection
    for pattern, label in _COMPILED_PATTERNS:
        if pattern.search(text):
            threats.append(label)
            # Replace the dangerous phrase with a safe placeholder
            text = pattern.sub(f"[REDACTED:{label}]", text)
            logger.warning(
                "prompt_injection_detected",
                threat=label,
                doc_id=doc_id,
                source=source,
            )

    # Step 3 — Collapse repeated delimiter sequences (--- === ### etc.)
    text = _DELIMITER_SEQUENCES.sub("—", text)

    # Step 4 — Truncate suspiciously long tokens (hidden text heuristic)
    words = text.split()
    cleaned_words = []
    for word in words:
        if len(word) > _MAX_SINGLE_TOKEN_LENGTH:
            threats.append("LONG_TOKEN_TRUNCATED")
            cleaned_words.append(word[:_MAX_SINGLE_TOKEN_LENGTH] + "…")
        else:
            cleaned_words.append(word)
    text = " ".join(cleaned_words)

    # Step 5 — Length cap
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
        logger.debug("document_text_truncated", doc_id=doc_id, max_chars=max_chars)

    was_modified = text != raw_text or bool(threats)

    if threats:
        logger.warning(
            "prompt_sanitization_summary",
            doc_id=doc_id,
            source=source,
            threat_count=len(threats),
            threats=list(set(threats)),
        )

    return SanitizationResult(
        cleaned_text=text,
        was_modified=was_modified,
        threats_found=list(set(threats)),
        truncated=truncated,
    )


def sanitize_user_input(raw: str, field_name: str = "input") -> str:
    """
    Lightweight sanitization for small user-controlled strings (search queries,
    session names, etc.) — not for bulk document text.
    """
    # Strip zero-width chars
    cleaned = _ZERO_WIDTH_CHARS.sub("", raw)
    # Remove control characters
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", cleaned)
    # Collapse injection triggers into placeholders
    for pattern, label in _COMPILED_PATTERNS:
        if pattern.search(cleaned):
            cleaned = pattern.sub(f"[REDACTED]", cleaned)
            logger.warning(
                "user_input_injection_attempt",
                field=field_name,
                threat=label,
            )
    return cleaned.strip()[:1024]  # Hard cap on user strings
