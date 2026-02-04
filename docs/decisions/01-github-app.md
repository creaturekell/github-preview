# GitHub App

Date: 2026-02-04 

Status: accepted

## Context 

Before a developer deploys something to production, having a preview URL turns "I think this works" into "anyone can see this works" will help avoid anything risky hitting production. 

The developer should be able to issue a /deploy comment to trigger the workflow to deploy and get a url. 

Initially, github actions seemed like the best approach:
- Simple setup (.github/workflows/<yaml files>)
- No separate service to deploy
- Built into Github

But drawbacks include workflows being limited by GitHub's concurrency limits and orphaned containers would have be handled by another GitHub actions jobs, which makes this option a bit messy.

The alternate approach, using a GitHub App, could integrate with GitHub via API and listens to GitHub webhooks and takes action when /deploy command is issued.

Pros include:
1) The app could run continously and handle much more load than GitHub Actions as it is deployed independently. 
2) It can also handle more complex logic and state management
3) Handling cleanup and managing orphan detection is easir. 

The downside is that is requires more setup and complexity, but benefits outweigh this aspect. 

## Decision

Decided to use GitHub Apps to support /deploy to execute a preview-url.  This would deploy to a preview environment and be torn down after 30 minutes.   Additionally, it better support scalability of lots of PRs, removing the barrier for engineers to deliver. 

## Consequences 









Deploying a web application to production on a regular basis requ


Initially, I proposed github actions that would essentailly react to a comment when /deploy is used.  