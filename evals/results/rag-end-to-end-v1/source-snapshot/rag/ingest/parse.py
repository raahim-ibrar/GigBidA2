import io
import re
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class InvalidDocument(ValueError):
    pass


@dataclass(frozen=True)
class TextBlock:
    text: str
    page: int | None = None


def parse_document(filename: str, content: bytes) -> list[TextBlock]:
    suffix = filename.rsplit(".", 1)[-1].lower()
    if suffix == "pdf":
        if not content.lstrip().startswith(b"%PDF-"):
            raise InvalidDocument("This file is not a valid PDF")
        try:
            pdf = PdfReader(io.BytesIO(content), strict=False)
            if pdf.is_encrypted:
                raise InvalidDocument("Upload an unencrypted PDF")
            if len(pdf.pages) > 200:
                raise InvalidDocument("PDFs must have at most 200 pages")
            blocks = [
                TextBlock(page.extract_text() or "", i + 1) for i, page in enumerate(pdf.pages)
            ]
        except (PdfReadError, ValueError, OSError) as exc:
            if isinstance(exc, InvalidDocument):
                raise
            raise InvalidDocument("The PDF could not be read") from None
    elif suffix in {"md", "txt"}:
        try:
            blocks = [TextBlock(content.decode("utf-8-sig"))]
        except UnicodeDecodeError:
            raise InvalidDocument("Text documents must use UTF-8 encoding") from None
    else:
        raise InvalidDocument("Supported files: .pdf, .md and .txt")
    cleaned = [
        TextBlock(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", b.text), b.page) for b in blocks
    ]
    if sum(len(b.text) for b in cleaned) > 500000:
        raise InvalidDocument("Extracted text is too large; split the document")
    cleaned = [b for b in cleaned if b.text.strip()]
    if not cleaned:
        raise InvalidDocument("No selectable text found. Scanned PDFs need OCR before uploading")
    return cleaned
