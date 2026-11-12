"""PDF CV parsing."""

from rag.ingest.parse import parse_document


def load(content: bytes):
    return parse_document("cv.pdf", content)
