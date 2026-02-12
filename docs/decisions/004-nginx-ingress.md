# Adopt NGINX Ingress Controller for Preview Routing

Date: 2026-02-10

Status: accepted, supersedes [003](003-traefik.md)

## Context

- Goal: provide **fast, reliable preview URLs** for PRs, such as `preview-pr-123.pre.chaoticbee.com`.
- Initial attempts:
  - **GKE Ingress per preview**:
    - Each preview created its own GCE HTTP(S) load balancer.
    - Resulted in slow URL readiness (minutes), multiple external IPs, and brittle URL map behavior.
  - **Traefik-based design**:
    - Introduced an internal Traefik proxy behind a shared GKE ingress.
    - While powerful, it added operational complexity (custom RBAC, EndpointSlice permissions, controller flags) and a second routing layer to debug.
- Requirements refined from experience:
  - Minimize moving parts: fewer custom components to tune and debug.
  - Use **standard Kubernetes ingress patterns** where possible.
  - Keep the model simple for contributors: “one preview = namespace + Service + Ingress”.
  - Retain **single external IP + wildcard DNS** to avoid the earlier multi-IP DNS issues.

## Decision

- **Adopt NGINX Ingress Controller** as the cluster’s preview routing layer instead of Traefik.
  - Deploy the official-style NGINX controller into its own namespace `ingress-nginx` via `helm-chart/nginx/nginx-ingress.yaml`, which defines:
    - `Namespace`, `ServiceAccount`, `ClusterRole`, `ClusterRoleBinding`.
    - `Deployment` `ingress-nginx-controller` with `controller-class=k8s.io/ingress-nginx` and `ingress-class=nginx`.
    - `Service` `ingress-nginx-controller` of type `LoadBalancer` (single external IP).
    - `IngressClass` named `nginx`.
- **Preview routing model:**
  - Each preview namespace (e.g., `preview-pr-123`) is deployed with the existing `preview-environment` Helm chart.
  - The chart creates:
    - A `Service` (ClusterIP) exposing port 8080.
    - An `Ingress` with:
      - `ingress.className: "nginx"`.
      - `host: preview-pr-123.pre.chaoticbee.com`.
      - `path: /` routing to the preview Service.
  - The NGINX ingress controller:
    - Watches `Ingress` objects with `ingressClassName: nginx` across namespaces.
    - Routes requests from the external LB → NGINX → preview Service → pod.
- **Configuration changes in this repo:**
  - `helm-chart/nginx/nginx-ingress.yaml`:
    - Manifests for NGINX ingress controller, RBAC, Service, and `IngressClass`.
  - `helm-chart/values-preview.yaml`:
    - `ingress.enabled: true`.
    - `ingress.className: "nginx"`.
    - `ingress.hosts[0].host` parameterized per preview (PR number).
    - Traefik-specific service annotations removed.
  - Traefik-related files remain for now but are no longer part of the recommended path and can be removed in a future cleanup.

## Alternatives Considered

- **A. Continue with Traefik (003-traefik)**
  - Pros:
    - Rich feature set and dashboard.
    - Flexible routing and middlewares.
  - Cons:
    - Introduced an extra hop and configuration surface on top of GKE’s own ingress.
    - Required custom RBAC for EndpointSlices, explicit provider flags, and additional debugging to understand why routes were/weren’t discovered.
    - For this project, most of Traefik’s advanced features were unused; the complexity cost outweighed the benefit.
  - **Superseded** by this decision; NGINX ingress provides what we need with a more “standard” setup.

- **B. Pure GKE Ingress per preview (no internal controller)**
  - Pros:
    - Uses only GKE-native components.
    - Conceptually simple.
  - Cons:
    - Slow load balancer provisioning and URL map propagation.
    - Difficult to manage many previews concurrently without LB sprawl and DNS complications.
  - **Rejected** for the same reasons as in 003: does not meet latency or scale requirements.

- **C. Shared GKE Ingress with programmatic rule mutation**
  - Pros:
    - Single external IP; works with wildcard DNS.
  - Cons:
    - Requires imperative updates to ingress rules for every preview create/delete.
    - Still subject to GCE URL map propagation delays.
  - **Rejected** as unnecessarily complex compared to a standard ingress controller.

- **D. API Gateway / external proxy in front of GKE**
  - Pros:
    - Offloads some responsibilities to a managed service.
  - Cons:
    - Adds another control plane and hop.
    - Overkill for cluster-local preview routing.
  - **Rejected** for this iteration.

## Consequences

- **Positive**
  - **Simplicity & familiarity**: NGINX ingress is a widely used, well-documented default in many K8s environments; operators and contributors are more likely to know it.
  - **Single external IP with wildcard DNS**: all previews share the `ingress-nginx-controller` Service IP, making DNS straightforward (`*.pre.chaoticbee.com`).
  - **Fast preview URL readiness**:
    - Once the pod is ready and the `Ingress` is created, NGINX discovers and routes to it quickly.
  - **Kubernetes-native workflow**:
    - “One namespace + Service + Ingress per preview” aligns with standard ingress patterns; no controller-specific annotations are required in `Service`.

- **Negative / Trade-offs**
  - Still operating a controller (NGINX) in the cluster: needs upgrades, monitoring, and debugging when things go wrong.
  - Slightly more work if later we want to adopt Gateway API or another controller; we’ll need another migration.
  - Existing Traefik artifacts are now legacy and should be cleaned up over time to avoid confusion.

- **Follow-ups**
  - Deprecate Traefik docs and mark 003-traefik as superseded by 004-nginx-ingress.
  - Update `helm-chart/QUICKSTART.md` and related docs to point to NGINX as the recommended path.
  - Optionally add TLS (managed certs) on top of NGINX once the HTTP path is stable.

