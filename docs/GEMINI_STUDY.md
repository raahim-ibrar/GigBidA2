# Optional Gemini architecture study

The default application profile remains open-weight. `MODEL_PROFILE=paid` enables the optional Google API profile using `GOOGLE_API_KEY` from the ignored `.env`. The profile name does not establish actual billing; recorded USD cost is unknown.

The Gemini research uses the same 50 fully fictional jobs and fictional portfolio cases as the architecture protocol. It sends no uploaded private CV to Google. Models are blocked by job across all three architectures: Gemini 3.1 Flash-Lite and Gemini 3.5 Flash-Lite. This is an optional closed-model study and does not replace the separately measured open-weight configurations.

Results are isolated at `evals/results/gemini-orchestration-v1`. Existing Groq results remain at `evals/results/student-orchestration-v1`; they must not be merged as one model-controlled experiment. The original Groq background process was stopped before Gemini launch.

The transport preserves Google tool thought signatures across normalized LangChain messages. It validates structured outputs with the existing Pydantic contracts. Local request gates allow 10 requests/minute and 480 requests/model/Pacific calendar day, below the account's displayed limits. Provider limits can still differ. Temporary server errors have at most two retries. Unknown failed-request usage is recorded separately from measured successful usage in native graph telemetry; USD billing is not inferred from free-tier availability.

Focused verification: 12 tests passed, including structured handoff validation, secret exclusion, signature preservation, transient outage retry, Groq regression tests, and real scripted ReAct/supervisor graph termination. These engineering tests do not establish proposal quality.

Private background status is `work/background-gemini-status.json`. The runner saves every completed case and pauses when the local daily quota lacks headroom. Keep Docker and the laptop awake for execution. Stop by creating `work/stop-background-gemini`; the runner checks between cases and during quota waits.
