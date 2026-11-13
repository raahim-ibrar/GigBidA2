# Submission artifacts

- Public source: [GigBidA2](https://github.com/raahim-ibrar/GigBidA2).
- [Engineering report PDF](../output/pdf/GigBid_RnD_Report.pdf).
- [Public three-minute video](https://raahim-ibrar.github.io/GigBidA2/demo.html) ([MP4](../output/video/GigBid_Demo.mp4)), with [30-second GIF](images/demo.gif).
- [Public technical article](https://raahim-ibrar.github.io/GigBidA2/) and [article PDF](../output/pdf/GigBid_Technical_Writeup.pdf).
- [Installable Portfolio MCP](../mcp_servers/portfolio/README.md), with actual Inspector screenshots linked there.
- [Approved proposal / API crash and resume](https://smith.langchain.com/public/f91fd52f-2903-4c50-8160-f2415edd1ea7/r).
- [Real-model Critic loop](https://smith.langchain.com/public/039792a8-3f8a-4d96-863e-8a9b43e3ae88/r).
- [Skipped scam](https://smith.langchain.com/public/b55b89d4-881e-4c66-8516-cef09cba7cd2/r) and [rejected injection](https://smith.langchain.com/public/06918fe8-f9e4-4551-a7d8-f1435f522869/r).
- [Two résumé lines](RESUME.md), [verification history](VERIFICATION.md), [data card](DATA_CARD.md), and [AI disclosure](AI_USAGE.md).

The recording uses real application interactions and hosted inference with an explicitly
fictional portfolio and rule-client simulator. It is not evidence of a real freelance hire.
The approved run survived an actual API process kill/restart and has exactly one approval,
one application write receipt, and one simulator proposal for that job. Public trace
snapshots omit private content and retain the original application correlation ID.

## Limits that must remain visible

- The student chose to exclude E6 uptime work. The public app and HTTP MCP demo are off;
  this does not satisfy the PDF's requirement to remain live until grades are released.
  The installable stdio MCP package and public article remain available independently.
- Instructor policy-update details were not supplied, so implementation time for that
  specific change cannot be reported. Hidden-test outcomes are available only to grading.
- The original grading GigSim was not supplied. The independent simulator is labelled
  accurately; compatibility with an unseen grader is unverified.
- Upwork OAuth, discovery and job reads were verified. Preview writes are fixture-tested;
  no real proposals/messages were sent. Final submission/direct messages remain disabled.
- Reviewer credentials and all keys stay in ignored local files. Share reviewer details
  privately only when a demo session is running; do not publish the credentials.


The primary evaluation now uses LLM-driven simulator outcomes and a matched nine-job
V0/V3 retrieval/proposal cohort. See `evals/results/evaluation-fidelity-v1/README.md`.
This does not change the separate deployment, cost or live-mode limitations.

Budget-based pricing now uses comparable posted-budget medians/IQRs and a bounded
client-history adjustment when enough simulator-client records exist. See
[pricing method and limitations](PRICING.md). Historical budgets are not verified
earnings; unavailable live client price history remains explicit. Existing research
results predate this pricing change and have not been rewritten.
