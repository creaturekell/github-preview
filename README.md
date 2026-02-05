# Github PR Deploy Preview

This repository explores the design and early implementation of a **preview deploy service** that allows engineers to deploy to an ephemeral preview environment directly from a GitHub pull request.

The primary goal is to improve developer confidence and reduce production risk by making changes visible and testable before merge.

> ⚠️ This project is intentionally a **work in progress** and is focused on architecture, tradeoffs, and developer experience rather than full production hardening.

---

## Problem Statement

Before deploying to production, engineers benefit from seeing their changes live in an isolated environment. The desired developer experience is simple:

1. An engineer comments `/preview` on a pull request (chose this over `/deploy` to be explicit that this isn't going to production)
2. Changes are deployed to a preview environment automatically
3. A preview URL is posted back to the PR
4. The environment is cleaned up after a fixed TTL

---

## Requirements

1. **Developer Experience**  
   Engineers trigger preview deployments via a `/preview` comment on a GitHub PR.

2. **Automatic Cleanup**  
   Preview environments must clean up after themselves to avoid unnecessary infrastructure cost.

3. **Scalability**  
   The system should handle bursts of activity (e.g., ~50 concurrent PR preview requests).

4. **Failure & Orphan Handling**  
   Partial or failed deployments may leave orphaned resources; these must be detected and cleaned up safely.
5. **Security**
   Prevent access to folks external to the company.  

---

## Architecture  

Design decisions and tradeoffs are documented in `/docs/decisions`.


### Core Components

| Service                                              | Description 
| ---------------------------------------------------- | ------------- |
| helloworld |  A simple containerized Python application used as the preview workload. |
| githubapp | A GitHub App that listens to webhook events and responds to `/preview` commands on pull requests. |
| deployer | A Deployment Orchestrator - Responsible for provisioning preview environments in GKE and generating preview URLs. |
| cleanup | Periodically scans for expired or orphaned preview environments and removes them. |
| statestore | Tracks preview deployments, ownership, timestamps, and lifecycle state. |

---

## High-Level Flow 

```mermaid
sequenceDiagram
    participant Engineer
    participant GitHub
    participant GitHubApp as GitHub App Service
    participant Deployer as Deployment Orchestrator
    participant GKE
    participant Cleanup as Cleanup Service
    participant DB as State Database

    Engineer->>GitHub: Comments "/preview" on PR
    GitHub->>GitHubApp: Webhook (issue_comment event)
    GitHubApp->>GitHubApp: Validate /preview command
    GitHubApp->>GitHub: PR Comment "Deployment requested! Setting up preview environment..."
    GitHubApp->>DB: Create deployment record
    GitHubApp->>Deployer: Queue deployment request
    Deployer->>GKE: Create namespace, deployment, service
    Deployer->>GKE: Configure ingress with preview URL
    Deployer->>DB: Update deployment status + URL
    Deployer->>GitHubApp: Deployment complete
    GitHubApp->>GitHub: Post preview URL comment
    Note over Cleanup,DB: Every 5 minutes
    Cleanup->>DB: Query deployments > 30min old
    Cleanup->>GKE: Delete namespace + resources
    Cleanup->>DB: Mark deployment as cleaned

```

--- 
## Screenshots

Will eventually add screenshots or video here.

---
## Quickstart

1. [Setup](/src/setupgke/README.md) preview Google Cloud Kubernetes Cluster 


---
## Why a GitHub App?

Details are captured in [`/docs/decisions/01-github-app.md`](/docs/decisions/01-github-app.md).

---

## Status

- Architecture and core flow defined
- Python helloworld app created for the simulated app to deploy
- GitHub App webhook handling to process /preview and post a comment in the PR that "Deployment requested! Setting up preview environment..."

- In Progress: Cleaning up the githubapp, there is a lot of extra code that was added while troubleshooting 403 error because of the installation_id not working.  Resolved by installing the app and enabling write permissions for pull request in addition to issue write permissions.

- Next: Setup initial GKE preview environment 


## Future considerations

- multiple apps are required for the preview
- rate limiting and communication back to the developer on when their preview will be deployed
- observability
- class of service, are some /previews more important then others
 