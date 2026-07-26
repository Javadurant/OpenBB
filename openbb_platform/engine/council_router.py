# engine/council_router.py
# QuantEdge — Council Router (5-Advisor Tool Dispatch)
# Six-Role Panel: DEAN · PAEZ · SELIVANOV · KARPATHY · NILSSON · GURPREET SINGH
#
# ARCHITECTURE (Council Verdict — Session 2026-05-14, Step 4):
#   Routing layer that maps each of the 5 Council advisors to the tools
#   they should use. Prevents groupthink by giving different advisors
#   access to different data sources / actions.
#
#   The router is *advisory*: it returns the list of tool names each
#   advisor SHOULD invoke for a given decision type. The actual MCP
#   tool invocation happens through engine/mcp_server.py.
#
# ADVISOR-TO-TOOL MAPPING (from Council blind-spot finding):
#   Contrarian        — risk-checking tools (account, positions)
#   First Principles  — minimal probe (health, account)
#   Expansionist      — execution tools (place orders, scan opportunities)
#   Outsider          — read-only diagnostic (health only)
#   Executor          — full toolkit (everything — they ship)
#
# DECISION TYPES:
#   risk_check        — Should we be holding positions right now?
#   opportunity_scan  — Is there a trade worth taking?
#   execution_review  — Are our recent orders behaving as expected?
#   strategy_pivot    — Is our overall approach still valid?
#
# WHY THIS LAYER EXISTS:
#   Without routing, all 5 advisors look at the same data and converge
#   on similar conclusions. Routing forces data diversity at the source,
#   which produces genuine disagreement and better synthesis.
#
# <- NEW [council_router]: Per-advisor tool dispatch with audit logging

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple

logger = logging.getLogger("QuantEdge.CouncilRouter")


# -- Advisor identity --
class Advisor(Enum):
    """The five Council advisors. Each has a distinct thinking style."""
    CONTRARIAN        = "CONTRARIAN"
    FIRST_PRINCIPLES  = "FIRST_PRINCIPLES"
    EXPANSIONIST      = "EXPANSIONIST"
    OUTSIDER          = "OUTSIDER"
    EXECUTOR          = "EXECUTOR"


# -- Decision types --
class DecisionType(Enum):
    """High-level decision categories the Council can be invoked for."""
    RISK_CHECK        = "RISK_CHECK"
    OPPORTUNITY_SCAN  = "OPPORTUNITY_SCAN"
    EXECUTION_REVIEW  = "EXECUTION_REVIEW"
    STRATEGY_PIVOT    = "STRATEGY_PIVOT"


# -- MCP tool names (must match engine/mcp_server.py exactly) --
TOOL_HEALTH:        str = "qe_health"
TOOL_GET_ACCOUNT:   str = "qe_get_account"
TOOL_GET_POSITIONS: str = "qe_get_positions"
TOOL_PLACE_ORDER:   str = "qe_place_order"

# Complete set of currently exposed tools.
# When new tools are added in engine/mcp_server.py, add them here as well.
ALL_TOOLS: Tuple[str, ...] = (
    TOOL_HEALTH,
    TOOL_GET_ACCOUNT,
    TOOL_GET_POSITIONS,
    TOOL_PLACE_ORDER,
)


# -- Advisor profile dataclass --
@dataclass(frozen=True)
class AdvisorProfile:
    """
    Per-advisor configuration:
      allowed_tools:  the set of MCP tools this advisor is authorised to invoke
      default_tools:  the tools this advisor should always call when convened
      can_execute:    whether this advisor is permitted to place orders
    """
    advisor:        Advisor
    allowed_tools:  Tuple[str, ...]
    default_tools:  Tuple[str, ...]
    can_execute:    bool
    rationale:      str


# -- Advisor → tool profiles --
# Mapping derived from Council session 2026-05-14 (blind-spot finding #2):
# "Data diversity prevents groupthink. Different advisors should access
#  different sources to prevent convergence on the same conclusion."
ADVISOR_PROFILES: Dict[Advisor, AdvisorProfile] = {
    Advisor.CONTRARIAN: AdvisorProfile(
        advisor=Advisor.CONTRARIAN,
        allowed_tools=(TOOL_HEALTH, TOOL_GET_ACCOUNT, TOOL_GET_POSITIONS),
        default_tools=(TOOL_GET_ACCOUNT, TOOL_GET_POSITIONS),
        can_execute=False,
        rationale=(
            "Contrarian's role is to find what's wrong. Reads account exposure and "
            "open positions to identify hidden risk. Never places orders — risk "
            "assessment must be independent from execution authority."
        ),
    ),
    Advisor.FIRST_PRINCIPLES: AdvisorProfile(
        advisor=Advisor.FIRST_PRINCIPLES,
        allowed_tools=(TOOL_HEALTH, TOOL_GET_ACCOUNT),
        default_tools=(TOOL_HEALTH,),
        can_execute=False,
        rationale=(
            "First Principles asks 'is the system in a state where decisions are "
            "meaningful?' Health check tells whether the broker is connected and "
            "what mode we're in. Minimal probing — strips away assumptions."
        ),
    ),
    Advisor.EXPANSIONIST: AdvisorProfile(
        advisor=Advisor.EXPANSIONIST,
        allowed_tools=(TOOL_HEALTH, TOOL_GET_ACCOUNT, TOOL_PLACE_ORDER),
        default_tools=(TOOL_GET_ACCOUNT,),
        can_execute=True,
        rationale=(
            "Expansionist looks for upside. Sees account capacity, then sizes "
            "opportunities. Can place orders when the case is strong — but always "
            "in SUPERVISED mode (let_god_trade page enforces user confirmation)."
        ),
    ),
    Advisor.OUTSIDER: AdvisorProfile(
        advisor=Advisor.OUTSIDER,
        allowed_tools=(TOOL_HEALTH,),
        default_tools=(TOOL_HEALTH,),
        can_execute=False,
        rationale=(
            "Outsider has no context. Only sees system health. Forces the question "
            "'does this even work?' before deeper analysis. Catches curse of "
            "knowledge — when experts see complexity that isn't there."
        ),
    ),
    Advisor.EXECUTOR: AdvisorProfile(
        advisor=Advisor.EXECUTOR,
        allowed_tools=ALL_TOOLS,
        default_tools=(TOOL_HEALTH, TOOL_GET_ACCOUNT, TOOL_GET_POSITIONS),
        can_execute=True,
        rationale=(
            "Executor cares about shipping. Full toolkit access. Reads complete "
            "system state to identify the fastest path to action. Authorised to "
            "execute orders in SUPERVISED mode."
        ),
    ),
}


