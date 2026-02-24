"""
Deployer worker HTTP service.

Receives deployment tasks from Cloud Tasks via HTTP POST, claims in statestore,
runs Helm install, posts preview URL to GitHub PR.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Ensure src is on path for imports
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Preview Deployer Worker")

# Config from env
CHART_PATH = os.getenv("CHART_PATH", str(_repo_root / "helm-chart"))
VALUES_PATH = os.getenv("VALUES_PATH", str(_repo_root / "helm-chart" / "values-preview.yaml"))
PREVIEW_DOMAIN = os.getenv("PREVIEW_DOMAIN")  # e.g. preview-pr-123.{domain}
KUBECONFIG = os.getenv("KUBECONFIG")
REQUIRE_CLOUD_TASKS_HEADER = os.getenv("REQUIRE_CLOUD_TASKS_HEADER", "true").lower() == "true"


def _load_base_values() -> dict:
    """Load base Helm values from file."""
    import yaml
    with open(VALUES_PATH) as f:
        return yaml.safe_load(f)


@app.get("/")
async def root():
    return {"status": "healthy", "service": "deployer-worker"}


@app.get("/health")
async def health():
    return {"status": "healthy", "chart_path": CHART_PATH}


@app.post("/tasks/deploy")
async def handle_deploy_task(request: Request, x_cloudtasks_taskname: str = Header(None, alias="X-CloudTasks-TaskName")):
    """
    Handle deployment task from Cloud Tasks.
    Cloud Tasks sends the task payload as the request body.
    """
    if REQUIRE_CLOUD_TASKS_HEADER and not x_cloudtasks_taskname:
        logger.warning("Rejecting request: missing X-CloudTasks-TaskName header")
        raise HTTPException(status_code=403, detail="Request must come from Cloud Tasks")

    try:
        body = await request.body()
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid task payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    idempotency_key = payload.get("idempotency_key")
    repo = payload.get("repo")
    pr_number = payload.get("pr_number")
    commit_sha = payload.get("commit_sha")
    installation_id = payload.get("installation_id")
    comment_id = payload.get("comment_id")

    if not all([idempotency_key, repo, pr_number, commit_sha, installation_id]):
        logger.error(f"Missing required fields in payload: {payload.keys()}")
        raise HTTPException(status_code=400, detail="Missing required fields")

    repo_owner, _, repo_name = repo.partition("/")
    if not repo_name:
        repo_owner, repo_name = repo, ""

    # Import here to defer statestore/githubapp deps until first request
    from statestore import claim_deployment, update_deployment, release_claim, get_deployment
    from deployer.main import HelmDeployer
    from githubapp.github_client import GitHubClient

    github_client = GitHubClient()
    deployer = HelmDeployer(kubeconfig_path=KUBECONFIG)

    # 1. Claim deployment (idempotency)
    claimed = claim_deployment(
        idempotency_key=idempotency_key,
        repo=repo,
        pr_number=pr_number,
        commit_sha=commit_sha,
        installation_id=installation_id,
        comment_id=comment_id,
    )
    if not claimed:
        existing = get_deployment(idempotency_key)
        if existing and existing.get("status") == "deployed" and existing.get("preview_url"):
            # Already deployed - post URL if not yet posted
            preview_url = existing["preview_url"]
            comment = f"✅ Preview already exists: {preview_url}"
            await github_client.post_comment(repo_owner, repo_name, pr_number, comment, installation_id)
        return JSONResponse(status_code=200, content={"message": "Already claimed or deployed", "idempotency_key": idempotency_key})

    release_name = f"preview-pr-{pr_number}"
    namespace = release_name
    preview_url = f"http://preview-pr-{pr_number}.{PREVIEW_DOMAIN}"
    image_tag = f"pr-{pr_number}-{commit_sha[:8]}"
    base_values = _load_base_values()

    try:
        # 2. Helm install (idempotent: "release already exists" = success)
        success = deployer.install_preview(
            release_name=release_name,
            chart_path=CHART_PATH,
            namespace=namespace,
            values=base_values,
            image_tag=image_tag,
            preview_url=preview_url,
        )
        if not success:
            # Check if release already exists (idempotent retry)
            already_exists = deployer._last_stderr and "already exists" in deployer._last_stderr
            if already_exists:
                logger.info(f"Release {release_name} already exists, treating as success")
                success = True
            else:
                release_claim(idempotency_key)
                return JSONResponse(
                    status_code=500,
                    content={"message": "Helm install failed", "idempotency_key": idempotency_key}
                )

        # 3. Post comment with preview URL
        comment = f"✅ Preview ready: {preview_url}"
        await github_client.post_comment(repo_owner, repo_name, pr_number, comment, installation_id)

        # 4. Update statestore
        update_deployment(
            idempotency_key=idempotency_key,
            status="deployed",
            preview_url=preview_url,
            release_name=release_name,
            namespace=namespace,
        )

        logger.info(
            f"Deployed preview: {idempotency_key}",
            extra={"idempotency_key": idempotency_key, "pr_number": pr_number, "preview_url": preview_url},
        )
        return JSONResponse(status_code=200, content={"message": "Deployed", "preview_url": preview_url})

    except Exception as e:
        logger.exception(f"Deployment failed: {e}")
        release_claim(idempotency_key)
        # Return 5xx so Cloud Tasks retries
        return JSONResponse(
            status_code=503,
            content={"message": "Deployment failed", "error": str(e), "idempotency_key": idempotency_key}
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
