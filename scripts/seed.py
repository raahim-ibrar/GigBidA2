"""Create three explicitly fictional demo accounts through the authenticated API."""

import argparse
import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from scripts.student_personas import TOPICS, documents


def seed(
    base="http://localhost:8000",
    *,
    credentials_path="work/demo-accounts.json",
    web_origin="http://localhost:3000",
):
    path = Path(credentials_path)
    saved = json.loads(path.read_text()) if path.exists() else {}
    path.parent.mkdir(parents=True, exist_ok=True)
    for persona in TOPICS:
        credentials = saved.setdefault(
            persona,
            {
                "email": f"demo-{persona}@example.org",
                "password": secrets.token_urlsafe(24),
            },
        )
        # Save before registration so an interrupted seed can log in without resetting an account.
        path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
        with httpx.Client(
            base_url=base + "/api", timeout=60, headers={"Origin": web_origin}
        ) as client:
            response = client.post("/auth/register", json=credentials)
            if response.status_code == 409:
                response = client.post("/auth/login", json=credentials)
            response.raise_for_status()
            account = response.json()
            client.headers["X-CSRF-Token"] = account["csrf_token"]
            result = client.put(
                "/profile/me",
                json={
                    "display_name": "Demo " + persona.replace("_", " "),
                    "persona": persona,
                    "hourly_floor": "15.00",
                    "weekly_connects_budget": 100,
                    "saved_searches": [TOPICS[persona][0][1][0]],
                },
            )
            result.raise_for_status()
            for document in documents(persona):
                response = client.post(
                    "/portfolio/documents",
                    files={
                        "file": (document["filename"], document["text"].encode(), "text/markdown"),
                    },
                    data={"metadata": document["metadata"].model_dump_json()},
                )
                response.raise_for_status()
            client.put("/marketplace", json={"mode": "student_sim"}).raise_for_status()
            availability = client.get("/workspace/availability")
            availability.raise_for_status()
            if not availability.json():
                start = (datetime.now(UTC) + timedelta(days=1)).replace(
                    hour=12, minute=0, second=0, microsecond=0
                )
                client.post(
                    "/workspace/availability",
                    json={
                        "start": start.isoformat(),
                        "end": (start + timedelta(hours=2)).isoformat(),
                    },
                ).raise_for_status()
            print(f"Prepared synthetic {persona} account and portfolio; indexing queued.")
    print(f"Private local credentials: {path.resolve()}")
    return saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    seed(args.base_url)
