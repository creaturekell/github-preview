"""Authentication and security utilities."""
import hmac
import hashlib
import logging
from typing import Optional

from .config import Config

logger = logging.getLogger(__name__)


def verify_webhook_signature(
    payload_body: bytes, 
    secret_token: str, 
    signature: Optional[str]
) -> bool:
    """Verify that the payload was sent from GitHub by validating SHA256.
    
    Args:
        payload_body: Original request body to verify
        secret_token: GitHub app webhook token (GITHUB_WEBHOOK_SECRET)
        signature: Header received from GitHub (X-Hub-Signature-256)
        
    Returns:
        True if signature is valid, False otherwise
    """
    if not signature:
        return False
    
    if not signature.startswith("sha256="):
        return False
    
    hash_object = hmac.new(
        secret_token.encode('utf-8'), 
        msg=payload_body, 
        digestmod=hashlib.sha256
    )
    expected_signature = "sha256=" + hash_object.hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)
