"""winnow — see docs/SPEC.md for what this package is going to be.

Only the orchestrator-safe mode exists so far. `src/cozempic/` is vendored prior
art, read-only and not winnow's code (docs/DECISIONS.md §0); the one sanctioned
path to it under an unattended harness is `winnow.orchestrator_safe`.
"""

__all__ = ["orchestrator_safe"]
