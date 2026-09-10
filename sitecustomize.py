from __future__ import annotations

# Python imports sitecustomize after the standard site initialization.  The
# application and its browser-test harnesses start from the repository root,
# so this is the earliest common point at which the authoritative semantic
# projector can be normalized before service_graph imports its build function.
from app.deep_audit_runtime_patch import install

install()
