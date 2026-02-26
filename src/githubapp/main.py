"""Main FastAPI application for GitHub App webhook server."""
import json
import logging

from fastapi import FastAPI, Request, HTTPException, Header, status
from fastapi.responses import JSONResponse

from .config import Config
from .auth import verify_webhook_signature
from .webhook_parser import WebhookParser
from .github_client import GitHubClient
from .queue_client import enqueue_deployment_task

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Validate configuration
Config.validate()

# Initialize FastAPI app
app = FastAPI(title="GitHub App Preview URL Service")

# Initialize GitHub client
github_client = GitHubClient()


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "github_app_id": Config.GITHUB_APP_ID is not None,
        "webhook_secret_configured": Config.GITHUB_WEBHOOK_SECRET is not None,
        "private_key_configured": Config.GITHUB_APP_PRIVATE_KEY is not None
    }


@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
    x_github_hook_installation_target_id: str = Header(None, alias="X-GitHub-Hook-Installation-Target-ID")
):
    """GitHub webhook endpoint that processes issue comment events."""
    body_bytes = await request.body()
    
    # Verify signature
    if not verify_webhook_signature(body_bytes, Config.GITHUB_WEBHOOK_SECRET, x_hub_signature_256):
        logger.warning("Webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse JSON payload
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    
    logger.info(f"Received GitHub event: {x_github_event}")
    
    # Only process issue_comment events
    if x_github_event != "issue_comment":
        logger.debug(f"Ignoring event type: {x_github_event}")
        return JSONResponse(
            status_code=200,
            content={"message": f"Event type {x_github_event} ignored"}
        )
    
    # Parse webhook payload
    event_data = WebhookParser.parse_issue_comment_event(payload)
    if not event_data:
        return JSONResponse(
            status_code=200,
            content={"message": "Event ignored or invalid"}
        )
    
    pr_number = event_data["pr_number"]
    repo_owner = event_data["repo_owner"]
    repo_name = event_data["repo_name"]
    repository_id = event_data["repository_id"]
    
    # Get installation ID
    installation_id = WebhookParser.extract_installation_id(
        payload, 
        x_github_hook_installation_target_id, 
        repository_id
    )
    
    # Fallback: Look up installation ID via API
    if not installation_id:
        installation_id = await github_client.find_installation_id(repo_owner)
    
    if not installation_id:
        logger.error("Could not determine installation ID")
        return JSONResponse(
            status_code=200,
            content={
                "message": "Could not determine installation ID. Please ensure the GitHub App is installed.",
                "help": "Go to your GitHub App settings and install it on your account or organization."
            }
        )
    
    logger.info(f"Processing /preview command for PR #{pr_number} in {repo_owner}/{repo_name}")

    # Get PR details to extract commit SHA
    try:
        access_token = await github_client.get_installation_access_token(installation_id)
        if not access_token:
            await github_client.post_comment(
                repo_owner, repo_name, pr_number,
                "❌ Failed to authenticate with GitHub.",
                installation_id
            )
            return JSONResponse(
                status_code=200,
                content={"message": "Failed to get installation token"}
            )

        pr_data = await github_client.get_pr_details(repo_owner, repo_name, pr_number, access_token)
        if not pr_data:
            await github_client.post_comment(
                repo_owner, repo_name, pr_number,
                "❌ Failed to retrieve PR information.",
                installation_id
            )
            return JSONResponse(
                status_code=200,
                content={"message": "Failed to get PR details"}
            )

        commit_sha = pr_data.get("head", {}).get("sha")
        if not commit_sha:
            await github_client.post_comment(
                repo_owner, repo_name, pr_number,
                "❌ Could not determine commit SHA for deployment.",
                installation_id
            )
            return JSONResponse(
                status_code=200,
                content={"message": "Could not get commit SHA"}
            )

        logger.info(f"Extracted commit SHA: {commit_sha}")

    except Exception as e:
        logger.error(f"Error processing PR: {e}")
        import traceback
        logger.debug(f"Traceback: {traceback.format_exc()}")
        await github_client.post_comment(
            repo_owner, repo_name, pr_number,
            "❌ An error occurred while processing the deployment request.",
            installation_id
        )
        return JSONResponse(
            status_code=200,
            content={"message": "Error processing PR", "error": str(e)}
        )

    # Post initial response comment (fast)
    await github_client.post_comment(
        repo_owner, repo_name, pr_number,
        "🚀 Deployment requested! Setting up preview environment...",
        installation_id
    )

    # Enqueue deployment task (non-blocking; Deployer worker will process)
    repo = f"{repo_owner}/{repo_name}"
    idempotency_key = f"{repo}#{pr_number}:{commit_sha}"
    task_payload = {
        "idempotency_key": idempotency_key,
        "repo": repo,
        "pr_number": pr_number,
        "commit_sha": commit_sha,
        "installation_id": installation_id,
        "comment_id": event_data.get("comment_id"),
    }
    if not enqueue_deployment_task(task_payload):
        await github_client.post_comment(
            repo_owner, repo_name, pr_number,
            "❌ Failed to queue deployment. Please check server configuration (CLOUD_TASKS_PROJECT, DEPLOYER_URL).",
            installation_id
        )

    return JSONResponse(
        status_code=200,
        content={
            "message": "Deployment request processed",
            "pr_number": pr_number,
            "repo": repo
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=Config.PORT,
        log_level="info",
        reload=Config.DEBUG
    )
