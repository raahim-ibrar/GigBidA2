# Temporary public demo backed by the laptop

The user chose this zero-hosting-charge route for the demo. The actual Next.js app,
FastAPI API, Linux Docker worker, Postgres, Redis, Qdrant and independent student
simulator run on the laptop. A Cloudflare Quick Tunnel provides public HTTPS to
the demo web port. No Azure VM or paid cloud resource was created.

This is the real application, with real hosted open-weight LLM calls, CPU
embeddings/reranking, durable checkpoints and human approval. It uses a separate
Postgres schema, Redis database 14, simulator database and synthetic demo accounts.
The private uploaded CV and the original local application are not copied into
the demo. Groq API quotas still apply. The original local app remains on port 3000;
the isolated demo uses 3001/8001/8081.

## Current session and login

The current URL and supervisor/child PIDs are recorded in
`work/public-demo/status.json`. The URL is temporary and changes on restart.
Login details are in `work/public-demo/LOGIN.txt` and `accounts.json`; these files
are ignored by Git and must not be published or shown in a recording.

The API enforces the generated HTTPS origin and Secure cookies. PostgreSQL,
Redis and Qdrant are not exposed by the tunnel. The separate simulator uses its
own random access key; the worker's private environment file remains in ignored
`work/public-demo/worker.env`.

## Actual verified examples

The valid synthetic Document Search job reached `awaiting_approval` through
normal queue processing, MCP, Groq generation, verification, Critic and preview:
11 steps, 13,717 tokens charged. No approval or submission was fabricated.
The reviewer can approve the displayed simulator proposal through the app.
Two additional real runs rejected the unpaid/off-platform scam and prompt
injection cases, each with risk 1.0 and no runtime error. Their IDs are saved in
`evals/results/demo-deployment.json`.

Progress is real: streaming SSE remains implemented. Because Cloudflare Quick
Tunnels do not support SSE, the client also replays authenticated, tenant-bound
activity over bounded JSON polling every three seconds while a run is active.
The same saved event IDs deduplicate replay and streaming updates. This is not
simulated progress. See `apps/api/routers/runs.py` and `RunWorkspace.tsx`.

## Keep running / stop

Keep Docker Desktop running, the laptop awake and connected to the Internet.
The screen may turn off. The public site stops working when the tunnel or laptop
stops. Locking the screen alone does not terminate the processes.

The hidden supervisor is `python -m scripts.demo_host`. It starts only its own
demo components and stops them when `work/public-demo/stop` is created. It does
not delete the saved database schema or volumes. The demo Linux worker container
is labelled and named `gigbid-public-demo-worker`; the original worker is separate.

The tunnel binary is the official Cloudflare Windows amd64 release, with its
published SHA-256 verified and recorded in `work/demo-tools/cloudflared-release.json`.
For a fresh checkout, install that binary in `work/demo-tools/cloudflared.exe`,
prepare the existing local database/Redis/Qdrant services and Groq key, build
`gigbid-demo-worker` using `infra/docker/worker.Dockerfile`, and build a standalone
frontend with `API_INTERNAL_URL=http://127.0.0.1:8001` and
`GIGBID_TEST_DIST=.next-demo` before starting the supervisor.

## Scope of proof

This verifies a public laptop-backed demo during the recorded session. It is not
evidence of an always-on cloud deployment, hidden-test performance, or completion
of the remaining published-MCP/tracing/integration requirements. The original
assignment requests continued availability until grading; the user chose this
temporary hosting mode. The optional capped-credit Azure/Vercel configuration
remains documented in `DEPLOYMENT.md` for later use.

Cloudflare reference: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
