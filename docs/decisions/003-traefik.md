# Adopt Traefik as Preview Routing Layer (Instead of GKE Ingress Only)

Date: 2026-02-10

Status: accepted

## Context

- The system needs to provide fast, reliable preview URLs for pull requests, e.g. `preview-pr-123.pre.chaoticbee.com`.
- Initial implementation used **GKE Ingress (GCE load balancer)** per preview environment. This led to:
  - Slow provisioning and consolidation of load balancers (minutes+ before a URL worked).
  - DNS complexity when multiple ingresses ended up with different external IPs.
  - Operational friction debugging multi‑ingress URL map behavior and IP conflicts.
- Requirements for the preview routing layer:
  - **Low latency URL readiness** (seconds, not minutes).
  - **Support many concurrent previews** without creating many cloud LBs.
  - **Wildcard DNS support** for `*.pre.chaoticbee.com`.
  - **Kubernetes‑native configuration** that can be driven by Helm and the preview deployer.
- Traefik is a mature, Kubernetes‑native reverse proxy that can:
  - Watch Kubernetes Ingress resources across namespaces.
  - Route based on hostnames (e.g., `preview-pr-123.pre.chaoticbee.com`).
  - Run behind a **single** GCE load balancer / shared ingress, eliminating per‑preview LB churn.

## Decision

- **Adopt Traefik** as the internal HTTP reverse proxy and router for preview environments.
  - Deploy Traefik into a dedicated namespace `preview-proxy` using `helm-chart/traefik/traefik-deployment.yaml`.
  - Expose Traefik via a single shared GKE Ingress (`preview-shared-ingress`) and static IP, fronted by wildcard DNS `*.pre.chaoticbee.com`.
  - Configure Traefik with the Kubernetes Ingress provider:
    - `--providers.kubernetesingress=true`
    - `--providers.kubernetesingress.ingressClass=traefik`
    - Watch ingresses across namespaces.
  - Create an `IngressClass` named `traefik` and use `ingressClassName: traefik` on preview ingresses.
- **Preview application routing model:**
  - Each preview namespace (e.g., `preview-pr-123`) deploys the app via the `preview-environment` Helm chart.
  - The chart creates:
    - A `Service` (ClusterIP) exposing port 8080.
    - A per‑preview `Ingress` with:
      - `ingressClassName: traefik`
      - `host: preview-pr-123.pre.chaoticbee.com`
      - `path: /` routing to the preview service.
  - Traefik discovers these ingresses and routes traffic from the shared ingress → Traefik → preview service.
- **Helm / scripting implications:**
  - `helm-chart/values-preview.yaml`:
    - `ingress.enabled: true`
    - `ingress.className: "traefik"`
    - `ingress.hosts[0].host` set per‑preview (PR number).
  - `helm-chart/traefik/setup.sh`:
    - Creates the `traefik` `IngressClass`.
    - Applies the Traefik deployment, waits for readiness.
    - Ensures Traefik RBAC includes `endpointslices.discovery.k8s.io`.

## Alternatives Considered

- **A. Pure GKE Ingress per preview (no Traefik)**
  - Each preview Helm release creates its own GKE Ingress and external HTTP(S) load balancer.
  - Pros:
    - Uses “built‑in” GKE components only.
    - Simple mental model: one ingress per preview.
  - Cons:
    - **Slow URL readiness**: load balancer and URL map provisioning can take several minutes.
    - DNS issues when multiple ingresses compete for the same wildcard hostname / static IP.
    - Higher cloud resource churn and risk of orphaned LBs.
  - **Rejected** because it does not meet latency and scalability requirements for many previews.

- **B. Single shared GKE Ingress with dynamic backend rules (no Traefik)**
  - Maintain one ingress and programmatically mutate its rules (paths/hosts) for each preview.
  - Pros:
    - Single external LB and IP (good for DNS and cost).
    - Stays within GKE primitives.
  - Cons:
    - Complex, imperative management of ingress rules (risk of conflicts / race conditions).
    - URL map convergence and propagation are still slow; previews can take minutes to become reachable.
  - **Rejected** because it still relies on slow GCE URL map updates and adds orchestration complexity.

- **C. NGINX Ingress Controller**
  - Use NGINX instead of Traefik as a cluster‑internal reverse proxy.
  - Pros:
    - Very common, battle‑tested choice.
    - Rich configuration surface.
  - Cons:
    - For this use case, Traefik’s simpler configuration and built‑in dashboard are a better fit.
    - Would require similar setup work (IngressClass, RBAC, controller deployment) with no clear advantage.
  - **Not chosen** for now; Traefik’s DX and built‑in tooling are preferred.

- **D. API‑Gateway‑style external proxy (e.g., Cloud Run / API Gateway in front of GKE)**
  - Terminate requests at a separate managed gateway and proxy into the cluster.
  - Pros:
    - Offloads some concerns to a managed service.
  - Cons:
    - Adds another control plane and hop.
    - More complex wiring for per‑preview routing.
  - **Rejected** as over‑complex for a cluster‑local preview routing need.

## Consequences

- **Positive**
  - **Fast preview URL readiness**: once the preview pod is ready and the ingress is created, Traefik can route traffic in seconds (no additional LB provisioning delay).
  - **Single external IP and wildcard DNS**: all previews share a single GCE LB and IP via `preview-shared-ingress`, simplifying DNS (`*.pre.chaoticbee.com`) and reducing cost.
  - **Scales to many previews**: adding a preview becomes “just” another namespace + Service + Ingress; Traefik automatically discovers routes.
  - **Good observability**: Traefik dashboard and access logs make it easier to trace routing issues.
  - **Clear separation of concerns**: GKE Ingress handles north‑south entry into the cluster; Traefik handles intra‑cluster HTTP routing to previews.

- **Negative / Trade‑offs**
  - Additional component to operate (Traefik deployment, RBAC, upgrades).
  - Need to maintain Traefik‑specific configuration (IngressClass, arguments, RBAC for EndpointSlices).
  - Debugging now involves both GKE Ingress and Traefik when issues occur (two hops instead of one).

- **Future considerations**
  - If Kubernetes Gateway API becomes preferred in this cluster, we may revisit using Traefik’s Gateway API support or another Gateway controller.
  - If preview load or complexity grows significantly, we may introduce rate‑limiting, auth, or mTLS at the Traefik layer.

