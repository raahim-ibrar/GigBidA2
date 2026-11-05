"""Regenerate the schema used by openapi-typescript; run from the repository root."""

import json
from pathlib import Path

from apps.api.main import app

root = Path(__file__).resolve().parents[1]
(root / "docs/openapi.json").write_text(
    json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
