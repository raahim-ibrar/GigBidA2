"""Measured research and delivery pages for the ten-page engineering review."""

from reportlab.lib.units import mm


def append_research(body, sub, section, table, source, read):
    analysis = read("evals/results/gemini-orchestration-v1/analysis.json")
    tools = read("evals/results/student-tool-study-v3/results.json")
    quality = read("evals/results/judge-proposals-final/results.json")
    calibration = read("evals/results/judge-calibration-v4/agreement.json")
    panel = read("evals/results/human-panel-v1/results.json")

    section(8, "R&D A/C: tools and architectures")
    body(
        "Fifty identical fully synthetic jobs were run through a real ReAct agent, the "
        "langgraph-supervisor package and the production hand-built graph: 150 executions. "
        "Gemini 3.1/3.5 Flash-Lite assignment was blocked by job, balanced within persona, "
        "and identical across architectures. This optional closed-model study is separate "
        "from the two open-weight local configurations. Each run had a 20,000-token cap; "
        "native graphs had 30 steps and the hand graph 40, with two Critic revisions. "
        "The frozen plan, as-run source snapshot and all failed observations are retained."
    )
    rows = []
    for name, result in analysis["conditions"].items():
        rows.append(
            [
                name,
                f"{result['error_free']}/50",
                f"{result['decision_stage_correct_n']}/50",
                f"{result['submissions']}/50",
                f"{result['replies']}/50",
                f"{result['measured_tokens_mean']:.0f}",
                f"{result['wall_seconds_p95_nearest_rank']:.1f}",
            ]
        )
    table(
        [
            "Architecture",
            "No error",
            "Correct decision",
            "Submitted",
            "Replies",
            "Tokens/job",
            "p95 s",
        ],
        rows,
        [31 * mm, 22 * mm, 27 * mm, 23 * mm, 21 * mm, 25 * mm, 22 * mm],
    )
    sub(
        "Decision versus completion",
        "The hand graph's 49/50 correct decisions are intermediate decisions: 13 runs failed "
        "later. Error-free correct decisions were 36/50 for ReAct, 23/50 for supervisor and "
        "36/50 for hand graph. The supervisor completed only 24/50 error-free, exposing "
        "delegation/context overhead under this budget. ReAct completed 41/50, hand graph "
        "37/50. Scam rejection was 1/6 for ReAct, 5/6 for supervisor and 6/6 for hand graph. "
        "ReAct's higher completion count therefore includes unsafe synthetic bids; "
        "it is not a sufficient reason to ship it.",
    )
    sub(
        "Failures, latency and cost",
        "Of 48 failures, 39 hit token/step budgets, four timed out, three were provider or "
        "structured-output failures and two were other observed stops. Measured successful-call "
        "tokens total 1,368,464; 58 native calls had unknown usage. Waits within attempts "
        "contribute to latency; between-attempt daily-quota pauses are not fully represented. "
        "All three p95 values exceed the declared 60-second analysis target. API billing "
        "was not independently verified and remains unknown, not asserted as zero.",
    )
    table(
        ["40-task tool condition", "Tool / argument accuracy", "Tokens/task"],
        [
            [
                name,
                f"{r['tool_accuracy']:.0%} / {r['argument_accuracy']:.0%}",
                f"{r['tokens_per_task']:.1f}",
            ]
            for name, r in tools["results"].items()
        ],
        [65 * mm, 66 * mm, 40 * mm],
    )
    body(
        "All 120 GPT-OSS 120B native tool calls were correct on this easy synthetic set. "
        "Fine tools used fewer tokens than coarse tools; rewritten descriptions did not "
        "improve already-perfect accuracy. No claim of real-task superiority follows."
    )
    source(
        "gemini-orchestration-v1/{plan,analysis,progress}.json and runs.jsonl; "
        "student-tool-study-v3/{plan,results}.json under evals/results/."
    )

    section(9, "Grounding, human review and X2")
    body(
        "The independent judge is Nvidia Nemotron 3.5 Lightning via the fixed OpenRouter "
        "free route, rather than either Gemini generator. Its rubric was frozen before "
        "human labels were compared. Output-protocol pilots with extra claim indices were "
        "rejected, retained separately, and repaired using per-item bounded claim schemas; the "
        "support and quality rubric was not tuned to the human answers."
    )
    table(
        ["Calibration on 30 human-labelled examples", "Observed agreement"],
        [
            [
                "Supported / unsupported / non-factual",
                f"{calibration['support']['agreement']:.0%}; "
                f"Cohen kappa {calibration['support']['kappa']:.3f}",
            ],
            [
                "Quality, 1-5 ordinal scale",
                f"{calibration['quality']['agreement']:.1%} exact; "
                f"weighted kappa {calibration['quality']['kappa']:.3f}",
            ],
        ],
        [108 * mm, 63 * mm],
    )
    body(
        "Claim agreement is limited. Judge scores below are proxy estimates, not verified "
        "truth. One human and purpose-built examples do not establish transfer to full drafts. "
        "All available drafts, including later-failing runs, are scored; no-draft runs remain "
        "failures in the system metrics. Submitted-only figures are saved separately."
    )
    table(
        [
            "Available drafts",
            "n",
            "Mean quality / 5",
            "Unsupported / factual claims",
            "Drafts flagged",
        ],
        [
            [
                name,
                str(r["n_drafts"]),
                f"{r['mean_quality_1_to_5']:.2f}",
                f"{r['claim_counts'].get('unsupported', 0)}/"
                f"{sum(r['claim_counts'].get(k, 0) for k in ('supported', 'unsupported'))}",
                str(r["drafts_with_unsupported_claim"]),
            ]
            for name, r in quality["all_available_drafts_including_failures"].items()
        ],
        [37 * mm, 14 * mm, 33 * mm, 57 * mm, 30 * mm],
    )
    sub(
        "Blind classmate panel",
        f"Two user-supplied reviewers rated twelve anonymized raw Qwen proposal pairs: "
        f"{panel['model_votes']['qwen3.5-4b']} votes for 4B and "
        f"{panel['model_votes']['qwen3-8b']} for 8B. Reviewers agreed on 11/12 pairs "
        "(kappa 0.833). This small convenience panel does not establish a winning model. "
        "Twenty-four ratings are twelve repeated jobs, not twenty-four independent jobs. "
        "Reviewer identity/independence was not verified; student-2 was reconstructed from "
        "the user's statement that only the final choice differed. This panel evaluates "
        "the earlier local raw candidates, not current Gemini architecture quality.",
    )
    sub(
        "X2: randomized proposal opening",
        "The hand-graph cohort was assigned before execution to evidence-first or "
        "problem-first openings, 25 jobs each. Intention-to-treat replies were 12/25 (48%) "
        "and 17/25 (68%). Evidence-minus-problem difference: -20 percentage points; "
        "two-sided Fisher p=0.252, conservative 95% Hoeffding interval [-79.2, +39.2] points. "
        "The observed difference is inconclusive. The pooled test ignores assignment "
        "strata; per-persona counts are saved. Rule-client outcomes are not real demand.",
    )
    source(
        "evals/results/judge-calibration-v4/agreement.json; judge-proposals-final/results.json; "
        "human-panel-v1/results.json; gemini-orchestration-v1/analysis.json."
    )

    section(10, "Delivery, limitations and reproduction")
    table(
        ["Requirement", "Evidence state"],
        [
            [
                "R&D A / B / C",
                "Tool design, five retrieval variants, two open configurations and "
                "150 architecture executions recorded; all negative results remain visible.",
            ],
            [
                "Human evaluation and X2",
                "30 calibration labels, two blind panel responses, "
                "independent proposal judging and randomized rule-client "
                "outcome analysis recorded.",
            ],
            [
                "Public delivery",
                "Public repository/article, installable MCP command and Inspector screenshots. "
                "Approved proposal/crash, scam, injection and real Critic trace cases verified. "
                "Temporary app/HTTP demo is off; E6 uptime is excluded, not satisfied.",
            ],
            [
                "Integration gaps",
                "GitHub README/code import and immutable audit snapshots are verified. "
                "Real Upwork OAuth/live reads are verified; preview writes are fixture-tested. "
                "Final submissions/messages are disabled; production-wide auth limits "
                "remain incomplete.",
            ],
            [
                "Unmeasured requirements",
                "Paired component-level injection-boundary study is recorded separately. "
                "No hidden-test results or observed instructor-policy-change "
                "implementation time is claimed.",
            ],
            [
                "Video",
                "Genuine three-minute UI recording and 30-second GIF: proposal approval, "
                "actual API restart, scam/injection rejection and approved client reply. "
                "Fictional account, real hosted inference, one simulator submission receipt.",
            ],
        ],
        [43 * mm, 128 * mm],
    )
    sub(
        "Engineering finding",
        "The custom graph improves intermediate decision coverage but does not eliminate "
        "writer/verifier budget failures. ReAct completes more jobs under this protocol. "
        "A reliable approval boundary and durable replay do not imply reliable generation. "
        "The next justified work is reducing verifier/context overhead, testing on less "
        "templated data, and obtaining stronger human agreement before quality claims.",
    )
    sub(
        "Reproduce without mixing cohorts",
        "Use https://github.com/raahim-ibrar/GigBidA2 and the current README. Run the "
        "download/preprocessing scripts, student_retrieval, student_generation and "
        "student_orchestration runners with their frozen plans and source snapshots. "
        "Gemini results are the optional closed-model profile; local Qwen and partial Groq "
        "runs remain distinct. Run evals.analyse_final_research and "
        "evals.analyse_proposal_quality to derive the final tables without new inference. "
        "Secrets and raw historical job text are excluded from Git.",
    )
    sub(
        "AI assistance and responsibility",
        "Codex assisted with implementation, tests, experiment tooling and documentation. "
        "The student supplied the calibration labels and reported classmate responses. "
        "Fictional sources and outcomes are labelled; no model-generated observation is "
        "presented as a human rating. The student must review the work and explain these "
        "trade-offs in the viva. Technical narrative: docs/TECHNICAL_WRITEUP.md.",
    )
    source("docs/{STATUS,RESULTS,VERIFICATION,AI_USAGE,TECHNICAL_WRITEUP}.md; evals/results/.")
