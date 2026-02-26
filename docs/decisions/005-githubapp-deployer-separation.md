# Separate GitHub App and Deployer for Scalable Preview Deployments

Date: 2026-02-12

Status: proposed

## Context

- The preview deploy service has two distinct responsibilities:
  1. **GitHub App**: Receive webhooks, validate `/preview` commands, post comments to PRs.
  2. **Deployer**: Provision preview environments in GKE (Helm install), generate preview URLs.
- Requirements call for handling bursts of activity (e.g., ~50 concurrent PR preview requests).
- If the GitHub App and Deployer are tightly coupled (e.g., same process), scaling to handle bursts would require scaling the entire webhook handler, which also increases GitHub webhook delivery surface and complexity.
- A single Deployer instance can become a bottleneck: Helm installs and K8s API calls are relatively slow; under load, webhook processing would block or time out.
- We need a design that:
  - Keeps the GitHub App lightweight and fast (acknowledge webhooks quickly).
  - Allows multiple Deployer instances to process deployment work in parallel.
  - Avoids **missed deployments** (requests lost or never processed).
  - Avoids **duplicate deployments** (same PR/commit deployed more than once by different workers).

## Decision

### 1. Separation of Concerns

- **GitHub App** (webhook service):
  - Receives GitHub webhooks, validates signatures, parses `/preview` commands.
  - Does **not** perform Helm or K8s operations.
  - Enqueues a deployment request and responds to GitHub quickly (e.g., posts "Deployment requested! Setting up preview environment...").
  - Stateless; can be scaled horizontally for webhook throughput.

- **Deployer** (worker service):
  - Pulls deployment requests from a shared work queue.
  - Performs Helm install, waits for readiness, obtains preview URL.
  - Updates deployment status and notifies the GitHub App (or a callback) to post the preview URL to the PR.
  - Can run multiple instances; each instance processes one or more requests concurrently.

### 2. Mechanism: GitHub App → Deployer

Use a **durable work queue** with at-least-once delivery:

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **Cloud Tasks** (GCP) | HTTP target or pull queue | Managed, retries, DLQ, integrates with GKE | GCP-specific |
| **Cloud Pub/Sub** | Publish message, workers subscribe | Managed, push or pull | No built-in "claim" semantics; need idempotency |
| **Redis + RQ/Celery** | In-memory queue with persistence | Simple, well-known | Requires Redis; operational overhead |


**Recommended for GCP/GKE**: **Cloud Tasks** (or Pub/Sub with a pull subscription).

**Request payload** (enqueued by GitHub App):

```json
{
  "idempotency_key": "owner/repo#123:abc123def",
  "repo": "owner/repo",
  "pr_number": 123,
  "commit_sha": "abc123def",
  "installation_id": 456,
  "comment_id": 789
}
```

- `idempotency_key`: Unique per PR+commit; used to detect duplicates.
- `comment_id`: Used to post the preview URL reply in the correct thread.

**Flow**:

1. GitHub App receives webhook → validates `/preview` → enqueues request → posts "Deployment requested..." (synchronous, fast).
2. Deployer worker pulls task → checks idempotency → performs Helm install → posts preview URL via GitHub API (using installation token).

### 3. Orchestration: Avoiding Missed and Duplicate Deployments

#### Avoiding Missed Deployments

- **Durable queue**: Messages persist until acknowledged. If a worker crashes, the message is redelivered (at-least-once).
- **Retries**: Configure retry policy (e.g., exponential backoff) for transient failures.
- **Dead-letter queue (DLQ)**: After N failed attempts, move to DLQ for manual inspection.
- **Visibility timeout / lease**: While a worker processes a task, it is invisible to other workers (Cloud Tasks, SQS) to avoid double delivery during processing.

#### Avoiding Duplicate Deployments

- **Idempotency key**: Each request has a unique key (e.g., `owner/repo#pr_number:commit_sha`).
- **Statestore check before deploy**: Before running `helm install`, the Deployer:
  1. Tries to **claim** the idempotency key in the statestore (e.g., `INSERT ... ON CONFLICT DO NOTHING` or compare-and-swap with status `claimed`).
  2. If claim fails (key already exists with status `deployed` or `in_progress`), skip deployment and optionally post a "Preview already exists" comment.
  3. If claim succeeds, proceed with Helm install.
- **Statestore updates**: On success, set status `deployed` and store preview URL. On failure, release the claim so a retry can try again.
- **Helm release naming**: Use deterministic names (e.g., `preview-pr-123`) so a duplicate `helm install` would fail with "release already exists"; the worker can treat that as idempotent success and fetch the existing URL.

### 4. Scaling Behavior

- **Low demand**: Run 1 Deployer instance; queue stays empty or near-empty.
- **High demand**: Scale Deployer horizontally (e.g., HPA on queue depth or CPU). Each instance pulls tasks independently; the queue and statestore coordinate to prevent duplicates.
- **GitHub App**: Scale based on webhook request rate; remains stateless and fast.

## Alternatives Considered

- **A. Monolithic GitHub App + Deployer**
  - Pros: Simple, single codebase.
  - Cons: Cannot scale deployment work independently; webhook handling blocks on Helm; poor latency under load.
  - **Rejected** for scaling and latency reasons.

- **B. Synchronous HTTP from GitHub App to Deployer**
  - GitHub App calls Deployer over HTTP, waits for completion.
  - Pros: Simple request/response.
  - Cons: Long-running HTTP ties up webhook handler; timeouts; no natural retry or backpressure.
  - **Rejected**; queue decouples and provides retries.

- **C. Kubernetes Jobs per deployment**
  - GitHub App creates a K8s Job; Job runs Helm.
  - Pros: Uses K8s primitives; Jobs can retry.
  - Cons: Job lifecycle management; harder to coordinate idempotency and status; more K8s API churn.
  - **Deferred**; queue + worker is simpler for now.

- **D. Event-driven with no statestore**
  - Rely only on queue deduplication.
  - Cons: Queues typically offer at-least-once delivery; duplicates are possible. Without a statestore, we cannot safely deduplicate.
  - **Rejected**; statestore (or equivalent) is needed for idempotency.

## Consequences

- **Positive**
  - **Independent scaling**: GitHub App and Deployer scale separately based on their respective load.
  - **Resilience**: Queue provides buffering and retries; workers can crash and tasks are redelivered.
  - **No missed deployments**: Durable queue + retries ensure requests are eventually processed.
  - **No duplicate deployments**: Idempotency key + statestore claim prevents double deploys for the same PR/commit.
  - **Fast webhook response**: GitHub App responds quickly; GitHub does not time out waiting for deployment.

- **Negative / Trade-offs**
  - **Additional components**: Queue (Cloud Tasks/Pub/Sub) and statestore must be operated and monitored.
  - **Eventual consistency**: Preview URL is posted asynchronously; user may wait a few seconds to a minute.
  - **Operational complexity**: Need to handle DLQ, monitor queue depth, and debug failed tasks.

- **Follow-ups**
  - Implement queue integration in GitHub App (enqueue on `/preview`).
  - Implement Deployer worker loop (pull, claim, deploy, post URL).
  - Add statestore schema and claim logic for idempotency.
  - Document runbook for DLQ and scaling.
  - Observability requirements
