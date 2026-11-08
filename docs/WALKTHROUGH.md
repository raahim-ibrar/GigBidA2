# Understanding GigBid

The code will be written with AI assistance. Your job is to understand the decisions, follow a run through the system, identify where failures occur and explain the evidence. The assignment's viva also asks for small live changes, so understanding includes being able to locate and alter configuration or a simple rule.

## One job, from start to finish

1. Currently you enter a job manually. It is saved with a source fingerprint, so repeating the same entry does not create another job. Marketplace scouting awaits the supplied connector assets.
2. Three branches inspect the same raw job concurrently. Analyst extracts requirements; Risk checks scams and client history; Matcher searches the portfolio for evidence. Matcher cannot wait for Analyst output while they are parallel; it derives its own search queries from the post.
3. Decision uses those results to choose skip, watch or bid. Pricing estimates a bid and checks the configured budget.
4. Writer creates a proposal from actual portfolio evidence. Verifier checks its claims. Critic asks for improvements, with a maximum of two rewrites.
5. Local draft checks block contact details, guarantees and other configured risks. Full platform compliance awaits the instructor policy pack.
6. The current preview says exactly what approval does: save a local draft and spend zero Connects. The actual application cost is unknown, and nothing is sent to a marketplace.
7. LangGraph pauses at an interrupt. The user reviews, approves, edits, regenerates one selected paragraph, or rejects. Regeneration preserves other paragraphs, checks the result again, and requests a new approval.
8. The local executor rechecks the approval and current source evidence, then saves one artifact in Postgres. Repeating the operation returns that artifact. External submission still needs a tested provider adapter and its own retry/reconciliation behavior.

The worker now runs proposal business nodes and stores checkpoints in Postgres. Edits go back through verification and need a new review. Tests use labelled deterministic responses to prove control/recovery behavior; real-model checks are separate and do not establish proposal quality or grading results.

## What you can try now

1. Upload a real portfolio source, enter a job, then inspect the proposal and evidence.
2. Edit or regenerate a paragraph. The updated result must be reviewed again before saving.
3. Open Pipeline: an approved local proposal is a draft, not a submitted application.
4. Start a conversation under Messages and enter a client's message manually. A new
   message invalidates the pending reply; approved email drafts stay in history.
5. Declare availability in Settings. An interview reply can offer actual free slots;
   the backend checks them again before saving the approved local email draft.
6. Open Analytics to inspect your own activity. Missing model measurements show
   “Not measured”; unavailable provider outcomes do not turn into zero-percent results.

The evaluation tools are calculators for observations collected during experiments.
They compare predictions with gold labels and report measured errors, retrieval
quality and outcomes. Implementing a calculator is different from having run the
experiment. The research tables still need the supplied data, real generation runs,
simulator outcomes and human/judge annotations. [EVALUATION.md](EVALUATION.md) gives
the input formats and commands without inventing results.

## What each folder means

| Folder | Purpose |
| --- | --- |
| `apps/web` | The interface the freelancer sees |
| `apps/api` | Login, API requests, durable approval lookup and streaming |
| `agent` | The workflow, structured handoffs, prompts and memory rules |
| `mcp_servers` | The controlled tools agents can use |
| `rag` | Turn portfolio files into searchable evidence and verify claims |
| `worker` | Run slow work outside web requests |
| `evals` | Measure whether designs actually work |
| `infra` | Start services locally and prepare deployment |
| `docs` | Explain the design, experiments and operating procedures |

## Terms you must be able to explain

**MCP:** a standard protocol for giving an agent named tools with input/output schemas. In GigBid, agents use MCP rather than reaching directly into databases or a marketplace API.

**RAG:** search your real portfolio and give the retrieved evidence to the writer. Retrieval does not guarantee truth; the verifier must still check what the writer claimed.

**LangGraph:** the workflow engine. Nodes perform work, edges define what follows, and state carries structured results between them.

**Checkpoint:** saved workflow state. The worker uses Postgres checkpoints so a pending review survives a restart. Unit tests may use memory; separate integration tests use real Postgres and recreate the runtime between run segments.

**Idempotency:** retrying an operation has the same external effect as doing it once. A checkpoint alone does not make marketplace writes idempotent.

**State, trace and memory:** state is what a current run needs; the trace records what happened; memory stores only deliberately promoted knowledge for later runs.

The current memory rule is deliberately explicit. If the same edit pattern appears in
three distinct drafts, Settings offers it for confirmation. Only a confirmed pattern
enters style memory; the complete edit diff stays in private review history. Outcome
memory has its own namespace and requires verified replies/wins on three distinct
marketplace jobs. A local draft is never a win or a reply. New runs load a snapshot of
active memory, and the writer must still ground experience claims in portfolio sources.
Removing a preference prevents future recall; it leaves earlier review history intact.

**Ablation:** remove one component from your best pipeline and measure what gets worse or stays the same.

## First things to read in the code

Read `agent/handoffs.py`, then `agent/graphs/bid_graph.py`, then its unit tests. Watch how approval pauses, rejection stops and edits return through verification. Read `agent/runtime.py` for checkpoint/resume handling and `agent/run_store.py` for the approval/local-save transaction. Next read `agent/marketplace_port.py` and one MCP server to see the tool boundary.

After each implemented feature, explain: what enters, what leaves, where it is stored, which tools it can access, what can fail, and which test proves the important behavior.
