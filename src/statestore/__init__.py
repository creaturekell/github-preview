"""Statestore for deployment tracking and idempotent claims."""

from .firestore_client import (
    claim_deployment,
    update_deployment,
    release_claim,
    get_deployment,
)

__all__ = [
    "claim_deployment",
    "update_deployment",
    "release_claim",
    "get_deployment",
]
