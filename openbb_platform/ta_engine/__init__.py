"""
ta_engine -- clean-room technical-analysis detection engines.

Currently exposes the rule-gated Elliott Wave engine. Pure stdlib, no I/O,
operates on ZigZag pivots so it is trivially unit-testable in isolation.
"""
from .elliott import (  # noqa: F401
    Pivot,
    ImpulseResult,
    ElliottAnalysis,
    classify_impulse,
    classify,
    analyze,
)
