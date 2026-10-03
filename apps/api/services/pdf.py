from __future__ import annotations

import io

from fastapi import HTTPException, status
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError

# The web app looks for these prefixes to decide whether to ask for a password.
PASSWORD_REQUIRED = "PASSWORD_REQUIRED"
PASSWORD_INCORRECT = "PASSWORD_INCORRECT"


def unlock_pdf(data: bytes, password: str | None) -> bytes:
    """Return the PDF unencrypted. Indian bank statements are almost always password protected,
    and Gemini rejects encrypted files ("The document has no pages")."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if not reader.is_encrypted:
            return data
        if not password:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{PASSWORD_REQUIRED}: This PDF is password protected. Enter its password.",
            )
        if not reader.decrypt(password):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{PASSWORD_INCORRECT}: That password did not open the PDF.",
            )
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except HTTPException:
        raise
    except (PyPdfError, ValueError, OSError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This PDF could not be read. It may be corrupted.")
