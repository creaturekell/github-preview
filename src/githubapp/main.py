import os
import logging
import hmac
import hashlib
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional
import json
import aiohttp

from fastapi import FastAPI, Request, HTTPException, Header, status
from fastapi.responses import JSONResponse
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


def verify_signature(payload_body, secret_token, signature):
    """Verify that the payload was sent from GitHub by validating SHA256.
    
    Args:
        payload_body: original request body to verify (request.body())
        secret_token: GitHub app webhook token (WEBHOOK_SECRET)
        signature: header received from GitHub (x-hub-signature-256)

    Returns:
        True if signature is valid, False otherwise
    """
    
    if not signature:
        return False

    if not signature.startswith("sha256="):
        return False

    hash_object = hmac.new(secret_token.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + hash_object.hexdigest()

    return hmac.compare_digest(expected_signature, signature)
   
    

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

def extract_command(comment_body: str) -> Optional[dict]:
    """
    Extract /preview command

    Args:
        comment_body: the comment text

    Returns:
        Dict with command info if /preview found, None otherwise
    """
    if not comment_body:
        return None 

    lines = comment_body.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('/preview'):
            parts = line.split()
            command = {
                'command': 'preview',
                'raw': line
            }

            return command
    
    return None

async def post_comment_to_pr(
    repo_owner: str,
    repo_name: str,
    pr_number: int,
    comment: str,
    installation_id: int
) -> bool:
    """
    Post a comment to a PR using GitHub API.
    
    Args:
        repo_owner: Repository owner
        repo_name: Repository name
        pr_number: Pull request number
        comment: Comment text to post
        installation_id: GitHub App installation ID
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import aiohttp
        
        jwt_token = generate_jwt_token()
        
        # First, get installation access token
        async with aiohttp.ClientSession() as session:
            # Get installation access token
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            async with session.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers=headers
            ) as resp:
                if resp.status != 201:
                    logger.error(f"Failed to get installation token: {resp.status}")
                    return False
                token_data = await resp.json()
                access_token = token_data.get("token")
                permissions = token_data.get("permissions", {})
                logger.info(f"Installation token permissions: {permissions}")
                
                # Verify the token has issues write permission
                issues_permission = permissions.get("issues", "none")
                if issues_permission != "write":
                    logger.warning(f"Issues permission is '{issues_permission}', expected 'write'")
                    logger.warning("The installation may need to be reinstalled to get updated permissions")
            
            # First, verify we can access the repository
            headers = {
                "Authorization": f"token {access_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Test repository access
            logger.info(f"Testing repository access for {repo_owner}/{repo_name}")
            async with session.get(
                f"https://api.github.com/repos/{repo_owner}/{repo_name}",
                headers=headers
            ) as repo_check:
                repo_status = repo_check.status
                logger.info(f"Repository access check status: {repo_status}")
                
                if repo_status == 404:
                    repo_error = await repo_check.text()
                    logger.error(f"Repository {repo_owner}/{repo_name} not found or not accessible to installation")
                    logger.error(f"Response: {repo_error}")
                    logger.error("The installation may not have access to this repository")
                    logger.error("Check the installation's repository access settings")
                    return False
                elif repo_status == 403:
                    repo_error = await repo_check.text()
                    logger.error(f"Cannot access repository: 403 Forbidden")
                    logger.error(f"Response: {repo_error}")
                    logger.error("The installation may not have been granted access to this repository")
                    logger.error("Even if you just added it, try:")
                    logger.error("1. Wait a few seconds and try again (GitHub may need to sync)")
                    logger.error("2. Uninstall and reinstall the app to refresh access")
                    return False
                elif repo_status == 200:
                    repo_data = await repo_check.json()
                    logger.info(f"Repository access confirmed: {repo_data.get('full_name')}")
                    logger.info(f"Repository is {'private' if repo_data.get('private') else 'public'}")
                    
                    # Test if we can read the issue/PR (this helps verify permissions)
                    logger.info(f"Testing if we can read issue/PR #{pr_number}")
                    async with session.get(
                        f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues/{pr_number}",
                        headers=headers
                    ) as issue_check:
                        issue_status = issue_check.status
                        logger.info(f"Issue/PR read status: {issue_status}")
                        if issue_status == 200:
                            issue_data = await issue_check.json()
                            logger.info(f"Can read issue/PR: {issue_data.get('title', 'N/A')[:50]}")
                        elif issue_status == 403:
                            issue_error = await issue_check.text()
                            logger.error(f"Cannot read issue/PR: 403 - {issue_error}")
                            logger.error("This suggests a permissions issue even though repository access works")
                else:
                    repo_error = await repo_check.text()
                    logger.warning(f"Unexpected repository access status: {repo_status}")
                    logger.warning(f"Response: {repo_error}")
            
            # Post comment to PR
            payload = {"body": comment}
            comment_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues/{pr_number}/comments"
            logger.info(f"Posting comment to PR #{pr_number} at {comment_url}")
            logger.debug(f"Comment payload: {payload}")
            
            async with session.post(
                comment_url,
                headers=headers,
                json=payload
            ) as resp:
                resp_status = resp.status
                logger.info(f"Comment POST response status: {resp_status}")
                if resp.status == 201:
                    logger.info(f"Posted comment to PR #{pr_number}")
                    return True
                elif resp.status == 403:
                    error_text = await resp.text()
                    logger.error(f"Failed to post comment: 403 Forbidden")
                    logger.error(f"Error response: {error_text}")
                    logger.error("")
                    logger.error("Debugging info:")
                    logger.error(f"  - Repository: {repo_owner}/{repo_name}")
                    logger.error(f"  - PR Number: {pr_number}")
                    logger.error(f"  - Installation ID: {installation_id}")
                    logger.error(f"  - Token has 'issues: write' permission: Yes")
                    logger.error("")
                    logger.error("Possible causes:")
                    logger.error("1. Repository access: The installation may not have access to this specific repository")
                    logger.error("2. Installation settings: Check if the installation is set to 'All repositories' or includes this repo")
                    logger.error("3. Repository permissions: Even with 'Issues: Write', the repo must be accessible")
                    logger.error("4. GitHub sync delay: If you just added the repo, wait 10-30 seconds and try again")
                    logger.error("")
                    logger.error("To check/fix:")
                    logger.error("1. Go to: https://github.com/settings/installations")
                    logger.error("2. Find your GitHub App installation (ID: {})".format(installation_id))
                    logger.error("3. Click 'Configure'")
                    logger.error("4. Under 'Repository access', verify this repository is listed")
                    logger.error("5. If you just added it, wait a moment and try again")
                    logger.error("6. Try uninstalling and reinstalling the app to refresh access")
                    return False
                else:
                    error_text = await resp.text()
                    logger.error(f"Failed to post comment: {resp.status} - {error_text}")
                    return False
                    
    except Exception as e:
        logger.error(f"Error posting comment to PR: {e}")
        return False


@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(None, alias="X-GitHub-Event"), 
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
    x_github_hook_installation_target_id: str = Header(None, alias="X-GitHub-Hook-Installation-Target-ID")):
    body_bytes = await request.body()
    
    # Verify signature first
    if not verify_signature(body_bytes, GITHUB_WEBHOOK_SECRET, x_hub_signature_256):
        logger.warning("Webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )    
    
    logger.info(f"Received GitHub event: {x_github_event}")

    if x_github_event != "issue_comment":
        logger.debug(f"Ignoring event type: {x_github_event}")
        return JSONResponse(
            status_code=200,
            content={"message": f"Event type {x_github_event} ignored"}
        )

    # Extract event data
    action = payload.get("action")
    comment = payload.get("comment", {})
    issue = payload.get("issue", {})
    repository = payload.get("repository", {})
    
    # Get repository info first (needed for validation and lookup)
    repo_owner = repository.get("owner", {}).get("login")
    repo_name = repository.get("name")
    repository_id = repository.get("id")

    # Get installation ID from header (most reliable for GitHub Apps)
    installation_id = None
    if x_github_hook_installation_target_id:
        try:
            potential_id = int(x_github_hook_installation_target_id)
            # Check if it's the repository ID (common mistake - header might be wrong)
            if repository_id and potential_id == repository_id:
                logger.warning(f"Header value {potential_id} matches repository ID, ignoring it")
            else:
                installation_id = potential_id
                logger.info(f"Got installation id from header: {installation_id}")
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid installation ID in header: {x_github_hook_installation_target_id}, error: {e}")
    
    # Fallback: try from payload (won't work for issue_comment events)
    if not installation_id:
        installation = payload.get("installation", {})
        installation_id = installation.get("id")
        if installation_id:
            logger.info(f"Got installation id from payload: {installation_id}")
    
    # Fallback: Look up installation ID via API
    if not installation_id and repo_owner:
        logger.info(f"Looking up installation ID for owner: {repo_owner}")
        try:
            jwt_token = generate_jwt_token()
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github.v3+json"
                }
                
                # Method 1: Try direct user/org installation endpoint
                # Try as user first
                async with session.get(
                    f"https://api.github.com/users/{repo_owner}/installation",
                    headers=headers
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        installation_id = data.get("id")
                        logger.info(f"Found installation ID via user lookup: {installation_id}")
                    elif resp.status == 404:
                        # Try as organization
                        async with session.get(
                            f"https://api.github.com/orgs/{repo_owner}/installation",
                            headers=headers
                        ) as org_resp:
                            if org_resp.status == 200:
                                org_data = await org_resp.json()
                                installation_id = org_data.get("id")
                                logger.info(f"Found installation ID via org lookup: {installation_id}")
                
                # Method 2: List all installations (fallback if direct lookup fails)
                if not installation_id:
                    logger.info("Listing all app installations")
                    async with session.get(
                        "https://api.github.com/app/installations",
                        headers=headers
                    ) as resp:
                        if resp.status == 200:
                            installations = await resp.json()
                            logger.info(f"Found {len(installations)} installation(s)")
                            
                            if len(installations) == 0:
                                logger.error("GitHub App has no installations. Please install the app on your account/organization.")
                            elif len(installations) == 1:
                                # If only one installation, use it
                                installation_id = installations[0].get("id")
                                account = installations[0].get("account", {})
                                account_login = account.get("login", "unknown")
                                logger.info(f"Using single installation ID {installation_id} for account {account_login}")
                            else:
                                # Multiple installations - try to find one that matches the repo owner
                                for inst in installations:
                                    account = inst.get("account", {})
                                    account_login = account.get("login", "")
                                    if account_login.lower() == repo_owner.lower():
                                        installation_id = inst.get("id")
                                        logger.info(f"Found matching installation ID {installation_id} for {account_login}")
                                        break
                                
                                # If no match, use the first one (with warning)
                                if not installation_id:
                                    installation_id = installations[0].get("id")
                                    account = installations[0].get("account", {})
                                    account_login = account.get("login", "unknown")
                                    logger.warning(f"Multiple installations found, using first one (ID: {installation_id}, account: {account_login})")
                        else:
                            error_text = await resp.text()
                            logger.error(f"Failed to list installations: {resp.status}")
                            logger.error(f"Error response: {error_text}")
                            
        except Exception as e:
            logger.error(f"Error looking up installation ID: {e}")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")

    if action != "created":
        logger.debug(f"Ignoring action: {action}")
        return JSONResponse(
            status_code=200,
            content={"message": f"Action {action} ignored"}
        )

    if "pull" not in issue.get("html_url", ""):
        logger.debug("Comment is not on a PR, ignoring")
        return JSONResponse(
            status_code=200,
            content={"message": "Comment is not on a PR"}
        )

    # Extract PR number
    pr_number = issue.get("number")
    if not pr_number:
        logger.warning("Could not extract PR number from issue")
        return JSONResponse(
            status_code=200,
            content={"message": "Could not extract PR number"}
        )
    
    # Validate we have all required info
    if not installation_id:
        logger.error("Could not determine installation ID")
        logger.error("This usually means:")
        logger.error("1. The GitHub App is not installed on your account/organization")
        logger.error("2. The webhook is not configured correctly")
        logger.error("3. The installation was removed")
        return JSONResponse(
            status_code=200,
            content={
                "message": "Could not determine installation ID. Please ensure the GitHub App is installed on this repository.",
                "help": "Go to your GitHub App settings and install it on your account or organization."
            }
        )
    
    if not all([repo_owner, repo_name]):
        logger.warning("Missing required repository info")
        return JSONResponse(
            status_code=200,
            content={"message": "Missing repository information"}
        )
    
    # Extract comment body and check for /preview command
    comment_body = comment.get("body", "")
    preview_command = extract_command(comment_body)
    
    if not preview_command:
        logger.debug("No /preview command found in comment")
        return JSONResponse(
            status_code=200,
            content={"message": "No /preview command found"}
        )

    logger.info(f"Processing /preview command for PR #{pr_number} in {repo_owner}/{repo_name}")

    # Get the PR to extract the commit SHA
    try:
        jwt_token = generate_jwt_token()

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            async with session.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers=headers
            ) as resp:
                if resp.status != 201:
                    error_text = await resp.text()
                    logger.error(f"Failed to get installation token: {resp.status}")
                    logger.error(f"Installation ID used: {installation_id}")
                    logger.error(f"Error response: {error_text}")
                    return JSONResponse(
                        status_code=200,
                        content={"message": f"Failed to get installation token: {resp.status}"}
                    )
                token_data = await resp.json()
                access_token = token_data.get("token")
                logger.info(f"Successfully obtained installation access token")
            
            # Get PR details
            headers = {
                "Authorization": f"token {access_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            async with session.get(
                f"https://api.github.com/repos/{repo_owner}/{repo_name}/pulls/{pr_number}",
                headers=headers
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to get PR details: {resp.status}")
                    await post_comment_to_pr(
                        repo_owner, repo_name, pr_number,
                        "❌ Failed to retrieve PR information.",
                        installation_id
                    )
                    return JSONResponse(
                        status_code=200,
                        content={"message": "Failed to get PR details"}
                    )
                pr_data = await resp.json()
                commit_sha = pr_data.get("head", {}).get("sha")
                
                if not commit_sha:
                    logger.error("Could not extract commit SHA from PR")
                    await post_comment_to_pr(
                        repo_owner, repo_name, pr_number,
                        "❌ Could not determine commit SHA for deployment.",
                        installation_id
                    )
                    return JSONResponse(
                        status_code=200,
                        content={"message": "Could not get commit SHA"}
                    )
       

    except Exception as e:
        logger.error(f"Error getting PR details: {e}")


     # Post initial response comment
    await post_comment_to_pr(
        repo_owner, repo_name, pr_number,
        "🚀 Deployment requested! Setting up preview environment...",
        installation_id
    )

    return {"message": "waaaa"}

@app.get("/")
async def root():
    return {"status": "healthy"}


@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=port,
        log_level="debug",
        reload=os.getenv("DEBUG","false").lower() == "true"
    )