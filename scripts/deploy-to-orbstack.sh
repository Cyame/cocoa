#!/usr/bin/env bash
# Cocoa one-click deploy/update to orbstack K8s cluster.
#
# This script is IDEMPOTENT: re-running it updates resources in place.
# It applies the PostgreSQL, backend, and portal manifests, reconciles the
# two Secrets, waits for readiness, runs Alembic, and prints final status.
#
# USAGE:
#   ./scripts/deploy-to-orbstack.sh           # full deploy
#   ./scripts/deploy-to-orbstack.sh --status  # only show current state
#   ./scripts/deploy-to-orbstack.sh --logs    # tail recent backend logs
#
# EXIT CODES:
#   0 = success; 1 = orbstack/tooling unreachable; 2 = images missing
#   3 = pods not Ready within timeout; 4 = alembic failed
#
# See `.omo/evidence/orbstack-operations.md` for operational conventions.

set -euo pipefail

NS="cocoa"
KUBECTL_TIMEOUT="${KUBECTL_TIMEOUT:-180}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST_DIR="$ROOT_DIR/cocoa-artifacts/k8s"
MODE="deploy"

log() { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[deploy]\033[0m %s\n' "$*" >&2; }
ok() { printf '\033[1;32m[deploy]\033[0m %s\n' "$*"; }
usage() { sed -n '2,21p' "$0"; exit 0; }

case "${1:-deploy}" in
  --help|-h) usage ;;
  --status) MODE="status" ;;
  --logs) MODE="logs" ;;
  deploy|"") MODE="deploy" ;;
  *) err "Unknown option: $1"; usage >&2; exit 1 ;;
esac

require_command() {
  command -v "$1" >/dev/null 2>&1 || { err "$1 not found"; exit 1; }
}

require_command kubectl

CURRENT_CONTEXT="$(kubectl config current-context 2>/dev/null || printf 'none')"
log "K8s context: $CURRENT_CONTEXT"
if [[ "$CURRENT_CONTEXT" != "orbstack" ]]; then
  case "$CURRENT_CONTEXT" in
    *k3d*|*minikube*|*kind*) ;;
    *)
      err "Unexpected K8s context '$CURRENT_CONTEXT'; switch to orbstack first:"
      err "  kubectl config use-context orbstack"
      exit 1
      ;;
  esac
fi

if ! kubectl cluster-info >/dev/null 2>&1; then
  err "Kubernetes cluster is unreachable; start OrbStack Kubernetes first"
  exit 1
fi

show_status() {
  printf '%s\n' '=== pods ==='
  kubectl get pods -n "$NS" 2>/dev/null || true
  printf '%s\n' '=== services ==='
  kubectl get svc -n "$NS" 2>/dev/null || true
  printf '%s\n' '=== recent backend events ==='
  kubectl get events -n "$NS" --sort-by='.lastTimestamp' 2>/dev/null | tail -10 || true
}

if [[ "$MODE" == "status" ]]; then
  show_status
  exit 0
fi

if [[ "$MODE" == "logs" ]]; then
  POD="$(kubectl get pod -l app=cocoa-backend -n "$NS" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
  [[ -n "$POD" ]] || { err "No backend pod found in namespace $NS"; exit 1; }
  kubectl logs -n "$NS" "$POD" --tail=200 --since=1h
  exit 0
fi

require_command docker
MISSING=()
for image in cocoa-backend:latest cocoa-instance:latest cocoa-portal:latest; do
  if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -qx "$image"; then
    MISSING+=("$image")
  fi
