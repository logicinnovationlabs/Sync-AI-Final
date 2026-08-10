"""API v1 routes.

Block A: auth, oauth, me, admin, connectors, scoped_probes
Block C: identity, acl

Routers are imported by app.main (and tests) as submodules — avoid eager
imports here so `from app.api.v1 import identity` stays lightweight.
"""

__all__ = [
    "auth",
    "oauth",
    "me",
    "admin",
    "connectors",
    "scoped_probes",
    "identity",
    "acl",
]
