# Example starter kit review

Reviewed on 8 November 2026: `GigBid_Student_Starter_Kit_v0.1.zip`.
Archive SHA-256: `ade5df7ba886d65dcdccd12ceda5a019891b7a73a5e658fe0651546755f514fb`.
The archive was inspected without replacing or copying its scaffold into our project.

The archive has 54 entries: configuration/documentation, code placeholders, two
synthetic jobs, one synthetic freelancer, one portfolio example, one client-history
record, and an explicitly illustrative policy file. These are development examples.

It contains no `gigsim/` implementation, no `data/personas/` corpora, and no
`evals/datasets/` evaluation set. `mcp_servers/marketplace/server.py` is a TODO to
wrap the supplied GigSim API. `agent/marketplace_port.py` defines an interface and
leaves the GigSim/live adapters to the student.

The kit README explicitly says its sample data is not a replacement for the
instructor-provided GigSim data or evaluation sets. Its policy example likewise
defers to the instructor-provided grading policy pack.

The teacher's accompanying message says to use the kit as an example and create an
independent implementation. Our existing project was built independently. This
message does not explicitly reassign construction of the GigSim simulator to the
student. The actual simulator/API contract and grading assets still need a separate
source or instructor clarification. No simulator endpoints, grading labels or
research outcomes should be inferred from these tiny samples.