done
if (( ${#MISSING[@]} > 0 )); then
  err "Missing Docker images: ${MISSING[*]}"
  err "Build them locally before deploying, for example: docker build -t cocoa-backend:latest ..."
  exit 2
fi
ok "All required Cocoa images are present locally"

log "Ensuring namespace $NS exists"
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

log "Applying PostgreSQL manifest"
kubectl apply -f "$MANIFEST_DIR/postgresql-deployment.yaml"

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-devpassword}"
POSTGRES_DB="${POSTGRES_DB:-cocoa_dev}"
DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://postgres:devpassword@cocoa-postgres:5432/cocoa_dev}"
JWT_SECRET="${JWT_SECRET:-dev-secret-not-for-production-32-chars-min-OK}"
ENCRYPTION_KEY="${ENCRYPTION_KEY:-dev-encrypt-key-32-bytes-long-AAA}"
COCOA_K8S_DISABLED="${COCOA_K8S_DISABLED:-false}"
COCOA_INSTANCE_IMAGE_PULL_POLICY="${COCOA_INSTANCE_IMAGE_PULL_POLICY:-Never}"
# Stable internal token for instance pods ↔ backend /api/v1/internal/*.
# Reuse the live secret value when present so redeploys do not rotate it.
EXISTING_API_TOKEN="$(
  kubectl get secret cocoa-backend-secrets -n "$NS" \
    -o jsonpath='{.data.COCOA_API_TOKEN}' 2>/dev/null | base64 -d 2>/dev/null || true
)"
COCOA_API_TOKEN="${COCOA_API_TOKEN:-${EXISTING_API_TOKEN:-$(openssl rand -base64 32)}}"

apply_secret() {
  local name="$1"; shift
  kubectl create secret generic "$name" -n "$NS" "$@" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  ok "Reconciled Secret $name (values are never printed)"
}

log "Ensuring deployment Secrets"
apply_secret cocoa-postgres-secret \
  --from-literal=POSTGRES_USER="$POSTGRES_USER" \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  --from-literal=POSTGRES_DB="$POSTGRES_DB"

log "Waiting for PostgreSQL"
kubectl wait --for=condition=ready pod -l app=cocoa-postgres -n "$NS" --timeout="${KUBECTL_TIMEOUT}s" || {
  err "PostgreSQL pod was not Ready within ${KUBECTL_TIMEOUT}s"; exit 3;
}

POSTGRES_POD="$(kubectl get pod -l app=cocoa-postgres -n "$NS" -o jsonpath='{.items[0].metadata.name}')"
# The manifest's PVC may already be initialized with another database name.
# Create the configured database if it is absent; this is safe to repeat.
# NB: capture the full psql output first (no pipe into grep -q), because
# grep -q exits on the first match and SIGPIPEs psql, which under
# `set -o pipefail` makes the pipeline non-zero and spuriously triggers
# createdb even when the database already exists.
DB_PRESENT="$(kubectl exec -n "$NS" "$POSTGRES_POD" -- psql -U "$POSTGRES_USER" -d postgres \
  -v ON_ERROR_STOP=1 -tAc "SELECT 1 FROM pg_database WHERE datname = '$POSTGRES_DB'")"
if [[ "$DB_PRESENT" != "1" ]]; then
  kubectl exec -n "$NS" "$POSTGRES_POD" -- createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
fi

apply_secret cocoa-backend-secrets \
  --from-literal=DATABASE_URL="$DATABASE_URL" \
  --from-literal=JWT_SECRET="$JWT_SECRET" \
  --from-literal=ENCRYPTION_KEY="$ENCRYPTION_KEY" \
  --from-literal=COCOA_K8S_DISABLED="$COCOA_K8S_DISABLED" \
  --from-literal=COCOA_INSTANCE_IMAGE_PULL_POLICY="$COCOA_INSTANCE_IMAGE_PULL_POLICY" \
  --from-literal=COCOA_API_TOKEN="$COCOA_API_TOKEN"

log "Applying backend RBAC + backend and portal manifests"
kubectl apply -f "$MANIFEST_DIR/backend-rbac.yaml"
kubectl apply -f "$MANIFEST_DIR/backend-deployment.yaml"
kubectl apply -f "$MANIFEST_DIR/portal-deployment.yaml"

# The image tag is fixed at `latest`, so `kubectl apply` does NOT create a new
# pod when the image was rebuilt with the same tag. Force a rollout so alembic
# and the smoke check always run against the NEW code, never the stale pod.
log "Forcing rollout of rebuilt image (fixed latest tag)"
kubectl rollout restart deployment/cocoa-backend -n "$NS"
kubectl rollout restart deployment/cocoa-portal -n "$NS"

log "Waiting for backend rollout (timeout ${KUBECTL_TIMEOUT}s)"
kubectl rollout status deployment/cocoa-backend -n "$NS" --timeout="${KUBECTL_TIMEOUT}s" || {
  err "Backend pod was not Ready within ${KUBECTL_TIMEOUT}s"; exit 3;
}
log "Waiting for portal rollout (timeout ${KUBECTL_TIMEOUT}s)"
kubectl rollout status deployment/cocoa-portal -n "$NS" --timeout="${KUBECTL_TIMEOUT}s" || {
  err "Portal pod was not Ready within ${KUBECTL_TIMEOUT}s"; exit 3;
}

log "Running alembic upgrade head"
# Re-fetch the pod name AFTER the rollout so it points at the NEW pod.
BACKEND_POD="$(kubectl get pod -l app=cocoa-backend -n "$NS" -o jsonpath='{.items[0].metadata.name}')"
ALEMBIC_OK=0
for attempt in 1 2 3; do
  if kubectl exec -n "$NS" "$BACKEND_POD" -- uv run alembic upgrade head; then
    ALEMBIC_OK=1
    break
  fi
  err "Alembic migration failed (attempt $attempt/3); retrying in 5s"
  sleep 5
  # The pod may have been replaced mid-retry; re-resolve the current name.
  BACKEND_POD="$(kubectl get pod -l app=cocoa-backend -n "$NS" -o jsonpath='{.items[0].metadata.name}')"
done
if (( ALEMBIC_OK != 1 )); then
  err "Alembic migration failed after 3 attempts"
  exit 4
fi

log "Running backend /health smoke check"
kubectl exec -n "$NS" "$BACKEND_POD" -- python -c \
  'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:4510/health", timeout=10).read().decode())'

printf '\n'
show_status
printf '%s\n' '=== secrets (names only) ==='
kubectl get secrets -n "$NS"
printf '\n'
ok "Deploy complete. Namespace $NS remains running for inspection."
printf '%s\n' "Tip: $0 --status | $0 --logs"
