"""GigSim port backed by our explicitly student-built simulator schema.

No instructor implementation was supplied. The provider ID remains student_sim
so measurements cannot be confused with an independently supplied benchmark.
"""

from mcp_servers.marketplace.adapters.student_sim import StudentSimAdapter


class GigSimAdapter(StudentSimAdapter):
    """Our working GigSim-compatible application port, with host-bound identity."""
