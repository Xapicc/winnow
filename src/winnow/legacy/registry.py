"""Strategy registry and prescription definitions."""

from __future__ import annotations

from .types import StrategyInfo

# Global strategy registry — populated by @strategy decorator in strategies/
STRATEGIES: dict[str, StrategyInfo] = {}

# Prescriptions: named combos of strategies with curated ordering
PRESCRIPTIONS: dict[str, list[str]] = {
    "gentle": [
        "compact-summary-collapse",
        "attribution-snapshot-strip",
        "progress-collapse",
        "file-history-dedup",
        "metadata-strip",
    ],
    "standard": [
        "compact-summary-collapse",
        "attribution-snapshot-strip",
        "progress-collapse",
        "file-history-dedup",
        "metadata-strip",
        # Ahead of every strategy that rewrites tool_result content
        # (tool-output-trim, tool-result-age, stale-reads): identical-reread
        # compares result bytes, and a rewrite upstream of it destroys the
        # byte-identity it tests for.
        "identical-reread",
        "thinking-blocks",
        "tool-output-trim",
        "tool-result-age",
        "stale-reads",
        "system-reminder-dedup",
        "tool-use-result-strip",
    ],
    "aggressive": [
        "compact-summary-collapse",
        "attribution-snapshot-strip",
        "progress-collapse",
        "file-history-dedup",
        "metadata-strip",
        # Ahead of every strategy that rewrites tool_result content
        # (tool-output-trim, tool-result-age, stale-reads): identical-reread
        # compares result bytes, and a rewrite upstream of it destroys the
        # byte-identity it tests for.
        "identical-reread",
        # Lossy sibling of identical-reread, aggressive-tier because what it
        # removes is a file version held neither in the conversation nor on
        # disk. Immediately after it, for the same ordering reason and so a
        # byte-identical pair is settled by the lossless rule first.
        "changed-reread",
        "thinking-blocks",
        "tool-output-trim",
        "tool-result-age",
        "stale-reads",
        "system-reminder-dedup",
        "tool-use-result-strip",
        "image-strip",
        "http-spam",
        "error-retry-collapse",
        "background-poll-collapse",
        "document-dedup",
        "mega-block-trim",
        "envelope-strip",
    ],
}


def strategy(name: str, description: str, tier: str, expected_savings: str):
    """Decorator to register a strategy function."""
    def decorator(func):
        STRATEGIES[name] = StrategyInfo(
            name=name,
            description=description,
            tier=tier,
            expected_savings=expected_savings,
            func=func,
        )
        return func
    return decorator
