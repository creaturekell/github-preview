"""GitHub API client for interacting with GitHub's API."""
import logging
from typing import Optional, Dict, Any
import aiohttp
import jwt
from datetime import datetime

from .config import Config

logger = logging.getLogger(__name__)


class GitHubClient:
    """Client for interacting with GitHub API."""
    
    BASE_URL = "https://api.github.com"
    
    def __init__(self):
        self._jwt_token: Optional[str] = None
    
    def _generate_jwt_token(self) -> str:
        """Generate a JWT token for GitHub App authentication."""
        if not Config.GITHUB_APP_ID or not Config.GITHUB_APP_PRIVATE_KEY:
            raise ValueError("GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY must be set")
        
        now = int(datetime.now().timestamp())
        payload = {
            "iat": now - 60,  # Issued at time (1 minute ago to account for clock skew)
            "exp": now + (10 * 60),  # Expires in 10 minutes
            "iss": Config.GITHUB_APP_ID
        }
        
        return jwt.encode(payload, Config.GITHUB_APP_PRIVATE_KEY, algorithm="RS256")
    
    async def get_installation_access_token(self, installation_id: int) -> Optional[str]:
        """Get an installation access token."""
        jwt_token = self._generate_jwt_token()
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            async with session.post(
                f"{self.BASE_URL}/app/installations/{installation_id}/access_tokens",
                headers=headers
            ) as resp:
                if resp.status != 201:
                    error_text = await resp.text()
                    logger.error(f"Failed to get installation token: {resp.status} - {error_text}")
                    return None
                
                token_data = await resp.json()
                permissions = token_data.get("permissions", {})
                logger.info(f"Installation token permissions: {permissions}")
                return token_data.get("token")
    
    async def find_installation_id(self, repo_owner: str) -> Optional[int]:
        """Find installation ID for a repository owner."""
        logger.info(f"Looking up installation ID for owner: {repo_owner}")
        jwt_token = self._generate_jwt_token()
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Try direct user/org installation endpoint
            async with session.get(
                f"{self.BASE_URL}/users/{repo_owner}/installation",
                headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    installation_id = data.get("id")
                    logger.info(f"Found installation ID via user lookup: {installation_id}")
                    return installation_id
                elif resp.status == 404:
                    # Try as organization
                    async with session.get(
                        f"{self.BASE_URL}/orgs/{repo_owner}/installation",
                        headers=headers
                    ) as org_resp:
                        if org_resp.status == 200:
                            org_data = await org_resp.json()
                            installation_id = org_data.get("id")
                            logger.info(f"Found installation ID via org lookup: {installation_id}")
                            return installation_id
            
            # Fallback: List all installations
            return await self._find_installation_from_list(session, headers, repo_owner)
    
    async def _find_installation_from_list(
        self, 
        session: aiohttp.ClientSession, 
        headers: Dict[str, str], 
        repo_owner: str
    ) -> Optional[int]:
        """Find installation ID from list of all installations."""
        logger.info("Listing all app installations")
        async with session.get(
            f"{self.BASE_URL}/app/installations",
            headers=headers
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.error(f"Failed to list installations: {resp.status} - {error_text}")
                return None
            
            installations = await resp.json()
            logger.info(f"Found {len(installations)} installation(s)")
            
            if len(installations) == 0:
                logger.error("GitHub App has no installations.")
                return None
            elif len(installations) == 1:
                installation_id = installations[0].get("id")
                account = installations[0].get("account", {})
                account_login = account.get("login", "unknown")
                logger.info(f"Using single installation ID {installation_id} for account {account_login}")
                return installation_id
            else:
                # Multiple installations - try to find one that matches the repo owner
                for inst in installations:
                    account = inst.get("account", {})
                    account_login = account.get("login", "")
                    if account_login.lower() == repo_owner.lower():
                        installation_id = inst.get("id")
                        logger.info(f"Found matching installation ID {installation_id} for {account_login}")
                        return installation_id
                
                # If no match, use the first one (with warning)
                installation_id = installations[0].get("id")
                account = installations[0].get("account", {})
                account_login = account.get("login", "unknown")
                logger.warning(f"Multiple installations found, using first one (ID: {installation_id}, account: {account_login})")
                return installation_id
    
    async def get_pr_details(
        self, 
        repo_owner: str, 
        repo_name: str, 
        pr_number: int, 
        access_token: str
    ) -> Optional[Dict[str, Any]]:
        """Get pull request details."""
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"token {access_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            async with session.get(
                f"{self.BASE_URL}/repos/{repo_owner}/{repo_name}/pulls/{pr_number}",
                headers=headers
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Failed to get PR details: {resp.status} - {error_text}")
                    return None
                
                return await resp.json()
    
    async def post_comment(
        self,
        repo_owner: str,
        repo_name: str,
        pr_number: int,
        comment: str,
        installation_id: int
    ) -> bool:
        """Post a comment to a PR."""
        access_token = await self.get_installation_access_token(installation_id)
        if not access_token:
            return False
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"token {access_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Verify repository access
            if not await self._verify_repository_access(session, headers, repo_owner, repo_name, pr_number):
                return False
            
            # Post comment
            payload = {"body": comment}
            comment_url = f"{self.BASE_URL}/repos/{repo_owner}/{repo_name}/issues/{pr_number}/comments"
            logger.info(f"Posting comment to PR #{pr_number}")
            
            async with session.post(comment_url, headers=headers, json=payload) as resp:
                if resp.status == 201:
                    logger.info(f"Posted comment to PR #{pr_number}")
                    return True
                elif resp.status == 403:
                    error_text = await resp.text()
                    logger.error(f"Failed to post comment: 403 Forbidden - {error_text}")
                    logger.error("Installation may need repository access or reinstallation")
                    return False
                else:
                    error_text = await resp.text()
                    logger.error(f"Failed to post comment: {resp.status} - {error_text}")
                    return False
    
    async def _verify_repository_access(
        self,
        session: aiohttp.ClientSession,
        headers: Dict[str, str],
        repo_owner: str,
        repo_name: str,
        pr_number: int
    ) -> bool:
        """Verify that we can access the repository and issue."""
        # Check repository access
        async with session.get(
            f"{self.BASE_URL}/repos/{repo_owner}/{repo_name}",
            headers=headers
        ) as repo_check:
            if repo_check.status == 404:
                logger.error(f"Repository {repo_owner}/{repo_name} not found or not accessible")
                return False
            elif repo_check.status == 403:
                logger.error(f"Cannot access repository: 403 Forbidden")
                logger.error("Installation may not have been granted access to this repository")
                return False
            elif repo_check.status == 200:
                repo_data = await repo_check.json()
                logger.info(f"Repository access confirmed: {repo_data.get('full_name')}")
                # Verify we can read the issue
                async with session.get(
                    f"{self.BASE_URL}/repos/{repo_owner}/{repo_name}/issues/{pr_number}",
                    headers=headers
                ) as issue_check:
                    if issue_check.status == 403:
                        issue_error = await issue_check.text()
                        logger.error(f"Cannot read issue/PR: 403 - {issue_error}")
                        return False
                    elif issue_check.status == 200:
                        logger.debug("Can read issue/PR")
        
        return True
