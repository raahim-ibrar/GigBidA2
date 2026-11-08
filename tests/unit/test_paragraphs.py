import pytest
from pydantic import ValidationError

from agent.handoffs import ApprovalDecision
from agent.proposal_nodes import ParagraphRewrite, paragraph_spans


def test_paragraph_boundaries_keep_separators_and_surrounding_text_exact():
    source = "  First paragraph.\r\n \r\nSecond paragraph.\n\nFinal paragraph.  "
    spans = paragraph_spans(source)
    assert len(spans) == 3
    start, end = spans[1]
    changed = source[:start] + "Replacement." + source[end:]
    assert changed == "  First paragraph.\r\n \r\nReplacement.\n\nFinal paragraph.  "
    with pytest.raises(ValidationError):
        ParagraphRewrite(text="A replacement.\n\nAnd another paragraph.")
    with pytest.raises(ValidationError):
        ApprovalDecision(action="regenerate")
