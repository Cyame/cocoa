# Cocoa Artifacts

Build artifacts and Kubernetes deployment manifests for the Cocoa multi-agent control studio.

## Directory Structure

```
cocoa-artifacts/
├── docker/
│   └── Dockerfile.instance  # Instance runtime container image
├── k8s/
│   └── instance/
│       ├── deployment.yaml       # Deployment (1 replica, workspace PVC)
│       ├── configmap.yaml        # ConfigMap (RUNTIME_CONFIG, INSTANCE_ID)
│       ├── pvc.yaml              # PersistentVolumeClaim (1Gi workspace)
│       ├── service.yaml          # ClusterIP Service (port 8080)
│       ├── networkpolicy.yaml    # NetworkPolicy (Office-level ingress isolation)
│       └── kustomization.yaml    # Kustomize entrypoint
└── README.md
```

## Manifest Overview

| Manifest | Purpose |
|----------|---------|
| `Dockerfile.instance` | Builds the `cocoa-instance` image from `python:3.12-slim`. Copies the backend and runs `uv sync --frozen`. Entrypoint: `python -m app.agent_runtime` (module implemented in P8). |
| `deployment.yaml` | Single-replica Deployment per Instance. Mounts the workspace PVC at `/app/.pi/workspace`. Env vars from the per-instance ConfigMap. Requests: 100m CPU, 256Mi memory. |
| `configmap.yaml` | Injects `RUNTIME_CONFIG` (JSON from Instance DB record) and `INSTANCE_ID` into the container. Non-sensitive config only — secrets go to a separate Secret resource (not scaffolded in P7). |
| `pvc.yaml` | 1Gi `ReadWriteOnce` volume per Instance. Stores the agent workspace under `/app/.pi/workspace`. Each Instance gets its own PVC for filesystem isolation. |
| `service.yaml` | `ClusterIP` Service mapping port 8080. No external exposure — cocoa-backend communicates with Instances from within the cluster. |
| `networkpolicy.yaml` | Ingress-only NetworkPolicy. Only Pods carrying `office-id={office_id}` may connect to this Instance. Requires a CNI that enforces NetworkPolicy (Calico, Cilium, etc.). |
| `kustomization.yaml` | Groups all 5 YAML resources under a common `app: cocoa-instance` label. Apply with `kubectl apply -k`. |

## Template Variables

All YAML files in `k8s/instance/` use `{variable}` placeholders. A deploy script must substitute these before applying:

| Variable | Description | Example |
|----------|-------------|---------|
| `{instance_id}` | Unique Instance UUID (also used as Deployment/Service/ConfigMap/PVC name prefix) | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `{office_id}` | Office UUID — used on Pod labels and NetworkPolicy ingress selector | `f1e2d3c4-b5a6-7890-1234-567890abcdef` |

## Usage

### Build the Instance Image

```bash
docker build -t cocoa-instance:latest -f cocoa-artifacts/docker/Dockerfile.instance .
```

### Apply Manifests (after template substitution)

```bash
# Substitute template variables first (example with sed):
# sed -e "s/{instance_id}/a1b2c3d4-.../g" \
#     -e "s/{office_id}/f1e2d3c4-.../g" \
#     cocoa-artifacts/k8s/instance/*.yaml > /tmp/instance-rendered/
# Then apply:
kubectl apply -k cocoa-artifacts/k8s/instance/
```

### Delete an Instance

```bash
kubectl delete -k cocoa-artifacts/k8s/instance/
```

## Related

- [docs/runtime-system.md](../docs/runtime-system.md) — Instance lifecycle model and API reference
- [README.md](../README.md) — Project overview and status
- [AGENTS.md](../AGENTS.md) — Development conventions
