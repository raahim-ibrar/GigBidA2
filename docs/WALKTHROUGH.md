# Understanding GigBid

The code will be written with AI assistance. Your job is to understand the decisions, follow a run through the system, identify where failures occur and explain the evidence. The assignment's viva also asks for small live changes, so understanding includes being able to locate and alter configuration or a simple rule.

## One job, from start to finish

1. Scout asks the marketplace for jobs. It checks duplicates so a job is not processed twice.
2. Three branches inspect the same raw job concurrently. Analyst extracts requirements; Risk checks scams and client history; Matcher searches the portfolio for evidence. Matcher cannot wait for Analyst output while they are parallel; it derives its own search queries from the post.
3. Decision uses those results to choose skip, watch or bid. Pricing estimates a bid and checks the configured budget.
4. Writer creates a proposal from actual portfolio evidence. Verifier checks its claims. Critic asks for improvements, with a maximum of two rewrites.
5. Compliance checks platform rules. A failed check blocks progress.
6. The marketplace produces a dry-run preview showing the exact outgoing action and Connects cost.
7. LangGraph pauses at an interrupt. The user reviews, approves, edits or rejects.
8. A later executor will carry out an approved action using an idempotency key. A repeated delivery must return the prior result, not spend twice.

The graph routing and interrupt mechanism exist. Portfolio uploads, source revisions and evidence retrieval now work, including the real Portfolio MCP server. Proposal agents and external action execution still need implementation. Graph unit tests currently use explicitly labelled fixture nodes to check routing.

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

**Checkpoint:** saved workflow state. Postgres checkpoints will let an approval survive a process restart. The skeleton's unit tests use memory checkpoints, which do not survive restarts.

**Idempotency:** retrying an operation has the same external effect as doing it once. A checkpoint alone does not make marketplace writes idempotent.

**State, trace and memory:** state is what a current run needs; the trace records what happened; memory stores only deliberately promoted knowledge for later runs.

**Ablation:** remove one component from your best pipeline and measure what gets worse or stays the same.

## First things to read in the code

Read `agent/handoffs.py`, then `agent/graphs/bid_graph.py`, then its unit tests. Watch how approval pauses and how reject/edit cannot reach the executor. Next read `agent/marketplace_port.py` and one MCP server to see the tool boundary.

After each implemented feature, explain: what enters, what leaves, where it is stored, which tools it can access, what can fail, and which test proves the important behavior.
