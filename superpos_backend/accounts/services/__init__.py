"""accounts.services — domain service layer for the accounts app.

Modules here implement cross-cutting workflows (account-movement posting,
balance lookups, …) that don't belong on model classes themselves. Views
import these helpers; tests import them directly.

Phase 1.5 Slice D ships: `account_movements`.
"""
