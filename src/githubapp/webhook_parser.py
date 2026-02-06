"""Webhook payload parsing and validation."""
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class WebhookParser:
    """Parser for GitHub webhook payloads."""
    
    @staticmethod
    def extract_command(comment_body: str) -> Optional[Dict[str, str]]:
        """Extract /preview command from comment body."""
        if not comment_body:
            return None
        
        lines = comment_body.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('/preview'):
                return {
                    'command': 'preview',
                    'raw': line
                }
        
        return None
    
    @staticmethod
    def parse_issue_comment_event(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse issue_comment event payload and extract relevant data."""
        action = payload.get("action")
        if action != "created":
            logger.debug(f"Ignoring action: {action}")
            return None
        
        issue = payload.get("issue", {})
        comment = payload.get("comment", {})
        repository = payload.get("repository", {})
        
        # Check if comment is on a PR
        if "pull" not in issue.get("html_url", ""):
            logger.debug("Comment is not on a PR, ignoring")
            return None
        
        pr_number = issue.get("number")
        if not pr_number:
            logger.warning("Could not extract PR number from issue")
            return None
        
        repo_owner = repository.get("owner", {}).get("login")
        repo_name = repository.get("name")
        repository_id = repository.get("id")
        
        if not all([repo_owner, repo_name]):
            logger.warning("Missing required repository info")
            return None
        
        comment_body = comment.get("body", "")
        command = WebhookParser.extract_command(comment_body)
        
        if not command:
            logger.debug("No /preview command found in comment")
            return None
        
        return {
            "pr_number": pr_number,
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "repository_id": repository_id,
            "comment_body": comment_body,
            "command": command
        }
    
    @staticmethod
    def extract_installation_id(
        payload: Dict[str, Any],
        header_value: Optional[str],
        repository_id: Optional[int]
    ) -> Optional[int]:
        """Extract installation ID from header or payload."""
        installation_id = None
        
        # Try header first
        if header_value:
            try:
                potential_id = int(header_value)
                # Check if it's the repository ID (common mistake)
                if repository_id and potential_id == repository_id:
                    logger.warning(f"Header value {potential_id} matches repository ID, ignoring it")
                else:
                    installation_id = potential_id
                    logger.info(f"Got installation id from header: {installation_id}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid installation ID in header: {header_value}, error: {e}")
        
        # Fallback: try from payload
        if not installation_id:
            installation = payload.get("installation", {})
            installation_id = installation.get("id")
            if installation_id:
                logger.info(f"Got installation id from payload: {installation_id}")
        
        return installation_id
