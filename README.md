# Github PR Preview 

# Requirements 

1. Create a developer experience that involves an engineering executing a /deploy command in github that kicks off the deploy and then provides a preview-url to the engineer.

2. After the preview is comlpete, clean-up after one-self

3. Additional scenerios to consider, 50 /deploy requests at a time.  How would you clean up.

4. Partial deploys, where a container might orphaned, how do you handle that to prevent unnecessary costs. 


# Design Overview 

See /docs/descisions for design descisions

1. Hello World App - Simple Python static site container
2. Preview GitHub App Service  - Webhook server that listens for /deploy commands
3. Deployment Orchestrator - Manages GKE deployments and generates preview URLs
4. Cleanup Service - Handles cleanup and orphan detection



## Flow 

sequenceDiagram
    participant Engineer
    participant GitHub
    participant GitHubApp as GitHub App Service
    participant Deployer as Deployment Orchestrator
    participant GKE
    participant Cleanup as Cleanup Service
    participant DB as State Database

    Engineer->>GitHub: Comments "/deploy" on PR
    GitHub->>GitHubApp: Webhook (issue_comment event)
    GitHubApp->>GitHubApp: Validate /deploy command
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