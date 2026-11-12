"""Loopback-only review collection; answer files are private and never fabricated."""

import json
import re
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from evals.human_review import ROOT

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class Submission(BaseModel):
    packet_id: str
    reviewer_id: str = Field(min_length=1, max_length=60)
    kind: Literal["calibration", "panel"]
    ratings: list[dict] = Field(max_length=100)
    complete: bool


@app.get("/{kind}.html")
def packet(kind: Literal["calibration", "panel"]):
    return FileResponse(ROOT / f"output/reviews/{kind}.html")


@app.post("/api/answers")
async def answers(body: Submission, request: Request):
    if request.headers.get("origin") not in {"http://localhost:8090", "http://127.0.0.1:8090"}:
        raise HTTPException(403, "Local review origin required")
    spec = json.loads((ROOT / f"output/reviews/{body.kind}.json").read_text())
    if spec["packet_id"] != body.packet_id:
        raise HTTPException(409, "Packet version changed")
    expected = {item["id"] for item in spec["items"]}
    ids = [row.get("id") for row in body.ratings]
    if len(ids) != len(set(ids)) or not set(ids) <= expected:
        raise HTTPException(422, "Unknown or repeated items")
    for row in body.ratings:
        valid = (
            (
                row.get("support") in {"supported", "unsupported", "not_factual"}
                and type(row.get("quality")) is int
                and 1 <= row["quality"] <= 5
            )
            if body.kind == "calibration"
            else row.get("preference") in {"a", "b", "tie"}
        )
        if body.complete and not valid:
            raise HTTPException(422, "Incomplete rating")
    if body.complete and set(ids) != expected:
        raise HTTPException(422, "Every item must be rated before completion")
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", body.reviewer_id)
    directory = ROOT / "work/human-review/answers"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{body.kind}-{safe}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(body.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)
    return {"saved": True, "complete": body.complete}
