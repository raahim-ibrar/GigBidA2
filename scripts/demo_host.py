"""Run an isolated synthetic demo through a temporary public HTTPS tunnel."""

import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema

from apps.api.database import make_engine
from apps.api.settings import Settings
from scripts.seed import seed

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work/public-demo"
SCHEMA = "gigbid_public_demo_20261112"


def main():
    os.chdir(ROOT)
    WORK.mkdir(parents=True, exist_ok=True)
    stop = WORK / "stop"
    stop.unlink(missing_ok=True)
    children, handles = {}, []

    def save(phase, **details):
        (WORK / "status.json").write_text(
            json.dumps(
                {
                    "phase": phase,
                    "updated_unix": time.time(),
                    "schema": SCHEMA,
                    "pids": {name: process.pid for name, process in children.items()},
                    **details,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def start(name, arguments, env):
        log = (WORK / f"{name}.log").open("w", encoding="utf-8")
        handles.append(log)
        children[name] = subprocess.Popen(
            arguments,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return children[name]

    def wait_ready(url, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if stop.exists():
                raise RuntimeError("Demo stopped during startup")
            try:
                if httpx.get(url, timeout=5).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(1)
        raise RuntimeError("Demo service did not become ready: " + url)

    try:
        settings = Settings()
        admin = make_engine(settings.database_url)
        with admin.begin() as connection:
            connection.execute(CreateSchema(SCHEMA, if_not_exists=True))
        admin.dispose()
        database = (
            make_url(settings.database_url)
            .update_query_dict({"options": "-csearch_path=" + SCHEMA})
            .render_as_string(hide_password=False)
        )
        redis = (
            make_url(settings.redis_url).set(database="14").render_as_string(hide_password=False)
        )
        private = WORK / "private-settings.json"
        saved = (
            json.loads(private.read_text())
            if private.exists()
            else {"simulator_key": secrets.token_urlsafe(32)}
        )
        saved.setdefault("mcp_token", secrets.token_urlsafe(40))
        private.write_text(json.dumps(saved), encoding="utf-8")
        env = {
            **os.environ,
            "DATABASE_URL": database,
            "REDIS_URL": redis,
            "MODEL_PROFILE": "hosted_open",
            "GROQ_API_KEY": settings.groq_api_key.get_secret_value(),
            "GITHUB_TOKEN": settings.github_token.get_secret_value(),
            "LANGSMITH_API_KEY": settings.langsmith_api_key.get_secret_value(),
            "LANGSMITH_PROJECT": settings.langsmith_project,
            "LANGSMITH_TRACING": "false",
            "TRACE_EXPORT_ENABLED": "true",
            "STUDENT_SIM_URL": "http://127.0.0.1:8081",
            "STUDENT_SIM_API_KEY": saved["simulator_key"],
            "STUDENT_SIM_DATABASE": str(WORK / "simulator.sqlite"),
            "STUDENT_SIM_CATALOGUE": "synthetic",
            "STUDENT_SIM_CLIENT_MODE": "rule",
            "MODEL_CACHE_DIR": str(settings.model_cache_dir),
            "APP_ENV": "development",
            "COOKIE_SECURE": "false",
        }
        # Migration settings are read from environment; no production/private schema is copied.
        os.environ.update(
            {k: env[k] for k in ("DATABASE_URL", "REDIS_URL", "APP_ENV", "COOKIE_SECURE")}
        )
        save("migrating")
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        start(
            "simulator",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "simulator.app:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8081",
            ],
            env,
        )
        web_env = {**env, "PORT": "3001", "HOSTNAME": "127.0.0.1", "NODE_ENV": "production"}
        dist = os.getenv("GIGBID_DEMO_DIST", ".next-demo-v2")
        start("web", ["node", f"apps/web/{dist}/standalone/server.js"], web_env)
        wait_ready("http://127.0.0.1:3001/sign-in")
        start(
            "tunnel",
            [
                str(ROOT / "work/demo-tools/cloudflared.exe"),
                "tunnel",
                "--url",
                "http://127.0.0.1:3001",
                "--protocol",
                "http2",
            ],
            env,
        )
        save("connecting_tunnel")
        deadline, public = time.monotonic() + 90, None
        while time.monotonic() < deadline:
            log = (WORK / "tunnel.log").read_text(encoding="utf-8", errors="replace")
            matches = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", log)
            if matches:
                public = matches[-1]
                break
            time.sleep(1)
        if not public:
            raise RuntimeError("Tunnel did not provide a public hostname")
        env.update(WEB_ORIGIN=public, APP_ENV="production", COOKIE_SECURE="true")
        start(
            "api",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "apps.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8001",
            ],
            env,
        )
        wait_ready("http://127.0.0.1:8001/health/ready")
        wait_ready("http://127.0.0.1:8081/health")
        worker_env = {
            **env,
            "DATABASE_URL": make_url(database)
            .set(host="postgres")
            .render_as_string(hide_password=False),
            "REDIS_URL": make_url(redis).set(host="redis").render_as_string(hide_password=False),
            "QDRANT_URL": "http://qdrant:6333",
            "MODEL_CACHE_DIR": "/app/work/models",
            "HF_HOME": "/app/work/models/hf",
            "STUDENT_SIM_URL": "http://host.docker.internal:8081",
        }
        worker_keys = [
            "DATABASE_URL",
            "REDIS_URL",
            "QDRANT_URL",
            "MODEL_CACHE_DIR",
            "HF_HOME",
            "MODEL_PROFILE",
            "GROQ_API_KEY",
            "LANGSMITH_API_KEY",
            "LANGSMITH_PROJECT",
            "LANGSMITH_TRACING",
            "TRACE_EXPORT_ENABLED",
            "STUDENT_SIM_URL",
            "STUDENT_SIM_API_KEY",
            "APP_ENV",
            "WEB_ORIGIN",
            "COOKIE_SECURE",
        ]
        worker_file = WORK / "worker.env"
        worker_file.write_text(
            "\n".join(f"{key}={worker_env[key]}" for key in worker_keys) + "\n", encoding="utf-8"
        )
        start(
            "worker",
            [
                "docker",
                "run",
                "--rm",
                "--name",
                "gigbid-public-demo-worker",
                "--label",
                "gigbid.demo.owner=" + SCHEMA,
                "--network",
                "gigbid_default",
                "--env-file",
                str(worker_file),
                "-v",
                "gigbid_model-cache:/app/work/models",
                "gigbid-demo-worker",
            ],
            env,
        )
        save("seeding_synthetic_accounts", public_url=public)
        wait_ready(public + "/api/status")
        seed(public, credentials_path=str(WORK / "accounts.json"), web_origin=public)
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from apps.api.models import User

        engine = make_engine(database)
        with Session(engine) as db:
            tenant = db.scalar(select(User.id).where(User.email == "demo-ai_ml@example.org"))
        engine.dispose()
        if not tenant:
            raise RuntimeError("Seeded AI demo account not found")
        start(
            "portfolio_mcp",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "mcp_servers.http:configured_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8104",
            ],
            {
                **env,
                "GIGBID_TENANT_ID": tenant,
                "GIGBID_MCP_SERVER": "portfolio",
                "MCP_BEARER_TOKEN": saved["mcp_token"],
            },
        )
        (WORK / "MCP-CONNECTION.json").write_text(
            json.dumps(
                {
                    "url": public + "/mcp",
                    "headers": {"Authorization": "Bearer " + saved["mcp_token"]},
                    "account": "AI synthetic demo",
                    "tools": "read-only portfolio",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        save(
            "ready",
            public_url=public,
            credentials_file=str(WORK / "accounts.json"),
            hosting="Laptop frontend/backend via temporary HTTPS tunnel; "
            "not always-on cloud hosting",
        )
        print("Demo ready: " + public, flush=True)
        while not stop.exists():
            dead = [name for name, child in children.items() if child.poll() is not None]
            if dead:
                raise RuntimeError("Demo processes exited: " + ", ".join(dead))
            time.sleep(2)
        save("stopped", public_url=public)
    except Exception as error:
        save("needs_attention", error_type=type(error).__name__, message=str(error))
        raise
    finally:
        if "worker" in children:
            owned = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "gigbid.demo.owner"}}',
                    "gigbid-public-demo-worker",
                ],
                capture_output=True,
                text=True,
            )
            if owned.returncode == 0 and owned.stdout.strip() == SCHEMA:
                subprocess.run(
                    ["docker", "stop", "--time", "10", "gigbid-public-demo-worker"],
                    capture_output=True,
                )
        for child in children.values():
            if child.poll() is None:
                child.terminate()
        for child in children.values():
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    main()
