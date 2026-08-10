#!/usr/bin/env bash
# Build the v5.1 "1+5" instance image family (see .omo/plans/v5-1-definition.md N2):
#   cocoa-instance-base:{engine-v}                 Node host + pi + subagent extension
#   cocoa-instance-{slug}:{engine-v}  (5 始祖)      thin layer: enabled agents baked
#
# Single sources of truth:
#   - engine-v: cocoa-instance-host/package.json pin of @earendil-works/pi-coding-agent
#   - enabled agent set per slug: cocoa-backend/app/core/builtin_presets.py
#     (manifest.subagent_strategy.enabled) — no hardcoded copy here.
#
# USAGE:
#   ./scripts/build-instance-images.sh          # build only (no push)
#   ./scripts/build-instance-images.sh --push   # build + push + registry check
#
# ENV:
#   COCOA_INSTANCE_REGISTRY   registry prefix (default localhost:5000)
#
# Idempotent: always rebuilds + (with --push) overwrites existing tags.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENTS_SRC="$ROOT_DIR/cocoa-instance-host/subagents/agents"
PRESETS_PY="$ROOT_DIR/cocoa-backend/app/core/builtin_presets.py"
PACKAGE_JSON="$ROOT_DIR/cocoa-instance-host/package.json"
DOCKER_DIR="$ROOT_DIR/cocoa-artifacts/docker"

REGISTRY="${COCOA_INSTANCE_REGISTRY:-localhost:5000}"
MODE="build"

log() { printf '[build-instance-images] %s\n' "$*"; }
err() { printf '[build-instance-images] ERROR: %s\n' "$*" >&2; }

case "${1:-build}" in
  build|"") MODE="build" ;;
  --push|-p) MODE="push" ;;
  --help|-h) sed -n '2,16p' "$0"; exit 0 ;;
  *) err "Unknown option: $1"; sed -n '2,16p' "$0" >&2; exit 1 ;;
esac

command -v docker >/dev/null 2>&1 || { err "docker not found"; exit 1; }

# --- engine-v: pi package pin (single source of truth) ---------------------
ENGINE_V="$(python3 -c '
import json, sys
with open(sys.argv[1]) as f:
    pkg = json.load(f)
pin = pkg.get("dependencies", {}).get("@earendil-works/pi-coding-agent", "")
if not pin:
    sys.exit("package.json has no @earendil-works/pi-coding-agent pin")
print(pin)
' "$PACKAGE_JSON")"

# Drift guard: bump deliberately when the pi pin changes.
if [[ "$ENGINE_V" != "0.83.0" ]]; then
  err "engine-v ${ENGINE_V} != 0.83.0 pin assertion; update this guard (and the"
  err "ENGINE_V default in Dockerfile.instance-ancestor) when pi upgrades"
  exit 1
fi
log "engine-v = ${ENGINE_V} (pi package pin)"

# --- enabled sets: builtin_presets.py (single source of truth) -------------
# Emit "slug<TAB>enabled1 enabled2 ..." per 始祖 (every preset carrying
# subagent_strategy). Fails loudly if T2-style manifest blocks are missing.
SNAPSHOT="$(cd "$ROOT_DIR" && python3 -c '
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "cocoa-backend"))
from app.core.builtin_presets import BUILTIN_PRESETS
rows = []
for p in BUILTIN_PRESETS:
    manifest = p.get("manifest") or {}
    strategy = manifest.get("subagent_strategy")
    if strategy is None:
        continue
    enabled = strategy.get("enabled") or []
    if not enabled:
        sys.exit("subagent_strategy.enabled empty for slug " + p["slug"])
    rows.append(p["slug"] + "\t" + " ".join(enabled))
if not rows:
    sys.exit("no builtin preset carries subagent_strategy (v5.1 T2 not landed?)")
print("\n".join(rows))
')"

declare -a SLUGS=() ENABLED_SETS=()
while IFS=$'\t' read -r slug enabled; do
  SLUGS+=("$slug")
  ENABLED_SETS+=("$enabled")
done <<< "$SNAPSHOT"
log "ancestors: ${#SLUGS[@]} (${SLUGS[*]})"

# --- validate: every enabled capability id has an agent .md on disk ---------
for enabled in "${ENABLED_SETS[@]}"; do
  for name in $enabled; do
    if [[ ! -f "$AGENTS_SRC/$name.md" ]]; then
      err "enabled capability '$name' has no agent file at $AGENTS_SRC/$name.md"
      exit 1
    fi
  done
