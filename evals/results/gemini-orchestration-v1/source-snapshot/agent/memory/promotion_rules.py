"""Only explicit promotion candidates may enter long-term memory."""


def may_promote_style(*, user_confirmed: bool, matching_edits: int) -> bool:
    return user_confirmed and matching_edits >= 3


def may_promote_outcome(*, source: str, outcome: str, observations: int) -> bool:
    return source == "marketplace_event" and outcome in {"won", "replied"} and observations >= 3
