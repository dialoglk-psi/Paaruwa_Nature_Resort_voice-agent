# Deploying Paaruwa Nature Resort Agent to TKE

Target cluster: **AI nprod** (ap-singapore, K8s 1.34.1, node type SA5.LARGE8 only).

## Security warning

The `Dockerfile` copies `gcp-credentials.json` directly into the image at build
time. This is acceptable for this nprod deployment, but it means anyone with
pull access to the TCR image can extract the service account key. For
production, replace this with a Kubernetes Secret mounted as a file (e.g. via
a `gcp-credentials` Secret and a volume mount at `/app/gcp-credentials.json`)
instead of baking it into the image, and remove it from the Dockerfile/image
layers.

## Step 1: Create the TCR namespace

In the Tencent Cloud console, go to **Container Registry (TCR) → Namespaces**
and create a namespace named `paaruwa-agent` under your registry instance
(`ccr.ccs.tencentyun.com`).

## Step 2: Docker login to TCR

```bash
docker login ccr.ccs.tencentyun.com --username YOUR_ACCOUNT_ID
```

Enter your TCR password/access token when prompted.

## Step 3: Build and push the image

From the project root:

```bash
chmod +x build-and-push.sh
./build-and-push.sh
```

This builds and pushes `ccr.ccs.tencentyun.com/paaruwa-agent/paaruwa-resort-agent:v1`.

## Step 4: Get kubeconfig for the TKE cluster

In the Tencent Cloud console: **TKE → Cluster "AI nprod" → Basic Info → API
Server** and download/copy the kubeconfig. Save it as `~/.kube/config` or set:

```bash
export KUBECONFIG=/path/to/tke-kubeconfig.yaml
```

## Step 5: Create the namespace in the cluster

```bash
kubectl create namespace paaruwa-agent
```

(`deploy-tke.yaml` also declares this namespace, so this step is optional if
you apply it first — but it's listed here in case you want to create secrets
before applying the deployment.)

## Step 6: Create the TCR image pull secret

```bash
kubectl create secret docker-registry tcr-secret \
  --namespace=paaruwa-agent \
  --docker-server=ccr.ccs.tencentyun.com \
  --docker-username=YOUR_ACCOUNT_ID \
  --docker-password=YOUR_TCR_PASSWORD
```

## Step 7: Fill in and apply the app secret

Edit `secret-template.yaml` and replace every `REPLACE_ME` placeholder with
the real values from your `.env` file. Then apply it:

```bash
kubectl apply -f secret-template.yaml
```

Do not commit the filled-in version of this file to git.

## Step 8: Apply the deployment

```bash
kubectl apply -f deploy-tke.yaml
```

This creates the `paaruwa-agent` namespace (if not already present), the
`paaruwa-resort-agent` Deployment, and its HorizontalPodAutoscaler.

## Step 9: Watch the pod come up

```bash
kubectl get pods -n paaruwa-agent -w
```

## Step 10: Check logs

```bash
kubectl logs -n paaruwa-agent deployment/paaruwa-resort-agent --tail=50
```

## Notes

- No public IP / LoadBalancer is used — the agent only makes outbound
  connections to LiveKit Cloud, so no ingress or external service is needed.
  Ensure the cluster's NAT gateway allows outbound HTTPS/WSS traffic.
- Resource requests/limits (`500m`/`1Gi` requests, `2`/`4Gi` limits) are sized
  to fit comfortably on a single SA5.LARGE8 node (4 vCPU / 8 GB), leaving
  headroom for a second replica or other pods.
- `terminationGracePeriodSeconds: 900` gives an active call up to 15 minutes
  to finish before the pod is killed during a rollout or scale-down.
