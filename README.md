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
   - Engineers trigger preview deployments via a `/preview` comment on a GitHub PR.
   - preview url return within seconds, not minutes.
   - if it takes minutes to spin up, communicate back to the engineer on status

2. **Automatic Cleanup**  
   Preview environments must clean up after themselves to avoid unnecessary infrastructure cost.
   Preview environments available for 4 hours or when PR is closed

3. **Scalability**  
   The system should handle bursts of activity (e.g., ~50 concurrent PR preview requests).

4. **Failure & Orphan Handling**  
   Partial or failed deployments may leave orphaned resources; these must be detected and cleaned up safely.
   
5. **Security**
   Prevent access to folks external to the company.  

---

## Architecture  

Design decisions and tradeoffs are documented in `/docs/decisions`.

```mermaid
flowchart TB
    subgraph External["External"]
        Engineer
        GitHub["GitHub (PR Comments)"]
        DNS["DNS *.yourhostname"]
    end

    subgraph Services["Preview Deploy Services"]
        GitHubApp["GitHub App<br/>Webhook Handler"]
        Deployer["Deployer<br/>Helm + K8s API"]
    end

    subgraph GKE["GKE Cluster"]
        subgraph ingress["ingress-nginx namespace"]
            NGINX["NGINX Ingress Controller<br/>LoadBalancer (single IP)"]
        end

        subgraph preview1["preview-pr-123 namespace"]
            Svc1["Service"]
            Pod1["helloworld Pod"]
        end

        subgraph preview2["preview-pr-456 namespace"]
            Svc2["Service"]
            Pod2["helloworld Pod"]
        end
    end

    subgraph Future["Planned"]
        Cleanup["Cleanup Service"]
        Statestore["State Store"]
        Dashboard["Dashboard"]
    end

    Engineer -->|"/preview" added to PR comment| GitHub
    GitHub -->|Webhook| GitHubApp
    GitHubApp -->|Helm install| Deployer
    Deployer -->|Create namespace, Deployment, Service, Ingress| GKE
    NGINX -->|route by host| Svc1
    NGINX -->|route by host| Svc2
    Svc1 --> Pod1
    Svc2 --> Pod2
    DNS -->|A record| NGINX
    Engineer -->|http://preview-pr-123.yourhostname| DNS
    Cleanup -.->|"periodic scan"| GKE
    Deployer -.->|"deployment state"| Statestore
    Statestore -.->|"status"| Dashboard
```

### Core Components

| Service                                              | Description 
| ---------------------------------------------------- | ------------- |
| helloworld |  A simple containerized Python application used as the preview workload. |
| githubapp | A GitHub App that listens to webhook events and responds to `/preview` commands on pull requests. |
| deployer | A Deployment Orchestrator - Responsible for provisioning preview environments in GKE and generating preview URLs. |
| cleanup | Periodically scans for expired or orphaned preview environments and removes them. |
| statestore | Tracks preview deployments, ownership, timestamps, and lifecycle state. |
| dashboard | Displays the status of previews |

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

## Status

### Done:
- Architecture and core flow defined
- Python helloworld app created for the simulated app to deploy
- GitHub App webhook handling to process /preview and post a comment in the PR that "Deployment requested! Setting up preview environment..."
- Refactor and modularize githubapp 
- Setup initial GKE preview environment and manually perform deploy steps of helloworld 
    - Build Docker Image(s)
    - Publish Docker Image to container registry
    - Build helm chart
    - Deploy helm chart
    - Get preview URL

### Wip:

manual steps work, focus on deployer, milestones below
m1: chose statestore, schema and claim logic
m2: cloud tasks queue setup 
m3: update github-app to use enqueue
m4: deploye worker task handler and peforms helm install
m5: idempotency and error handling
m6: deployment and scaling
m7: documentation 

### Next: 


7. dashboard of preview status
8. create clean-up service
9. create scaffolding for services, that incorporate 12factor app factors and observability.
9. expand complexity of app beyond helloworld
9. support for launching dependant services
10. population of initial data into the application






