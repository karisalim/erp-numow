"""pos.services — domain service layer.

Modules here implement cross-cutting workflows (idempotency, posting,
movement-ledger writes, …) that are not appropriate to live on the model
classes themselves. Views import these helpers; tests import them directly.

Phase 1 slice ships: `idempotency`.
"""
