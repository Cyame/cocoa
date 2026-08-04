"""Event type constants for the Cocoa observability layer.

Naming convention: ``<domain>.<action_past_tense>``

Examples
--------
``system.startup``, ``harness.loop_started``

Harness-family events are defined here but their emit points land in P8.
This phase only declares the constants.
"""

# ---------------------------------------------------------------------------
# System lifecycle
# ---------------------------------------------------------------------------

SYSTEM_STARTUP = "system.startup"
SYSTEM_SHUTDOWN = "system.shutdown"

# ---------------------------------------------------------------------------
# Harness loop (emit points in P8)
# ---------------------------------------------------------------------------

HARNESS_LOOP_STARTED = "harness.loop_started"
HARNESS_CHECKPOINT = "harness.checkpoint"
HARNESS_CONTINUATION_INJECTED = "harness.continuation_injected"
HARNESS_LOOP_STOPPED = "harness.loop_stopped"
HARNESS_BREAKER_TRIPPED = "harness.breaker_tripped"
# control_sent is the D11 control-plane downlink event. Payload carries
# `{"action": "kill" | "pause" | "resume", "instance_id": "..."}`.
# Instance agent runtime consumes it on next checkpoint and self-terminates.
HARNESS_PAUSED = "harness.paused"
HARNESS_RESUMED = "harness.resumed"
HARNESS_INTERRUPTED = "harness.interrupted"
HARNESS_CONTROL_SENT = "harness.control_sent"

# ---------------------------------------------------------------------------
# Messaging (emit points in P5)
# ---------------------------------------------------------------------------

MESSAGING_MESSAGE_SENT = "messaging.message_sent"
MESSAGING_DELIVERY_BLOCKED = "messaging.delivery_blocked"
MESSAGING_ACTIVATION_TRIGGERED = "messaging.activation_triggered"

# Composer / Tunnel-shaped chat stream (PRD-v3.4.1)
CHAT_RESPONSE_CHUNK = "chat.response.chunk"
CHAT_RESPONSE_DONE = "chat.response.done"
CHAT_RESPONSE_ERROR = "chat.response.error"

# ---------------------------------------------------------------------------
# CentralHub (emit points in P6)
# ---------------------------------------------------------------------------

FORNIX_FILE_CREATED = "fornix.file_created"
FORNIX_FILE_UPDATED = "fornix.file_updated"
FORNIX_FILE_ARCHIVED = "fornix.file_archived"

# ---------------------------------------------------------------------------
# Memory (emit points in P6)
# ---------------------------------------------------------------------------

MEMORY_ENTRY_APPENDED = "memory.entry_appended"

# ---------------------------------------------------------------------------
# Instance lifecycle (emit points in P7)
# ---------------------------------------------------------------------------

INSTANCE_CREATED = "instance.created"
INSTANCE_DEPLOYED = "instance.deployed"
INSTANCE_STARTED = "instance.started"
INSTANCE_RESTARTED = "instance.restarted"
INSTANCE_STOPPED = "instance.stopped"
INSTANCE_FAILED = "instance.failed"
INSTANCE_DELETED = "instance.deleted"

# ---------------------------------------------------------------------------
# Learning (emit points in P10)
# ---------------------------------------------------------------------------

LEARNING_DISTILLATION_COMPLETED = "learning.distillation_completed"

# Phase-15f capability lifecycle (PRD §13.6.3–§13.6.5)
# reap:        Memory → Capability (instance-private, market entry)
# promote:     Instance cap → Entity shared (+ market entry)
# transmute:   Entity → BaseClass (new 神职)
# combine:     N Capabilities → 1 Gene (L2 packaging)
LEARNING_REAP_COMPLETED = "learning.reap_completed"
LEARNING_PROMOTE_COMPLETED = "learning.promote_completed"
LEARNING_DISTILL_TRANSMUTED = "learning.distill_transmuted"
LEARNING_CAPABILITY_COMBINED = "learning.capability_combined"

# Phase-15f T4: instance re-sync after promote (PRD §13.6.7).
# Plural form distinct from the lifecycle INSTANCE_RESTARTED above; this
# is the operator-initiated batch re-sync event payload.
INSTANCE_BATCH_RESTARTED = "instance.batch_restarted"

# ---------------------------------------------------------------------------
# Clone operations (v4.4)
# ---------------------------------------------------------------------------

BASE_CLASS_CLONED = "base_class.cloned"
ENTITY_CLONED = "entity.cloned"
ORGANIZATION_CLONED = "organization.cloned"
WORKSPACE_CLONED = "workspace.cloned"
WORKSPACE_CLONE_PASSAGE_DROPPED = "workspace.clone_passage_dropped"
