"""Atomic simulator balances, request receipts, messages and lifecycle events."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class SimConflict(ValueError):
    pass


class SimStore:
    def __init__(self, path, catalogue, *, starting_connects=100, client_mode="rule"):
        if client_mode not in {"rule", "llm"}:
            raise ValueError("Unknown simulator client mode")
        self.client_mode = client_mode
        self.path, self.jobs, self.starting_connects = (
            str(path),
            {j["id"]: j for j in catalogue},
            starting_connects,
        )
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS accounts(
                    tenant TEXT PRIMARY KEY, balance INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS writes(tenant TEXT NOT NULL, key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(tenant,key));
                CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, tenant TEXT NOT NULL,
                    job_id TEXT NOT NULL, body TEXT NOT NULL, UNIQUE(tenant,job_id));
                CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, tenant TEXT NOT NULL,
                    conversation TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pending_clients(
                    proposal TEXT PRIMARY KEY, tenant TEXT NOT NULL, attempts INTEGER NOT NULL,
                    next_at REAL NOT NULL, error TEXT);
                CREATE TABLE IF NOT EXISTS client_decisions(
                    proposal TEXT PRIMARY KEY, body TEXT NOT NULL);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def balance(self, tenant):
        with self.db() as db:
            row = db.execute("SELECT balance FROM accounts WHERE tenant=?", (tenant,)).fetchone()
            return row[0] if row else self.starting_connects

    def _event(self, db, tenant, proposal, stage, **extra):
        body = {
            "event_id": str(uuid4()),
            "proposal_id": proposal["id"],
            "job_id": proposal["job_id"],
            "stage": stage,
            "occurred_at": datetime.now(UTC).isoformat(),
            "source": "student_sim",
            **extra,
        }
        db.execute("INSERT INTO events(tenant,body) VALUES (?,?)", (tenant, json.dumps(body)))

    def write(self, tenant, tool, payload):
        fingerprint = hashlib.sha256(
            json.dumps({"tool": tool, "payload": payload}, sort_keys=True).encode()
        ).hexdigest()
        key = payload["idempotency_key"]
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT fingerprint,result FROM writes WHERE tenant=? AND key=?", (tenant, key)
            ).fetchone()
            if prior:
                if prior[0] != fingerprint:
                    raise SimConflict("Idempotency key has different arguments")
                return json.loads(prior[1])
            if tool == "submit_proposal":
                job = self.jobs.get(payload["job_id"])
                if job is None:
                    raise KeyError("Job not found")
                if db.execute(
                    "SELECT id FROM proposals WHERE tenant=? AND job_id=?", (tenant, job["id"])
                ).fetchone():
                    raise SimConflict("A proposal already exists for this account and job")
                db.execute(
                    "INSERT OR IGNORE INTO accounts VALUES (?,?)", (tenant, self.starting_connects)
                )
                changed = db.execute(
                    "UPDATE accounts SET balance=balance-? WHERE tenant=? AND balance>=?",
                    (job["connects_cost"], tenant, job["connects_cost"]),
                ).rowcount
                if not changed:
                    raise SimConflict("Insufficient Connects")
                result = {
                    "id": str(uuid4()),
                    "job_id": job["id"],
                    "status": "submitted",
                    "connects_spent": job["connects_cost"],
                    "source": "student_sim",
                }
                db.execute(
                    "INSERT INTO proposals VALUES (?,?,?,?)",
                    (result["id"], tenant, job["id"], json.dumps(payload)),
                )
                self._event(db, tenant, result, "submitted", connects_spent=job["connects_cost"])
                if self.client_mode == "rule":
                    self._simulate_client(db, tenant, result, job, payload)
                else:
                    db.execute(
                        "INSERT INTO pending_clients VALUES (?,?,0,0,NULL)", (result["id"], tenant)
                    )
            elif tool == "send_message":
                conversation = payload["conversation_id"]
                if not db.execute(
                    "SELECT id FROM proposals WHERE id=? AND tenant=?", (conversation, tenant)
                ).fetchone():
                    raise KeyError("Conversation not found")
                result = {
                    "id": str(uuid4()),
                    "conversation_id": conversation,
                    "status": "sent",
                    "source": "student_sim",
                }
                body = {**result, "text": payload["text"], "sender": "freelancer"}
                db.execute(
                    "INSERT INTO messages VALUES (?,?,?,?)",
                    (result["id"], tenant, conversation, json.dumps(body)),
                )
            else:
                raise ValueError("Unsupported simulator write")
            db.execute(
                "INSERT INTO writes VALUES (?,?,?,?)",
                (tenant, key, fingerprint, json.dumps(result)),
            )
            return result

    def _simulate_client(self, db, tenant, proposal, job, payload):
        """Declared rule model, not evidence of real-world proposal effectiveness."""
        text = payload["text"].lower()
        coverage = sum(skill.lower() in text for skill in job["required_skills"]) / len(
            job["required_skills"]
        )
        priced = job["budget_min"] <= payload["bid_amount"] <= job["budget_max"]
        replied = job["gold"]["bid"] and priced and coverage >= 1 / 3 and len(text.split()) >= 12
        self._record_client(db, tenant, proposal, replied, coverage >= 2 / 3)

    def _record_client(self, db, tenant, proposal, replied, hired):
        self._event(db, tenant, proposal, "viewed")
        if replied:
            self._event(db, tenant, proposal, "replied")
            self._event(db, tenant, proposal, "interview")
            message_id = str(uuid4())
            body = {
                "id": message_id,
                "conversation_id": proposal["id"],
                "sender": "client",
                "text": (
                    "Thanks for the proposal. Could you suggest interview times "
                    "and clarify the first milestone?"
                ),
                "synthetic": True,
            }
            db.execute(
                "INSERT INTO messages VALUES (?,?,?,?)",
                (message_id, tenant, proposal["id"], json.dumps(body)),
            )
            if hired:
                self._event(db, tenant, proposal, "hired")
        else:
            self._event(db, tenant, proposal, "lost")

    def claim_client(self, now):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT proposal,tenant,attempts FROM pending_clients "
                "WHERE next_at<=? AND attempts<3 ORDER BY rowid LIMIT 1",
                (now,),
            ).fetchone()
            if not row:
                return None
            db.execute(
                "UPDATE pending_clients SET next_at=?,attempts=attempts+1 WHERE proposal=?",
                (now + 300, row[0]),
            )
            request = json.loads(
                db.execute("SELECT body FROM proposals WHERE id=?", (row[0],)).fetchone()[0]
            )
            return {
                "proposal_id": row[0],
                "tenant": row[1],
                "attempt": row[2] + 1,
                "request": request,
                "job": self.jobs[request["job_id"]],
            }

    def resolve_client(self, claim, decision, metrics):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute(
                "SELECT proposal FROM pending_clients WHERE proposal=?", (claim["proposal_id"],)
            ).fetchone():
                return False
            job, request = claim["job"], claim["request"]
            priced = job["budget_min"] <= request["bid_amount"] <= job["budget_max"]
            eligible = priced and job["gold"]["bid"]
            replied = eligible and decision in {"reply", "interview", "hire"}
            hired = replied and decision == "hire"
            proposal = {"id": claim["proposal_id"], "job_id": job["id"], "source": "student_sim"}
            self._record_client(db, claim["tenant"], proposal, replied, hired)
            db.execute(
                "INSERT INTO client_decisions VALUES (?,?)",
                (
                    claim["proposal_id"],
                    json.dumps(
                        {
                            "decision": decision,
                            "effective_reply": replied,
                            "metrics": metrics,
                            "synthetic": True,
                        }
                    ),
                ),
            )
            db.execute("DELETE FROM pending_clients WHERE proposal=?", (claim["proposal_id"],))
            return True

    def client_failed(self, claim, now):
        with self.db() as db:
            db.execute(
                "UPDATE pending_clients SET next_at=?,error=? WHERE proposal=?",
                (
                    now + 10 * 2 ** claim["attempt"],
                    "Client model unavailable; outcome pending",
                    claim["proposal_id"],
                ),
            )

    def messages(self, tenant, conversation):
        with self.db() as db:
            if not db.execute(
                "SELECT id FROM proposals WHERE tenant=? AND id=?", (tenant, conversation)
            ).fetchone():
                raise KeyError("Conversation not found")
            return [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT body FROM messages WHERE tenant=? AND conversation=? ORDER BY rowid",
                    (tenant, conversation),
                )
            ]

    def events(self, tenant, after=0):
        with self.db() as db:
            return [
                {"cursor": row[0], **json.loads(row[1])}
                for row in db.execute(
                    "SELECT seq,body FROM events WHERE tenant=? AND seq>? ORDER BY seq LIMIT 200",
                    (tenant, after),
                )
            ]
