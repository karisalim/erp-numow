# Source of Truth

## Purpose

This document defines the authoritative sources for product decisions, workflow rules, UX guidance, and implementation baseline decisions for the SuperPOS v3.6 direction.

This file is planning-only. It does not change backend, frontend, database, or API behavior.

---

## 1. Authoritative Business Source of Truth

These files are the primary source of truth for business rules and product scope.

- [enhacment_new_version/PRD_v3_6.md](enhacment_new_version/PRD_v3_6.md) — business source of truth
- [enhacment_new_version/FLOW_v3_6.md](enhacment_new_version/FLOW_v3_6.md) — workflow/source of truth
- [enhacment_new_version/DOMAIN_v3_6.md](enhacment_new_version/DOMAIN_v3_6.md) — domain rules/source of truth
- [enhacment_new_version/DESIGN_v3_6.md](enhacment_new_version/DESIGN_v3_6.md) — UX/design rules/source of truth

### Business logic guidance

Use the above v3.6 docs to define:

- business rules
- workflow steps
- domain entities and relationships
- status lifecycle rules
- approval rules
- posting and settlement rules
- ERP-lite scope boundaries

---

## 2. UX and Prototype References

### UX prototype reference only

- [enhacment_new_version/SuperPOS.dc.html](enhacment_new_version/SuperPOS.dc.html) — UX prototype reference only

Use this file to guide:

- screen structure
- component flow
- navigation patterns
- interaction behavior
- visual hierarchy

Do not use it as the source of business logic, domain rules, or persistence rules.

### Legacy visual reference only

- [SuperPOS_old_prototybe.html](SuperPOS_old_prototybe.html) — legacy visual reference only

Use only for historical inspiration if needed. It is not a current product authority.

---

## 3. Legacy Documentation

These are legacy-only references and should not drive new implementation decisions.

- [PRD_old_v.md](PRD_old_v.md)
- [FLOW_old_v.md](FLOW_old_v.md)
- [DOMAN_old_v.md](DOMAN_old_v.md)
- [DESIGN_old_v.md](DESIGN_old_v.md)

These files may be used for:

- historical context
- comparison with older scope
- understanding prior assumptions

They must not override the v3.6 documents.

---

## 4. Current Backend and Frontend Code

The current implementation in the backend and frontend is an implementation baseline, not the product source of truth.

### Current backend baseline

- [superpos_backend](superpos_backend)
- [superpos_backend/accounts](superpos_backend/accounts)
- [superpos_backend/pos](superpos_backend/pos)

### Current frontend baseline

- [superpos](superpos)
- [superpos/src](superpos/src)

### How to treat current code

Use the current backend/frontend code to understand:

- existing architecture
- current data shape
- current route structure
- current screen structure
- what is already implemented

Do not treat current code as authoritative when it conflicts with the v3.6 documents.

---

## 5. Decision Hierarchy

When a conflict exists, resolve it in this order:

1. [enhacment_new_version/PRD_v3_6.md](enhacment_new_version/PRD_v3_6.md)
2. [enhacment_new_version/FLOW_v3_6.md](enhacment_new_version/FLOW_v3_6.md)
3. [enhacment_new_version/DOMAIN_v3_6.md](enhacment_new_version/DOMAIN_v3_6.md)
4. [enhacment_new_version/DESIGN_v3_6.md](enhacment_new_version/DESIGN_v3_6.md)
5. current backend/frontend implementation
6. legacy docs and legacy prototypes

### Conflict resolution rules

- Business rules always come from the v3.6 PRD, workflow, and domain docs.
- UX behavior comes from the v3.6 design doc and the Claude prototype.
- The current backend/frontend implementation is a reference for feasibility and migration planning, not a source of truth.
- Legacy docs and old prototypes are historical only.
- If a requirement is ambiguous, document the ambiguity and choose the least risky interpretation that preserves the v3.6 intent.

---

## 6. Working Rules for the Team

- Treat the v3.6 product docs as the main contract for scope and behavior.
- Treat the design doc and Claude prototype as the main contract for the intended UX.
- Treat the current implementation as a starting point for reuse, not as a replacement for the new product definition.
- Keep planning artifacts aligned with the documented business rules.
- When implementing, ensure the feature behavior matches the v3.6 contract even if the current code differs.

---

## 7. Scope Classification Summary

| Artifact | Role |
|---|---|
| [enhacment_new_version/PRD_v3_6.md](enhacment_new_version/PRD_v3_6.md) | Business source of truth |
| [enhacment_new_version/FLOW_v3_6.md](enhacment_new_version/FLOW_v3_6.md) | Workflow/source of truth |
| [enhacment_new_version/DOMAIN_v3_6.md](enhacment_new_version/DOMAIN_v3_6.md) | Domain rules/source of truth |
| [enhacment_new_version/DESIGN_v3_6.md](enhacment_new_version/DESIGN_v3_6.md) | UX/design rules/source of truth |
| [enhacment_new_version/SuperPOS.dc.html](enhacment_new_version/SuperPOS.dc.html) | UX prototype reference only |
| [SuperPOS_old_prototybe.html](SuperPOS_old_prototybe.html) | Legacy visual reference only |
| [PRD_old_v.md](PRD_old_v.md), [FLOW_old_v.md](FLOW_old_v.md), [DOMAN_old_v.md](DOMAN_old_v.md), [DESIGN_old_v.md](DESIGN_old_v.md) | Legacy only |
| [superpos_backend](superpos_backend) and [superpos](superpos) | Implementation baseline only |
