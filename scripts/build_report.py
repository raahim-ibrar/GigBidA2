"""Render an evidence-linked engineering review. Missing studies remain explicit."""

import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PURPLE = colors.HexColor("#7048aa")
INK = colors.HexColor("#242031")
MUTED = colors.HexColor("#645e73")
PALE = colors.HexColor("#f3eff9")


def read(path, default=None):
    source = Path(path)
    return json.loads(source.read_text(encoding="utf-8-sig")) if source.exists() else default


def build(output="output/pdf/GigBid_RnD_Report.pdf"):
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="BodyReview",
            fontName="Helvetica",
            fontSize=9.3,
            leading=14,
            textColor=INK,
            spaceAfter=9,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionReview",
            fontName="Helvetica-Bold",
            fontSize=19,
            leading=24,
            textColor=PURPLE,
            spaceAfter=15,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SubReview",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=INK,
            spaceBefore=11,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CellReview",
            fontName="Helvetica",
            fontSize=7.5,
            leading=11,
            textColor=INK,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SourceReview",
            fontName="Helvetica",
            fontSize=7.4,
            leading=11,
            textColor=MUTED,
            spaceAfter=8,
        )
    )
    story = []

    def para(text, style="BodyReview"):
        return Paragraph(escape(str(text)), styles[style])

    def body(text):
        story.append(para(text))

    def sub(title, text):
        story.extend([para(title, "SubReview"), para(text)])

    def section(number, title):
        if story:
            story.append(PageBreak())
        story.append(para(f"{number:02} / {title}", "SectionReview"))

    def table(headers, rows, widths):
        data = [[para(value, "CellReview") for value in headers]]
        data += [[para(value, "CellReview") for value in row] for row in rows]
        grid = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        grid.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), PALE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, PURPLE),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#dfdbe5")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.extend([grid, Spacer(1, 9)])

    def source(text):
        story.append(para("Evidence: " + text, "SourceReview"))

    verification = read("evals/results/engineering-verification.json", {})
    retrieval = read("evals/results/student-retrieval/results.json")["results"]
    generation = read("evals/results/student-generation-v3/progress.json", {})
    failures = read("evals/results/student-generation-v3/failures.json", [])
    data = read("evals/results/student-data-manifest.json", {})

    section(1, "GigBid engineering review")
    story.append(para("AI-4016 / Raahim / November 2026", "SourceReview"))
    body(
        "A freelancer copilot with a durable human approval boundary, portfolio-grounded "
        "drafts, and an independently implemented student marketplace simulator."
    )
    body(
        "This engineering review distinguishes implemented behaviour, controlled synthetic "
        "measurements and evidence still missing. It is not a claim of completed hidden-test "
        "performance or a deployed public service. Negative model results are retained."
    )
    sub(
        "Problem and constraints",
        "The workflow is discovery, risk and fit assessment, pricing, "
        "grounded drafting, human review and client response. Automation may recommend, skip "
        "or prepare an action. It must never send a proposal, send a message or spend Connects "
        "without a matching approval. Edits invalidate the previous approval and are rechecked.",
    )
    sub(
        "Declared budgets",
        "The configured targets are p95 analysis within 60 seconds, proposal "
        "preparation within 120 seconds, and inference API targets of USD 0.02 and USD 0.05 "
        "respectively. Thread budgets bound steps, tokens and Critic revisions. Targets are not "
        "achieved measurements. Local API charges exclude GPU hardware and electricity.",
    )
    table(
        ["Evidence class", "Observed scope"],
        [
            [
                "Backend control/integration",
                f"{verification.get('backend', {}).get('passed', 'Not recorded')} "
                "passing checks at the recorded checkpoint; opt-in runtime tests are separate.",
            ],
            [
                "Browser flows",
                "Existing flows plus a separate simulator outage/retry/submission/reply test; "
                "deterministic role fixtures.",
            ],
            [
                "Retrieval study",
                "60 answerable synthetic tasks plus six unrelated tasks; real BGE/MiniLM "
                "inference.",
            ],
            [
                "Local graph study",
                "Two configurations, 30 synthetic jobs each. Grounding failures dominate.",
            ],
        ],
        [43 * mm, 128 * mm],
    )
    source(
        "evals/results/engineering-verification.json; student-retrieval/results.json; "
        "student-generation-v3/progress.json. Baseline source checkpoint: 4fed02f."
    )

    section(2, "Architecture and ownership")
    body(
        "The Next.js client uses typed FastAPI contracts. The API authenticates and persists "
        "work; Redis/Arq runs indexing and graph jobs. Postgres owns checkpoints, approval "
        "receipts, immutable effect records and the memory promotion ledger. Qdrant indexes "
        "tenant-filtered evidence IDs; source text remains in source storage."
    )
    table(
        ["Graph", "Execution and rationale"],
        [
            [
                "Bid",
                "Scout intake fans out to Analyst, Risk and Matcher. A join reconciles fit. "
                "Decision, pricing, writer, verifier, bounded Critic, compliance and exact preview "
                "lead to a human interrupt. An approved executor is the only write route.",
            ],
            [
                "Conversation",
                "One durable thread per conversation. Liaison classifies intent and "
                "drafts using portfolio evidence. Calendar slots come from Workspace. Verification "
                "and a fresh interrupt precede a saved draft or simulator message.",
            ],
        ],
        [30 * mm, 141 * mm],
    )
    sub(
        "Three separate stores",
        "State contains current job/conversation facts and typed "
        "handoffs. Execution events record progress, usage and safe failures. Long-term memory "
        "contains only promoted observations: repeated human-confirmed edits for style, and "
        "verified provider events for outcomes. Raw tool output does not become memory.",
    )
    sub(
        "Capability boundaries",
        "Portfolio MCP exposes search, source reads, resources and a "
        "screening prompt. Marketplace MCP wraps one port. Workspace MCP provides local "
        "calendar and draft tools. The host binds tenant and run identity; these are not "
        "model arguments. The HTTP wrapper uses bearer authentication and a shared Redis limit. "
        "Actual Upwork OAuth and GitHub ingestion are still absent.",
    )
    sub(
        "Crash and replay",
        "The graph uses Postgres checkpoints, an advisory lock and a SQL "
        "worker-token fence. The latest approval binds interrupt ID, version, digest, tool, "
        "payload and idempotency key. The upstream simulator has an atomic debit/receipt "
        "transaction. Reconciliation records an already observed effect rather than authorising "
        "a new one. Calendar, budget and evidence freshness are rechecked at execution.",
    )
    source(
        "agent/graphs; agent/runtime.py; mcp_servers; worker/simulator_sync.py; "
        "tests/integration/test_simulator_flow.py; docs/GRAPHS.md."
    )

    section(3, "Data and simulation")
    body(
        "The instructor's follow-up allows approved Kaggle datasets and clearly identified "
        "synthetic fields. The original GigSim was not delivered; the user confirmed that "
        "students must build their own. Our implementation is independent, and hidden-test "
        "compatibility is not established."
    )
    body(
        "The selected source is Asaniczka's Upwork Job Postings Dataset 2024, Kaggle version 1, "
        "with uploader-declared ODC Attribution terms. No Upwork website is scraped. Raw and "
        "derived job text is ignored by Git; attribution, version and hashes are documented. "
        "The database license does not independently establish rights in every job's text."
    )
    table(
        ["Source/preprocessing", "Recorded count"],
        [
            ["Input CSV rows", str(data.get("counts", {}).get("input_rows", "Not recorded"))],
            ["Selected per persona", "200 AI/ML, 200 full-stack, 200 analyst"],
            [
                "Missing/invalid budgets",
                str(data.get("counts", {}).get("dropped_unknown_budget", "Not recorded")),
            ],
            [
                "Text outside length bounds",
                str(data.get("counts", {}).get("dropped_text_bounds", "Not recorded")),
            ],
            [
                "Duplicate normalized content",
                str(data.get("counts", {}).get("dropped_duplicates", "Not recorded")),
            ],
        ],
        [111 * mm, 60 * mm],
    )
    sub(
        "Field provenance",
        "Base titles, descriptions, publication dates and posted budgets "
        "are historical observations. Persona/skills, client identity/history, Connects costs, "
        "screening questions, inserted attacks and all outcomes are generated or derived. "
        "USD is an assumption; posted budgets are not human-validated fair-price labels. "
        "Inserted scam labels do not accuse the original job authors.",
    )
    sub(
        "Fictional portfolios",
        "Three separately labelled personas have 20 case studies, "
        "three duplicate READMEs, one CV and 150 generated past proposals each. These are "
        "not Raahim's experience. Generated historical won/replied labels are not experimental "
        "successes. The retrieval gold uses project identity and is easier than real-job "
        "relevance.",
    )
    sub(
        "Client model",
        "The baseline studies use a transparent rule client: eligibility, "
        "budget, length and skill coverage determine outcomes. Optional local LLM client mode "
        "has a durable outbox and bounded retries. Its outcomes are a different experimental "
        "condition and are not mixed into the rule-client results.",
    )
    source(
        "docs/DATA_CARD.md; scripts/prepare_student_data.py; scripts/student_personas.py; "
        "evals/results/student-data-manifest.json; simulator/store.py and client.py."
    )

    section(4, "R&D B: measured retrieval")
    body(
        "Predeclared H1: hybrid retrieval plus cross-encoder reranking improves Recall@5 "
        "over dense V0 on industry-specific tasks. The frozen cohort has identical tasks and "
        "project-identity gold across all variants. Embeddings are BGE-small; reranking uses "
        "MiniLM. Timing excludes the separately recorded model warm-up."
    )
    rows = []
    for name, result in retrieval["variants"].items():
        a, b = result["at_5"]["overall"], result["at_10"]["overall"]
        rows.append(
            [
                name.upper(),
                f"{a['macro_recall_at_k']:.3f}",
                f"{a['macro_mrr_at_k']:.3f}",
                f"{b['macro_ndcg_at_k']:.3f}",
                f"{result['p95_seconds']:.3f}",
                f"{a['unanswerable_with_retrieval']}/6",
            ]
        )
    table(
        ["Variant", "Recall@5", "MRR@5", "nDCG@10", "p95 s", "Unrelated retrieval"],
        rows,
        [20 * mm, 26 * mm, 24 * mm, 29 * mm, 24 * mm, 48 * mm],
    )
    sub(
        "Conclusion",
        "H1 is not supported on this controlled set: V0 and V3 both have full "
        "recall. Reranking improves ordering. Requirement decomposition loses recall when "
        "generic requirements dominate rank fusion. V8 rejects the unrelated tasks at greater "
        "latency. This cohort is highly templated; ceiling effects limit generalisation.",
    )
    sub(
        "Shipped choice and ablations",
        "The declared rule selects by Recall@5, then nDCG@10, "
        "then p95. It selects V3. V3 versus V2 removes the reranker; V2 versus V0 removes "
        "lexical fusion; V8 versus V3 removes correction. These comparisons do not establish "
        "a real-client reply-rate benefit. Per-persona metrics and raw rankings remain available.",
    )
    sub(
        "Grounding",
        "The verifier assesses cover and screening sentences. Past claims need "
        "live supporting IDs; numerical achievements receive an additional source check. "
        "A source UUID is an identifier, not an achievement number. Future plans now have "
        "an explicit non-factual verdict. Human calibration and the blind panel "
        "are reported on page 9; "
        "uncalibrated model judgements are not independent gold labels.",
    )
    source(
        "evals/STUDENT_RESEARCH_PLAN.md; evals/results/student-retrieval/*.jsonl and "
        "results.json; agent/proposal_nodes.py; tests/unit/test_proposal_nodes.py."
    )

    section(5, "Models and negative results")
    body(
        "The frozen baseline compares all-role local Qwen 3.5 4B and Qwen 3 8B on the same "
        "30 synthetic jobs. Retrieval is held at V0 and fallback is disabled. Errors and "
        "skips stay in the denominator. These are open-model configurations, not a comparison "
        "of orchestration frameworks. Source checkpoint 4fed02f preserves the baseline."
    )
    rows = []
    for name, result in generation.get("models", {}).items():
        rows.append(
            [
                name,
                str(result["recorded_jobs"]),
                str(result["statuses"]),
                f"{result['p95_job_seconds']:.1f}",
                str(result["research_submissions"]),
            ]
        )
    table(
        ["Configuration", "Jobs", "Statuses", "p95 s", "Candidates submitted"],
        rows,
        [35 * mm, 15 * mm, 70 * mm, 19 * mm, 32 * mm],
    )
    sub(
        "Interpretation",
        "Most positive jobs stop at grounding. A diagnostic replay shows "
        "the local verifier calling future plans non-experience while still marking them "
        "unsupported. The writer also sometimes omits screening answers. This is a contract "
        "and prompt-handling failure as well as a model limitation. No useful reply or hire "
        "rate can be inferred from candidates that never reach submission.",
    )
    sub(
        "Fix and hosted recheck",
        "The revised contract distinguishes non-factual plans from "
        "past experience, explicitly tags the normal writer task, and keeps the past-claim "
        "guard. Groq GPT-OSS 20B/120B provide an optional hosted open-weight profile. A small "
        "control check correctly handles a future plan, unsupported number and supported "
        "source claim. The completed Gemini architecture study is separate "
        "from this frozen baseline; "
        "changed model, contract and retrieval prevent a clean causal model-only comparison.",
    )
    sub(
        "Cost and speed",
        "Usage records retain tokens, worker/model seconds and local "
        "generation throughput. Local inference API charge is zero but hardware/electricity "
        "are not priced. Qwen 4B generated 79.3 output tokens/s; 8B 64.4 tokens/s. "
        "The later inventory records an RTX 3070 Ti Laptop GPU (8 GB), Ryzen 9 6900HX "
        "and 15.2 GiB RAM; it is not an as-run hardware trace. Hosted actual "
        "billing is unknown unless verified, so it stays null. "
        "Groq has shared token/request guards and a daily study cap. A free API quota is not "
        "an unlimited budget, and rate-limit wait counts toward wall-clock latency.",
    )
    source(
        "evals/results/student-generation-v3/plan.json, progress.json and raw model JSONL; "
        "local-hardware-inventory.json; agent/providers/groq.py; tests/unit/test_groq_models.py."
    )

    section(6, "Failure analysis")
    body(
        "The table retains distinct failed jobs rather than selecting only successful "
        "proposals. Categories identify the visible stop condition; a stop does not prove "
        "that every removed sentence was actually false."
    )
    table(
        ["Job", "Configuration", "Category"],
        [[row["job_id"], row["model"], row["category"]] for row in failures[:10]],
        [79 * mm, 42 * mm, 50 * mm],
    )
    sub(
        "Screening grounding",
        "Future validation plans were removed even when they made "
        "no past-work claim. The fix is an explicit not-applicable verdict for non-factual "
        "text, with a separate host guard that still rejects past experience mislabeled "
        "non-factual. Deterministic regressions pass; broader human validation remains necessary.",
    )
    sub(
        "Cover grounding",
        "Some drafts overstate demonstration work or name unproven "
        "libraries. Those sentences should remain blocked. Synthetic coursework is explicitly "
        "framed as a demonstration, source IDs stay in structured claims, and the ordinary "
        "writer task is now unambiguous. These changes must not erase baseline failures.",
    )
    sub(
        "Schema and execution failures",
        "Earlier diagnostic runs exposed missing study "
        "checkpoint initialisation and truncated verbose verifier output. Setup failures are "
        "separate from model-quality results. Durable storage is initialised before graph "
        "execution and verifier reasons are bounded by the prompt. No hidden success is inferred.",
    )
    source(
        "evals/results/student-generation-v3/failures.json and raw records; "
        "tests/unit/test_proposal_nodes.py; docs/VERIFICATION.md."
    )

    section(7, "Safety, policy and operations")
    sub(
        "Approval is a transaction boundary",
        "Read tools cannot grant write permission. "
        "The executor requires the exact approved preview and current draft digest. "
        "Changes to evidence, budget, calendar or connection can block execution. The simulator "
        "atomically deduplicates the effect and debit. Repeated worker calls do not spend twice.",
    )
    sub(
        "Untrusted inputs",
        "Job descriptions, portfolio text and client messages are data. "
        "Prompts delimit their role, and deterministic guards flag injected instructions, "
        "off-platform requests, contact details and guarantees. PII masking covers logs/events. "
        "These are layered defences, not a measured zero attack-success claim. A before/after "
        "injection experiment is still required.",
    )
    sub(
        "Policy update",
        "Rules, model routes and thresholds are configuration. The announced "
        "instructor update was not supplied in this session. It would be dishonest to claim "
        "an observed change-request implementation time. The simulator's own rules are "
        "documented independently; they do not stand in for a missing instructor policy.",
    )
    sub(
        "Production state",
        "The production frontend build, generated API contracts, worker "
        "packaging and local services are implemented. Same-origin API proxying avoids sending "
        "a public browser to its own localhost. Public hosting is not yet configured. "
        "Upwork OAuth, GitHub ingestion, a complete tracing backend and production-wide auth "
        "limits remain required. The local address is not a public deployment.",
    )
    sub(
        "Recovery evidence",
        "Backend and browser flows verify saved approval after reload, "
        "exactly-once simulator effects, an outage banner, explicit checkpoint retry, event "
        "import and approved replies. Browser role models are deterministic fixtures; those "
        "tests establish control behaviour rather than proposal quality.",
    )
    source(
        "mcp_servers/marketplace/service.py; worker/simulator_sync.py; "
        "tests/integration/test_simulator_flow.py; apps/web/tests/e2e/simulator.spec.ts."
    )

    from report_research_sections import append_research

    append_research(body, sub, section, table, source, read)

    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)

    def footer(canvas, doc):
        canvas.setStrokeColor(PURPLE)
        canvas.setLineWidth(1)
        canvas.line(19 * mm, 18 * mm, A4[0] - 19 * mm, 18 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(
            19 * mm, 12 * mm, "GigBid / AI-4016 / Engineering review - measured evidence"
        )
        canvas.drawRightString(A4[0] - 19 * mm, 12 * mm, str(doc.page))

    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        rightMargin=19 * mm,
        leftMargin=19 * mm,
        topMargin=20 * mm,
        bottomMargin=25 * mm,
        title="GigBid engineering review",
        author="Raahim",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(target.resolve())


if __name__ == "__main__":
    build()
