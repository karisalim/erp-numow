"""Domain primitives reused across pos serializers/models/services.

This subpackage holds non-persistent enums, constants, and pure helpers that
encode the v3.6 business contract (status fields, transition rules, etc.)
without owning their own database tables. Models that *persist* live in
`pos.models`; movement/posting logic lives in `pos.services`.
"""
