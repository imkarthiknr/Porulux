import io

import pytest
from fastapi import HTTPException
from pypdf import PdfReader, PdfWriter

from services.pdf import unlock_pdf


def make_pdf(password=None) -> bytes:
    w = PdfWriter()
    w.add_blank_page(200, 200)
    if password:
        w.encrypt(password)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def test_plain_pdf_passes_through():
    data = make_pdf()
    assert unlock_pdf(data, None) == data


def test_encrypted_pdf_requires_password():
    with pytest.raises(HTTPException) as e:
        unlock_pdf(make_pdf("secret"), None)
    assert e.value.status_code == 422 and e.value.detail.startswith("PASSWORD_REQUIRED")


def test_wrong_password_rejected():
    with pytest.raises(HTTPException) as e:
        unlock_pdf(make_pdf("secret"), "nope")
    assert e.value.detail.startswith("PASSWORD_INCORRECT")


def test_correct_password_returns_readable_unencrypted_pdf():
    out = unlock_pdf(make_pdf("secret"), "secret")
    r = PdfReader(io.BytesIO(out))
    assert not r.is_encrypted and len(r.pages) == 1


def test_garbage_is_a_clean_422():
    with pytest.raises(HTTPException) as e:
        unlock_pdf(b"not a pdf at all", None)
    assert e.value.status_code == 422
