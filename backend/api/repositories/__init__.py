"""Typed repository layer over the BigQuery trip/session/eval tables.

One module per table; pydantic models and status enums live in `models`.
All functions follow the helper convention: return (success, result, error)
tuples and never raise on BigQuery failures — invalid enum values raise
pydantic ValidationError at the boundary instead of reaching SQL.
"""
