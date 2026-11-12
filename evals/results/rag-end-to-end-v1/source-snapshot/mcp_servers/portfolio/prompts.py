from pathlib import Path


def screening_prompt(question: str) -> str:
    template = Path(__file__).resolve().parents[2] / "agent/prompts/screening.md"
    return template.read_text(encoding="utf-8").replace("{{question}}", question)