done

# --- build ------------------------------------------------------------------
BASE_IMAGE="${REGISTRY}/cocoa-instance-base:${ENGINE_V}"
log "build ${BASE_IMAGE}"
docker build -f "$DOCKER_DIR/Dockerfile.instance-base" -t "$BASE_IMAGE" "$ROOT_DIR"

# Local alias so BuildKit resolves `FROM cocoa-instance-base:{engine-v}` in
# Dockerfile.instance-ancestor against the local store (no registry needed).
docker tag "$BASE_IMAGE" "cocoa-instance-base:${ENGINE_V}"

ANCESTOR_IMAGES=()
for i in "${!SLUGS[@]}"; do
  slug="${SLUGS[$i]}"
  enabled="${ENABLED_SETS[$i]}"
  image="${REGISTRY}/cocoa-instance-${slug}:${ENGINE_V}"
  ANCESTOR_IMAGES+=("$image")
  log "build ${image} (enabled: ${enabled})"
  docker build -f "$DOCKER_DIR/Dockerfile.instance-ancestor" \
    --build-arg "ENGINE_V=${ENGINE_V}" \
    --build-arg "SLUG=${slug}" \
    --build-arg "ENABLED_AGENTS=${enabled}" \
    -t "$image" \
    "$ROOT_DIR"
done

# --- embedded verification: images exist + baked agents match the set -------
missing=0
for image in "$BASE_IMAGE" "${ANCESTOR_IMAGES[@]}"; do
  docker image inspect "$image" >/dev/null 2>&1 || { err "missing image: $image"; missing=1; }
done
[[ "$missing" -eq 0 ]] || { err "one or more images failed to build"; exit 1; }

# base: extension present, agents dir empty
docker run --rm "$BASE_IMAGE" sh -c 'test -f "$HOME/.pi/agent/extensions/subagent/index.ts"' \
  || { err "base image missing subagent extension"; exit 1; }
if docker run --rm "$BASE_IMAGE" sh -c 'ls -A "$HOME/.pi/agent/agents"' | grep -q .; then
  err "base image agents dir must be empty (fallback + ConfigMap per G9)"
  exit 1
fi
log "base verified: extension present, agents dir empty"

# ancestors: baked .md files == enabled set (sorted comparison)
for i in "${!SLUGS[@]}"; do
  slug="${SLUGS[$i]}"
  expected="$(printf '%s' "${ENABLED_SETS[$i]}" | tr ' ' '\n' | sort | tr '\n' ' ' | sed 's/ $//')"
  actual="$(docker run --rm "${ANCESTOR_IMAGES[$i]}" sh -c 'ls "$HOME/.pi/agent/agents"' | sed 's/\.md$//' | sort | tr '\n' ' ' | sed 's/ $//')"
  if [[ "$actual" != "$expected" ]]; then
    err "ancestor ${slug} baked agents mismatch: expected [${expected}] got [${actual}]"
    exit 1
  fi
  docker run --rm "${ANCESTOR_IMAGES[$i]}" sh -c 'test -f "$HOME/.pi/agent/extensions/subagent/index.ts"' \
    || { err "ancestor ${slug} missing subagent extension (from base)"; exit 1; }
  log "ancestor ${slug} verified: agents = [${expected}]"
done

# --- push (only with --push) -------------------------------------------------
if [[ "$MODE" == "push" ]]; then
  registry_base="${REGISTRY#*://}"
  reachable=0
  for scheme in http https; do
    if docker run --rm --network host curlimages/curl curl -sf "${scheme}://${registry_base}/v2/" >/dev/null 2>&1; then
      reachable=1
      break
    fi
  done
  if [[ "$reachable" -ne 1 ]]; then
    err "registry ${REGISTRY} not reachable at /v2/; start it first, e.g.:"
    err "  docker run -d -p 5000:5000 --name cocoa-registry registry:2"
    exit 1
  fi
  log "registry ${REGISTRY} reachable"
  for image in "$BASE_IMAGE" "${ANCESTOR_IMAGES[@]}"; do
    log "push ${image}"
    docker push "$image"
  done
fi

log "done: ${#SLUGS[@]} ancestors + base (${MODE} mode)"
