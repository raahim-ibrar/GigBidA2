"""Declared fictional portfolios. None of these projects describe Raahim's experience."""

from rag.contracts import DocumentMetadata

TOPICS = {
    "ai_ml": [
        (
            "Document search",
            ["Python", "embeddings", "retrieval"],
            "search a document collection",
            "extract text, chunk documents, index embeddings, "
            "evaluate retrieval against held-out questions and expose a Python API",
        ),
        (
            "Ticket classification",
            ["Python", "classification", "evaluation"],
            "route support requests",
            "clean labelled tickets, train a text classifier, "
            "measure per-class precision and recall, and provide a confidence threshold",
        ),
        (
            "Forecast monitoring",
            ["Python", "forecasting", "monitoring"],
            "predict weekly demand",
            "build rolling-window features, compare seasonal baselines, "
            "backtest forecasts and monitor error drift",
        ),
    ],
    "full_stack": [
        (
            "Booking portal",
            ["React", "FastAPI", "PostgreSQL"],
            "manage online reservations",
            "build accessible React forms, a FastAPI service, "
            "PostgreSQL constraints and transactional booking conflict checks",
        ),
        (
            "Commerce dashboard",
            ["TypeScript", "Node.js", "Stripe"],
            "manage orders and payments",
            "implement typed order endpoints, webhook signature "
            "verification, idempotent payment processing and a TypeScript dashboard",
        ),
        (
            "Team workspace",
            ["Next.js", "authentication", "testing"],
            "coordinate a distributed team",
            "implement tenant-scoped authentication, Next.js "
            "workspace screens, server validation and browser regression tests",
        ),
    ],
    "data_analyst": [
        (
            "Revenue reporting",
            ["SQL", "Power BI", "reporting"],
            "explain revenue changes",
            "model a SQL star schema, reconcile revenue totals, "
            "define Power BI measures and build a filterable reporting dashboard",
        ),
        (
            "Experiment analysis",
            ["Python", "statistics", "experiments"],
            "evaluate a product experiment",
            "validate assignment balance, define the analysis "
            "window, calculate confidence intervals and report sample-size limitations",
        ),
        (
            "Data quality",
            ["SQL", "dbt", "validation"],
            "repair unreliable reporting data",
            "profile missing values, deduplicate records, "
            "write dbt uniqueness tests and reconcile source-to-report totals",
        ),
    ],
}
INDUSTRIES = [
    "education",
    "retail",
    "health administration",
    "logistics",
    "publishing",
    "hospitality",
    "professional services",
]
NOTICE = "SYNTHETIC PERSONA EXAMPLE. Fictional work for coursework; not a real client's record."


def cases(persona):
    for index in range(20):
        title, skills, goal, method = TOPICS[persona][index % 3]
        industry = INDUSTRIES[index // 3]
        project = f"Demo {title} / {industry}"
        text = (
            f"# {project}\n\n{NOTICE}\n\n"
            f"The fictional {industry} team needed to {goal}. "
            f"I used {', '.join(skills)} to {method}. "
            "I documented the acceptance criteria, checked malformed inputs, "
            "and supplied reproducible tests and a handover guide. "
            "The prototype was delivered as a scoped demonstration. "
            "No revenue uplift, accuracy number, years of experience or client testimonial "
            "is established by this synthetic example.\n"
        )
        yield {
            "key": f"{persona}-{index:02}",
            "filename": f"case-{index:02}.md",
            "text": text,
            "goal": goal,
            "industry": industry,
            "skills": skills,
            "metadata": DocumentMetadata(
                persona=persona,
                type="case_study",
                project=project,
                skills=skills,
                date=f"2025-{index % 12 + 1:02}-01",
                client_industry=industry,
            ),
        }


def documents(persona):
    rows = list(cases(persona))
    yield from rows
    skills = list(dict.fromkeys(skill for row in rows for skill in row["skills"]))
    yield {
        "filename": "synthetic-cv.md",
        "text": f"# Demo {persona.replace('_', ' ')}\n\n{NOTICE}\n\n"
        f"Skills practiced in fictional prototypes: {', '.join(skills)}. "
        "Experience is limited to the accompanying synthetic case studies. "
        "No professional tenure or paid-client history is claimed.",
        "metadata": DocumentMetadata(persona=persona, type="cv", project="Demo CV", skills=skills),
    }
    for outcome in ("won", "replied", "ignored"):
        proposals = []
        for index in range(50):
            row = rows[index % len(rows)]
            proposals.append(
                f"## Synthetic historical proposal {outcome}-{index:03}\n"
                f"I would help your {row['industry']} team {row['goal']}. "
                f"My fictional example is {row['metadata'].project}. "
                "I would agree a small first milestone and verify acceptance criteria. "
                f"Generated outcome label: {outcome}; not an observed marketplace result."
            )
        yield {
            "filename": f"synthetic-past-proposals-{outcome}.md",
            "text": f"# Fictional past proposals\n\n{NOTICE}\n\n" + "\n\n".join(proposals),
            "metadata": DocumentMetadata(
                persona=persona,
                type="proposal",
                project=f"Demo past proposals / {outcome}",
                skills=skills,
                outcome=outcome,
            ),
        }
    for row in rows[:3]:
        yield {
            "filename": "readme-" + row["filename"],
            "text": row["text"]
            + "\n## Run and test\nInstall the documented dependencies, configure a disposable "
            "database, run unit tests, and inspect validation errors before deployment.",
            "metadata": row["metadata"].model_copy(update={"type": "readme"}),
        }
