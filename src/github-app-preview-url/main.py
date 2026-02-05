import os
import logging
from datetime import datetime
from dotenv import load_dotenv

from fastapi import FastAPI, Request, HTTPException, Header
from pydantic import BaseModel
import jwt


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="GitHub App Preview URL Service")

# Environmental variables
load_dotenv() # loads .env into environment variables
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_APP_PRIVATE_KEY = os.getenv("GITHUB_APP_PRIVATE_KEY")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

# Validate required environment variables
if not all([GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY, GITHUB_WEBHOOK_SECRET]):
    logger.warning("Missing required environment variables. Some features may not work.")

@app.get("/")
async def root():
    return {"status": "healthy"}

@app.get("/health")
async def health():
    return {"status": "healthy"}


def verify_signature(payload_body, secret_token, signature_header):
    """Verify that the payload was sent from GitHub by validating SHA256.
    
    Reference docs: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries

    Raise and return 403 if not authorized.

    Args:
        payload_body: original request body to verify (request.body())
        secret_token: GitHub app webhook token (WEBHOOK_SECRET)
        signature_header: header received from GitHub (x-hub-signature-256)
    """
    

    # Will copy implementation from reference docs above later
    pass

def generate_jwt_token() -> str:
    """
    Generate a JWT token for GitHub App authentication.
    
    Returns:
        JWT token string
    """
    if not GITHUB_APP_ID or not GITHUB_APP_PRIVATE_KEY:
        raise ValueError("GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY must be set")

    now = int(datetime.now().timestamp())
    payload = {
        "iat": now - 60,  # Issued at time (1 minute ago to account for clock skew)
        "exp": now + (10 * 60),  # Expires in 10 minutes
        "iss": GITHUB_APP_ID  # Issuer is the App ID
    }

    token = jwt.encode(payload, GITHUB_APP_PRIVATE_KEY, algorithm="RS256")
    return token


@app.post("/webhook")
async def github_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    body_bytes = await request.body()
    if not verify_webhook_signature(body_bytes, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    return {"message": "webhook received"}

