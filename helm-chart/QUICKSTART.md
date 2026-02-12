# Quick Start Guide

## Prerequisites

### Domain Setup (Required for External Access)

**Note:** You have two options:
1. **Deploy first, then configure DNS** (recommended for first-time setup): Deploy the application first to get the ingress IP, then configure DNS to point to that IP.
2. **Use a static IP** (recommended for production): Create a static IP first, configure DNS, then deploy with the static IP annotation.

Before deploying, you need to set up DNS for your preview environments.

#### Option 1: Wildcard Domain (Recommended for Preview Environments)

For preview environments, a wildcard domain is most convenient (e.g., `*.preview.yourdomain.com`):

1. **Get your GKE ingress IP address** (after first deployment):
   ```bash
   kubectl get ingress -n preview-demo -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}'
   ```
   Note: The IP may take 1-2 minutes to appear after creating the ingress.

2. **Create DNS A record** in your DNS provider:
   - **Type:** A
   - **Name:** `*` (wildcard) or `*.preview`
   - **Value:** The IP address from step 1
   - **TTL:** 300 (or your preference)

   Example DNS records:
   ```
   *.preview.yourdomain.com  A  <ingress-ip>
   ```

3. **Verify DNS propagation:**
   ```bash
   dig preview-demo.yourdomain.com
   # or
   nslookup preview-demo.yourdomain.com
   ```

#### Option 2: Static IP with Specific Domains

For production-like previews with specific domains:

1. **Create a static IP in GCP:**
   ```bash
   gcloud compute addresses create preview-static-ip \
     --global \
     --project=${PROJECT_ID}
   ```

2. **Get the IP address:**
   ```bash
   gcloud compute addresses describe preview-static-ip \
     --global \
     --project=${PROJECT_ID} \
     --format="value(address)"
   ```

3. **Create DNS A record:**
   - **Type:** A
   - **Name:** `preview-demo` (or your subdomain)
   - **Value:** The static IP from step 2
   - **TTL:** 300

4. **Update Helm values to use static IP:**
   ```yaml
   ingress:
     annotations:
       kubernetes.io/ingress.global-static-ip-name: "preview-static-ip"
   ```

#### Option 3: Using Google Cloud DNS (Recommended for Existing Domains)

If you have an existing domain (e.g., `yourhostname` from Namecheap) and want GCP to handle DNS:

> **📖 Detailed Guide:** See [`DNS-SETUP-NAMECHEAP.md`](./DNS-SETUP-NAMECHEAP.md) for a complete step-by-step guide with Namecheap-specific instructions.

**Option 3a: Use a Subdomain (Recommended)**

Use a subdomain like `preview.yourhostname` so you don't affect your main domain:

1. **Create a managed zone for the subdomain:**
   ```bash
   gcloud dns managed-zones create preview-chaoticbee-zone \
     --dns-name=preview.yourhostname \
     --description="Preview environments for yourhostname" \
     --project=${PROJECT_ID}
   ```

2. **Get the nameservers:**
   ```bash
   gcloud dns managed-zones describe preview-chaoticbee-zone \
     --project=${PROJECT_ID} \
     --format="value(nameServers)"
   ```
   
   You'll get output like:
   ```
   ns-cloud-a1.googledomains.com.
   ns-cloud-a2.googledomains.com.
   ns-cloud-a3.googledomains.com.
   ns-cloud-a4.googledomains.com.
   ```

3. **Update Namecheap to use these nameservers:**
   - Log in to Namecheap
   - Go to **Domain List** → Select **yourhostname** → Click **Manage**
   - Go to **Advanced DNS** tab
   - Scroll to **Nameservers** section
   - Select **Custom DNS**
   - Enter the 4 nameservers from step 2 (without the trailing dots in the UI)
   - Click **Save**
   - **Note:** DNS propagation can take 24-48 hours, but usually happens within a few hours

4. **Wait for DNS propagation** (verify nameservers are updated):
   ```bash
   dig NS preview.yourhostname
   # Should show the Google Cloud DNS nameservers
   ```

5. **Deploy your application first** to get the ingress IP:
   ```bash
   # Deploy (see Deploy with Helm section below)
   # Then get the IP
   INGRESS_IP=$(kubectl get ingress -n preview-demo -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')
   echo "Ingress IP: ${INGRESS_IP}"
   ```

6. **Create wildcard A record** for preview environments:
   ```bash
   gcloud dns record-sets create "*.preview.yourhostname" \
     --rrdatas=${INGRESS_IP} \
     --type=A \
     --ttl=300 \
     --zone=preview-chaoticbee-zone \
     --project=${PROJECT_ID}
   ```

7. **Verify the DNS record:**
   ```bash
   gcloud dns record-sets list \
     --zone=preview-chaoticbee-zone \
     --project=${PROJECT_ID}
   
   # Test DNS resolution
   dig preview-demo.preview.yourhostname
   ```

