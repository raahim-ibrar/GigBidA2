"""Fixed word windows for the dense baseline, with source-page provenance."""

from rag.ingest.parse import TextBlock


def chunk_blocks(blocks: list[TextBlock], *, words: int = 180, overlap: int = 30):
    if not 0 <= overlap < words:
        raise ValueError("Overlap must be smaller than the chunk size")
    for block in blocks:
        tokens = block.text.split()
        for start in range(0, len(tokens), words - overlap):
            text = " ".join(tokens[start : start + words])
            if text:
                yield TextBlock(text, block.page)
            if start + words >= len(tokens):
                break
