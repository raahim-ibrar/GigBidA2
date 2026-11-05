from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from rag.index.bm25 import rank
from rag.ingest.chunkers import chunk_blocks
from rag.ingest.parse import InvalidDocument, TextBlock, parse_document
from rag.retrieval import fuse, requirements


def test_pdf_text_and_page_provenance_are_extracted():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 700 Td (Python FastAPI backend experience) Tj ET")
    page.replace_contents(stream)
    buffer = BytesIO()
    writer.write(buffer)
    blocks = parse_document("development-cv.pdf", buffer.getvalue())
    assert blocks[0].page == 1
    assert "Python FastAPI backend experience" in blocks[0].text


def test_chunk_overlap_and_source_page_are_preserved():
    blocks = list(
        chunk_blocks([TextBlock("one two three four five six seven", 3)], words=4, overlap=1)
    )
    assert [b.text for b in blocks] == ["one two three four", "four five six seven"]
    assert all(block.page == 3 for block in blocks)


@pytest.mark.parametrize(
    "name,content",
    [
        ("bad.pdf", b"not a PDF"),
        ("empty.txt", b" "),
        ("bad.txt", b"\xff\xfe"),
        ("bad.exe", b"data"),
    ],
)
def test_invalid_uploads_have_clear_errors(name, content):
    with pytest.raises(InvalidDocument):
        parse_document(name, content)


def test_lexical_rank_finds_rare_library_names_in_a_small_corpus():
    found = rank("Celery", {"a": "Python tasks with Celery", "b": "Logo design"}, 5)
    assert found and found[0][0] == "a"
    assert not rank("COBOL", {"a": "Python tasks", "b": "Logo design"}, 5)


def test_requirement_decomposition_and_fusion_deduplicate_items():
    assert requirements("- Python APIs; SQL reporting\nPython APIs") == [
        "Python APIs",
        "SQL reporting",
    ]
    assert fuse([[("a", 1), ("b", 0.5)], [("b", 1)]], 2)[0][0] == "b"
