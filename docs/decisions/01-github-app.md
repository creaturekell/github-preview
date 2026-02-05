# Design Decision: GitHub App for Preview Deploys

Date: 2026-02-04  
Status: Accepted

## Context

Before a developer deploys to production, having a preview URL turns *“I think this works”* into *“anyone can see this works.”* Preview environments reduce risk, improve collaboration, and increase confidence in changes before they reach production.

The desired developer experience is simple:
- A developer comments `/preview` on a pull request
- A preview environment is created
- A URL is returned and attached to the PR
- The preview environment is automatically torn down after a fixed TTL

### Initial Approach: GitHub Actions

GitHub Actions initially appeared to be the most straightforward solution:

- Native integration with GitHub
- Simple setup using `.github/workflows/*.yml`
- No separate service to deploy or operate

However, deeper analysis revealed several drawbacks:

- GitHub Actions are subject to concurrency and execution limits
- Managing long-running preview environments is awkward
- Cleanup and orphaned preview detection would require additional workflows
- Stateful coordination across many pull requests becomes complex and brittle

As scale increases (many PRs, frequent preview deploys), this approach becomes difficult to reason about and maintain.

### Alternative: GitHub App

A GitHub App can integrate with GitHub via the REST API and webhooks, listening for issue comment events and reacting when a `/deploy` command is issued.

Advantages of this approach include:

1. **Scalability**  
   The app runs continuously and is deployed independently, allowing it to handle significantly more load than GitHub Actions.

2. **Stateful logic**  
   The service can track active preview environments, TTLs, ownership, and cleanup state in a durable way.

3. **Lifecycle management**  
   Preview creation, expiration, and orphan detection are easier to model and enforce outside of ephemeral CI jobs.

4. **Clear separation of concerns**  
   GitHub Actions remain focused on CI, while the app owns preview environment orchestration.

The primary downside is increased setup and operational complexity, but this tradeoff is acceptable given the benefits at scale.

## Decision

Use a **GitHub App** to handle `/preview` commands and manage preview deployments.

When a `/preview` comment is posted on a pull request:
- The GitHub App receives the webhook event
- A preview environment is created
- A preview URL is posted back to the PR
- The environment is automatically torn down after 30 minutes

This approach better supports high PR volume, reduces operational risk, and removes friction for engineers delivering changes.

## Consequences

### Positive
- Scales to many concurrent preview environments
- Clear ownership of preview lifecycle management
- Easier cleanup and orphan detection
- Improved developer experience and faster feedback loops
- Extendable, a GitHub App allows future capabilities to more easily be incorporated.

### Negative
- Requires operating an additional service
- More initial setup compared to GitHub Actions
- Increased responsibility for security and credential management
