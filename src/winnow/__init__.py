"""winnow — see docs/SPEC.md for what this package is going to be.

`winnow.legacy` is the inherited implementation, now winnow's own code to
change (docs/DECISIONS.md §0, NOTICE). It is still kept behind its own
subpackage rather than merged in, because `docs/DECISIONS.md` §0.2 holds
that no new winnow code may import from the inherited guard, writer or
trigger, and a word in every import path makes that hard to breach by
accident. Under an unattended harness the one sanctioned path to it is
`winnow.orchestrator_safe`.
"""

__all__ = ["orchestrator_safe"]
