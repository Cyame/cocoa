# Cocoa Artifacts

Build artifacts and Kubernetes deployment manifests for the Cocoa multi-agent control studio.

## Directory Structure

```
cocoa-artifacts/
├── docker/
│   ├── Dockerfile.instance-base      # Instance base image: Node host + pi + subagent extension
│   └── Dockerfile.instance-ancestor  # Thin layer over base: baked enabled subagent agents
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
| `Dockerfile.instance-base` | Builds `cocoa-instance-base:{engine-v}`: Node host + pinned pi CLI + vendored subagent extension (`~/.pi/agent/extensions/subagent/`). Agents dir kept empty — custom slugs fall back to this image + ConfigMap (v5.1 G9). |
| `Dockerfile.instance-ancestor` | Builds `cocoa-instance-{slug}:{engine-v}` for the 5 始祖: `FROM base` + thin layer baking only the slug's enabled agent `.md` files into `~/.pi/agent/agents/`. Enabled set resolved by `scripts/build-instance-images.sh` from `builtin_presets.py` (`subagent_strategy.enabled`). |
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

### Build the 1+5 Instance Images

The v5.1 instance image family is `cocoa-instance-base:{engine-v}` + one thin
layer per 始祖 (`cocoa-instance-{fox|beaver|sparrow|coyote|lion}:{engine-v}`).
`engine-v` = pi runtime version (from `cocoa-instance-host/package.json` pin);
enabled agent sets come from `cocoa-backend/app/core/builtin_presets.py`.

```bash
bash scripts/build-instance-images.sh            # build 1+5 locally (no push)
bash scripts/build-instance-images.sh --push     # build + push to registry (localhost:5000 default)
COCOA_INSTANCE_REGISTRY=localhost:5000 bash scripts/build-instance-images.sh --push
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
