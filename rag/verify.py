from agent.handoffs import EvidenceItem, ProposalDraft


async def verify_claims(draft: ProposalDraft, evidence: list[EvidenceItem]) -> ProposalDraft:
    raise NotImplementedError(
        "Split claims, verify entailment, and remove or rewrite unsupported text"
    )