**Option 3b: Use Root Domain (Advanced)**

If you want to use the root domain `yourhostname` directly:

1. **Create a managed zone for the root domain:**
   ```bash
   gcloud dns managed-zones create chaoticbee-zone \
     --dns-name=yourhostname \
     --description="DNS zone for yourhostname" \
     --project=${PROJECT_ID}
   ```

2. **Get the nameservers and update Namecheap** (same as Option 3a, steps 2-3)

3. **Important:** Before switching nameservers, export your existing DNS records from Namecheap:
   - In Namecheap, go to **Advanced DNS** tab
   - Note down all existing A, CNAME, MX, TXT records
   - You'll need to recreate important ones (like MX for email) in Google Cloud DNS

4. **Recreate essential DNS records** in Google Cloud DNS:
   ```bash
   # Example: If you had an A record for www
   gcloud dns record-sets create "www.yourhostname" \
     --rrdatas=<your-existing-ip> \
     --type=A \
     --ttl=300 \
     --zone=chaoticbee-zone \
     --project=${PROJECT_ID}
   
   # Example: If you had MX records for email
   gcloud dns record-sets create "yourhostname" \
     --rrdatas="10 mail.example.com." \
     --type=MX \
     --ttl=300 \
     --zone=chaoticbee-zone \
     --project=${PROJECT_ID}
   ```

5. **Create preview subdomain records** after deployment:
   ```bash
   INGRESS_IP=$(kubectl get ingress -n preview-demo -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')
   
   gcloud dns record-sets create "*.preview.yourhostname" \
     --rrdatas=${INGRESS_IP} \
     --type=A \
     --ttl=300 \
     --zone=chaoticbee-zone \
     --project=${PROJECT_ID}
   ```

**Recommendation:** Use Option 3a (subdomain) to avoid affecting your main domain's DNS.

### SSL/TLS Certificate Setup (Optional but Recommended)

#### Using Google-Managed SSL Certificate

1. **Create a managed certificate:**
   ```bash
   kubectl apply -f - <<EOF
   apiVersion: networking.gke.io/v1
   kind: ManagedCertificate
   metadata:
     name: preview-cert
     namespace: preview-demo
   spec:
     domains:
       - "*.preview.yourhostname"  # Wildcard for all previews (recommended)
       # Or specific domains:
       # - preview-demo.preview.yourhostname
       # - preview-pr-123.preview.yourhostname
   EOF
   ```

2. **Update Helm values to use the certificate:**
   ```yaml
   ingress:
     annotations:
       networking.gke.io/managed-certificates: "preview-cert"
   ```

3. **Wait for certificate provisioning** (can take 10-60 minutes):
   ```bash
   kubectl describe managedcertificate preview-cert -n preview-demo
   ```

#### Using Let's Encrypt (with cert-manager)

If using cert-manager instead:

1. **Install cert-manager** (if not already installed):
   ```bash
   kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
   ```

2. **Create ClusterIssuer:**
   ```bash
   kubectl apply -f - <<EOF
   apiVersion: cert-manager.io/v1
   kind: ClusterIssuer
   metadata:
     name: letsencrypt-prod
   spec:
     acme:
       server: https://acme-v02.api.letsencrypt.org/directory
       email: your-email@example.com
       privateKeySecretRef:
         name: letsencrypt-prod
       solvers:
       - http01:
           ingress:
             class: gce
   EOF
   ```

3. **Update Helm values:**
   ```yaml
   ingress:
     annotations:
       cert-manager.io/cluster-issuer: "letsencrypt-prod"
     tls:
       - secretName: preview-tls
         hosts:
           - preview-demo.yourdomain.com
   ```

---

## Prerequisites

1. enable google artifact registry and create docker repo

  ```bash 
    gcloud services enable artifactregistry.googleapis.com --project=${PROJECT_ID} 
  
    gcloud artifacts repositories create docker-repo \
        --project=${PROJECT_ID}
        --repository-format=docker
        --location=${REGION}
  ```

2. Authenticate docker 

   ```bash 
    gcloud auth configure-docker us-central1-docker.pkg.dev
   ```

3. Build & tag 

    ```bash
    cd src/helloworld
    docker build -t us-central1-docker.pkg.dev/${PROJECT_ID}/docker-repo/helloworld:latest .
    ```

4. Push

   ```bash
   docker push us-central1-docker.pkg.dev/${PROJECT_ID}/docker-repo/helloworld:latest
   ```


5. **Configure kubectl for your GKE cluster:**
   ```bash
   gcloud container clusters get-credentials --project=${PROJECT_ID} your_cluter_name --zone ${REGION}
   ```

## Deploy with Helm

### Basic Deployment

