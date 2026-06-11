"""
lib — source-of-truth (DATA INAMOVIBLE v1) interface for the Witt × Organogenesis repo.

Public surface (GWT v1.1 §6.2):
  resolve_id.resolve / require / lookup_prior  — read-only identifier resolver
  verify_output.verify_identifiers             — deterministic anti-fabrication gate (§6.4)
  build_verified_store.build                   — the SINGLE WRITER of the store (human-run)

NO-SPEND: every module here is pure stdlib and makes ZERO network calls.
"""
