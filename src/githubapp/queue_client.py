"""
Cloud Tasks client for enqueueing deployment requests.

Enqueues tasks to be delivered via HTTP POST to the Deployer service.
"""

import json
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)


def enqueue_deployment_task(payload: Dict[str, Any]) -> bool:
    """
    Enqueue a deployment task to Cloud Tasks.

    Payload must include: idempotency_key, repo, pr_number, commit_sha,
    installation_id, comment_id (optional).

    Returns True if enqueued successfully, False otherwise.
    """
    project = os.getenv("CLOUD_TASKS_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("CLOUD_TASKS_LOCATION", "us-central1")
    queue = os.getenv("CLOUD_TASKS_QUEUE", "preview-deploy-queue")
    deployer_url = os.getenv("DEPLOYER_URL")

    if not deployer_url:
        logger.error("DEPLOYER_URL not set; cannot enqueue deployment task")
        return False

    if not project:
        logger.error("CLOUD_TASKS_PROJECT not set; cannot enqueue deployment task")
        return False

    try:
        from google.cloud import tasks_v2

        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(project, location, queue)

        from google.cloud.tasks_v2 import HttpRequest, Task

        http_request = HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=deployer_url.rstrip("/") + "/tasks/deploy",
            headers={"Content-Type": "application/json"},
            body=json.dumps(payload).encode(),
        )
        task = Task(http_request=http_request)

        response = client.create_task(parent=parent, task=task)
        logger.info(
            f"Enqueued deployment task: {payload.get('idempotency_key', 'unknown')}",
            extra={
                "idempotency_key": payload.get("idempotency_key"),
                "pr_number": payload.get("pr_number"),
                "task_name": response.name,
            },
        )
        return True

    except Exception as e:
        logger.error(
            f"Failed to enqueue deployment task: {e}",
            extra={"idempotency_key": payload.get("idempotency_key")},
        )
        return False