```bash
cd helm-chart

helm install preview-release . \
  --namespace preview-demo \
  --create-namespace \
  --set image.repository=us-central1-docker.pkg.dev/${PROJECT_ID}/docker-repo/helloworld \
  --set image.tag=latest \
  --set ingress.hosts[0].host=preview-demo.pre.yourhostname \
  --set ingress.hosts[0].paths[0].path=/ \
  --set ingress.hosts[0].paths[0].pathType=Prefix
```

### For Preview Environments (PR-based)

**Option 1: Using a values file (Recommended)**

1. **Copy and customize the preview values file:**
   ```bash
   cp values-preview.yaml values-pr-123.yaml
   ```

2. **Edit `values-pr-123.yaml`** with your specific values:
   ```yaml
   image:
     repository: us-central1-docker.pkg.dev/${PROJECT_ID}/docker-repo/helloworld
     tag: "pr-123-abc123"  # PR number and commit SHA
   
   ingress:
     hosts:
       - host: preview-pr-123.pre.yourhostname  # Your preview hostname
   
   env:
     - name: PR_NUMBER
       value: "123"
     - name: COMMIT_SHA
       value: "abc123"
   ```

3. **Deploy using the values file:**
   ```bash
   helm install preview-pr-123 . \
     --namespace preview-pr-123 \
     --create-namespace \
     -f values-pr-123.yaml
   ```

**Option 2: Using command-line flags (Quick testing)**

```bash
helm install preview-pr-123 . \
  --namespace preview-pr-123 \
  --create-namespace \
  --set image.repository=us-central1-docker.pkg.dev/${PROJECT_ID}/docker-repo/helloworld \
  --set image.tag=pr-123-abc123 \
  --set ingress.hosts[0].host=preview-pr-123.pre.yourhostname \
  --set ingress.hosts[0].paths[0].path=/ \
  --set ingress.hosts[0].paths[0].pathType=Prefix \
  --set ingress.className=gce \
  --set ingress.annotations."kubernetes\.io/ingress\.class"=gce
```

**Note:** The values file approach is recommended for consistency and easier management of multiple preview environments.

### Using Values File
  
   
```bash
# Copy and edit the example
cp values-preview-example.yaml my-preview-values.yaml
# Edit my-preview-values.yaml with your settings

helm install preview-release . \
  --namespace preview-demo \
  --create-namespace \
  -f my-preview-values.yaml
```

## Verify Deployment

```bash
# Check pods
kubectl get pods -n preview-demo

# Check service
kubectl get svc -n preview-demo

# Check ingress
kubectl get ingress -n preview-demo

# Get the URL
kubectl get ingress -n preview-demo -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}'
```

## Access the Application

Once the ingress has an IP address (may take 1-2 minutes for GKE), access via:

```bash
# Get the hostname from ingress
kubectl get ingress -n preview-demo -o jsonpath='{.items[0].spec.rules[0].host}'

# Or use the NOTES output
helm status preview-release -n preview-demo
```

## Cleanup

```bash
# Uninstall the Helm release (specify namespace)
helm uninstall preview-release -n preview-demo

# Or if you want to delete the namespace and everything in it
kubectl delete namespace preview-demo
```

**Note:** Always specify the namespace with `-n` or `--namespace` when uninstalling, as Helm defaults to the `default` namespace.

## GKE-Specific Notes

### Using Static IP

1. Create a static IP in GCP:
   ```bash
   gcloud compute addresses create preview-static-ip --global
   ```

2. Update values:
   ```yaml
   ingress:
     annotations:
       kubernetes.io/ingress.global-static-ip-name: "preview-static-ip"
   ```

### Using Google-Managed SSL Certificate

1. Create managed certificate:
   ```bash
   kubectl apply -f - <<EOF
   apiVersion: networking.gke.io/v1
   kind: ManagedCertificate
   metadata:
     name: preview-cert
     namespace: preview-demo
   spec:
     domains:
       - preview-pr-123.yourdomain.com
   EOF
   ```

2. Update ingress annotations:
   ```yaml
   ingress:
     annotations:
       networking.gke.io/managed-certificates: "preview-cert"
   ```

### DNS Configuration

See the **Domain Setup** section at the beginning of this guide for detailed DNS configuration instructions, including:
- Wildcard domain setup (recommended for preview environments)
- Static IP configuration
- Google Cloud DNS setup
- DNS verification steps

Quick reference:
1. Get the ingress IP: `kubectl get ingress -n preview-demo -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}'`
2. Create an A record in your DNS pointing to that IP (or use wildcard `*.preview.yourdomain.com`)
3. Wait for DNS propagation (can take a few minutes to hours depending on TTL)
4. Verify: `dig preview-demo.yourdomain.com` or `nslookup preview-demo.yourdomain.com`
