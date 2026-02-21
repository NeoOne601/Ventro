"""
Workpaper Utilities
Standalone helpers for PDF export and integrity hashing.
Extracted from reconciliation.py for testability (avoids importing the full
FastAPI route chain with HTTP dependencies during unit testing).
"""
from __future__ import annotations

import hashlib
from datetime import datetime


def sha256_hex(data: bytes) -> str:
    """Return the SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def html_to_pdf(html_content: str, session_id: str) -> bytes:
    """
    Convert an HTML workpaper to a signed PDF.
    Priority:
      1. playwright (best fidelity — full browser rendering)
      2. weasyprint (pure Python — good for server environments)
      3. HTML bytes fallback with embedded integrity footer
    """
    integrity_footer = (
        f"\n\n<!-- Ventro Integrity Footer -->\n"
        f"<!-- Session: {session_id} | Generated: {datetime.utcnow().isoformat()} | "
        f"SHA-256: {hashlib.sha256(html_content.encode()).hexdigest()} -->"
    )
    signed_html = html_content + integrity_footer

    # Try playwright first
    try:
        import os
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
            f.write(signed_html)
            tmp_html = f.name
        tmp_pdf = tmp_html.replace(".html", ".pdf")
        result = subprocess.run(
            ["playwright", "pdf", tmp_html, tmp_pdf],
            capture_output=True, timeout=30,
        )
        if result.returncode == 0 and os.path.exists(tmp_pdf):
            with open(tmp_pdf, "rb") as f:
                pdf = f.read()
            os.unlink(tmp_html)
            os.unlink(tmp_pdf)
            return pdf
    except Exception:
        pass

    # Try weasyprint
    try:
        from weasyprint import HTML
        return HTML(string=signed_html).write_pdf()
    except ImportError:
        pass

    # Fallback: return signed HTML bytes (browser renders it; integrity footer preserved)
    return signed_html.encode("utf-8")