# -- Decision type → advisor priority order --
# When a decision is convened, advisors run in this order. Order matters
# because earlier responses can influence framing (though anonymised peer
# review handles this in the Council session protocol).
DECISION_ADVISOR_ORDER: Dict[DecisionType, Tuple[Advisor, ...]] = {
    DecisionType.RISK_CHECK: (
        # Risk = Contrarian first, then validators
        Advisor.CONTRARIAN,
        Advisor.FIRST_PRINCIPLES,
        Advisor.OUTSIDER,
        Advisor.EXECUTOR,
        Advisor.EXPANSIONIST,
    ),
    DecisionType.OPPORTUNITY_SCAN: (
        # Opportunity = Expansionist first, then risk gates
        Advisor.EXPANSIONIST,
        Advisor.EXECUTOR,
        Advisor.CONTRARIAN,
        Advisor.OUTSIDER,
        Advisor.FIRST_PRINCIPLES,
    ),
    DecisionType.EXECUTION_REVIEW: (
        # Review past trades = Executor + Contrarian
        Advisor.EXECUTOR,
        Advisor.CONTRARIAN,
        Advisor.FIRST_PRINCIPLES,
        Advisor.EXPANSIONIST,
        Advisor.OUTSIDER,
    ),
    DecisionType.STRATEGY_PIVOT: (
        # Pivot = First Principles first (reframe), Outsider second (fresh eyes)
        Advisor.FIRST_PRINCIPLES,
        Advisor.OUTSIDER,
        Advisor.CONTRARIAN,
        Advisor.EXPANSIONIST,
        Advisor.EXECUTOR,
    ),
}


# -- Public routing API --
@dataclass(frozen=True)
class RouteAssignment:
    """
    A single advisor's tool assignment for a Council session.
    Used to dispatch MCP tool calls per advisor.
    """
    advisor:       Advisor
    tools_to_call: Tuple[str, ...]
    can_execute:   bool
    rationale:     str


def route_for_decision(
    decision: DecisionType,
    requested_tools: Tuple[str, ...] = (),
) -> List[RouteAssignment]:
    """
    Returns the per-advisor tool assignments for a given decision type.

    Args:
        decision:         The high-level decision category.
        requested_tools:  Optional override — specific tools the caller wants
                          invoked. Each advisor's tool list is the intersection
                          of (their allowed_tools) and (requested_tools).
                          When empty, advisors use their default_tools.

    Returns:
        Ordered list of RouteAssignment — one per advisor, in the order
        appropriate for the given decision type.

    Raises:
        ValueError: When decision is not a known DecisionType.
    """
    if decision not in DECISION_ADVISOR_ORDER:
        raise ValueError(
            f"Unknown decision type '{decision}'. "
            f"Valid: {[d.value for d in DecisionType]}"
        )

    advisor_order = DECISION_ADVISOR_ORDER[decision]
    assignments: List[RouteAssignment] = []

    for advisor in advisor_order:
        profile = ADVISOR_PROFILES[advisor]

        # If caller specified tools, intersect with allowed.
        # Otherwise use the advisor's default tool set.
        if requested_tools:
            tools = tuple(
                t for t in requested_tools if t in profile.allowed_tools
            )
        else:
            tools = profile.default_tools

        assignments.append(
            RouteAssignment(
                advisor=advisor,
                tools_to_call=tools,
                can_execute=profile.can_execute,
                rationale=profile.rationale,
            )
        )

    logger.info(
        "Routed decision '%s' to %d advisors with %d total tool calls",
        decision.value,
        len(assignments),
        sum(len(a.tools_to_call) for a in assignments),
    )

    return assignments


def get_advisor_profile(advisor: Advisor) -> AdvisorProfile:
    """Returns the profile for a single advisor. Raises KeyError if unknown."""
    return ADVISOR_PROFILES[advisor]


def list_decision_types() -> List[str]:
    """Returns the names of all decision types this router supports."""
    return [d.value for d in DecisionType]


def list_advisors() -> List[str]:
    """Returns the names of all advisors in the Council."""
    return [a.value for a in Advisor]
