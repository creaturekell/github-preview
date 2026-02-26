"""
Firestore-based statestore for deployment idempotency and claim logic.

Schema for deployments collection:
- idempotency_key (document ID): {owner}/{repo}#{pr_number}:{commit_sha}
- status: pending | claimed | deployed | failed
- repo, pr_number, commit_sha, installation_id, comment_id
- preview_url, release_name, namespace
- created_at, updated_at, claimed_by
"""

import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-init to allow optional dependency
_firestore_client = None


def _get_client():
    """Get Firestore client, initializing if needed."""
    global _firestore_client
    if _firestore_client is None:
        try:
            from google.cloud import firestore

            project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
            if project:
                _firestore_client = firestore.Client(project=project)
            else:
                _firestore_client = firestore.Client()
        except Exception as e:
            logger.error(f"Failed to initialize Firestore: {e}")
            raise
    return _firestore_client


COLLECTION = "deployments"
STATUS_PENDING = "pending"
STATUS_CLAIMED = "claimed"
STATUS_DEPLOYED = "deployed"
STATUS_FAILED = "failed"


def claim_deployment(
    idempotency_key: str,
    repo: str,
    pr_number: int,
    commit_sha: str,
    installation_id: int,
    comment_id: Optional[int] = None,
    claimed_by: Optional[str] = None,
) -> bool:
    """
    Claim a deployment for processing. Uses transaction to prevent duplicates.

    Returns True if claim succeeded, False if already claimed/deployed.
    """
    db = _get_client()
    doc_ref = db.collection(COLLECTION).document(idempotency_key)

    @db.transactional
    def _claim(transaction):
        doc = doc_ref.get(transaction=transaction)
        now = datetime.utcnow()

        if doc.exists:
            data = doc.to_dict()
            status = data.get("status")
            if status in (STATUS_CLAIMED, STATUS_DEPLOYED):
                logger.info(
                    f"Claim failed: {idempotency_key} already {status}",
                    extra={
                        "idempotency_key": idempotency_key,
                        "pr_number": pr_number,
                        "status": status,
                    },
                )
                return False

            # Update pending -> claimed
            transaction.update(
                doc_ref,
                {
                    "status": STATUS_CLAIMED,
                    "updated_at": now,
                    "claimed_by": claimed_by or os.getenv("HOSTNAME", "unknown"),
                },
            )
        else:
            # Insert new with status claimed
            transaction.set(
                doc_ref,
                {
                    "idempotency_key": idempotency_key,
                    "status": STATUS_CLAIMED,
                    "repo": repo,
                    "pr_number": pr_number,
                    "commit_sha": commit_sha,
                    "installation_id": installation_id,
                    "comment_id": comment_id,
                    "claimed_by": claimed_by or os.getenv("HOSTNAME", "unknown"),
                    "created_at": now,
                    "updated_at": now,
                },
            )

        logger.info(
            f"Claimed deployment: {idempotency_key}",
            extra={"idempotency_key": idempotency_key, "pr_number": pr_number},
        )
        return True

    transaction = db.transaction()
    return _claim(transaction)


def update_deployment(
    idempotency_key: str,
    status: str,
    preview_url: Optional[str] = None,
    release_name: Optional[str] = None,
    namespace: Optional[str] = None,
) -> None:
    """Update deployment status after success or failure."""
    db = _get_client()
    doc_ref = db.collection(COLLECTION).document(idempotency_key)

    data = {
        "status": status,
        "updated_at": datetime.utcnow(),
    }
    if preview_url is not None:
        data["preview_url"] = preview_url
    if release_name is not None:
        data["release_name"] = release_name
    if namespace is not None:
        data["namespace"] = namespace

    doc_ref.update(data)
    logger.info(
        f"Updated deployment: {idempotency_key} -> {status}",
        extra={"idempotency_key": idempotency_key, "status": status},
    )


def release_claim(idempotency_key: str) -> None:
    """Release a claim so the task can be retried (e.g., on worker failure)."""
    db = _get_client()
    doc_ref = db.collection(COLLECTION).document(idempotency_key)

    doc_ref.update(
        {
            "status": STATUS_PENDING,
            "updated_at": datetime.utcnow(),
            "claimed_by": None,
        }
    )
    logger.info(
        f"Released claim: {idempotency_key}",
        extra={"idempotency_key": idempotency_key},
    )


def get_deployment(idempotency_key: str) -> Optional[dict]:
    """Get deployment record by idempotency key."""
    db = _get_client()
    doc_ref = db.collection(COLLECTION).document(idempotency_key)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data["idempotency_key"] = doc.id
        return data
    return None
