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
FORNIX_FILE_RESTORED = "fornix.file_restored"
# Dual-write (DB + Host shared/ mirror) failure. The API rolls back the DB
# change and surfaces a 5xx — never a silent DB-only or file-only write.
FORNIX_SYNC_FAILED = "fornix.sync_failed"

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
# Learning (emit points in P10 / v4.6)
# ---------------------------------------------------------------------------

# Legacy distill command (directive router `/distill`) — kept for the
# historical slash-command flow; the v4.6 lifecycle events below are the
# canonical audit set (v4-6-learning-writeback.md L3).
LEARNING_DISTILLATION_COMPLETED = "learning.distillation_completed"

# v4.6 learning write-back — canonical past-tense audit events.
# reap:        Memory → Capability (instance-private, market entry)
# promote:     Instance cap → Entity shared (+ market entry)
# transmute:   Entity → BaseClass (new 神职)
# compose:     N Capabilities → 1 Gene (L2 packaging)
LEARNING_REAPED = "learning.reaped"
LEARNING_PROMOTED = "learning.promoted"
LEARNING_TRANSMUTED = "learning.transmuted"
LEARNING_COMPOSED = "learning.composed"

# v4.6 存量迁移：notepad_refs 指向的文件不可读，content 回落为路径字符串。
LEARNING_NOTEPAD_MIGRATION_ORPHAN = "learning.notepad_migration_orphan"

# v4.7 inject 发射点（本切片仅声明常量，emit 在 v4.7 harness-collab 落地）——
# 注入入口与出口事件成对（audit-product-design.md §14）。
LEARNING_CAPABILITY_INJECTED = "learning.capability_injected"
LEARNING_GENE_INJECTED = "learning.gene_injected"

# ---------------------------------------------------------------------------
# Inject queue / report (emit points in v4.7 H6 inject_queue service)
# ---------------------------------------------------------------------------

# Enqueue: Harness/Workspace 下行注入已入队（payload 含 queue_id/kind/delivery_mode/tldr）。
HARNESS_INJECT_REQUESTED = "harness.inject_requested"
# Host 对 soft_inject/wake 应用成功并 ACK 后发出。
HARNESS_INJECT_APPLIED = "harness.inject_applied"
# Host 报错 / 拒绝 / 超时 → failed。
HARNESS_INJECT_FAILED = "harness.inject_failed"
# Instance 结构化 report_event 被接受（V47-10 校验通过）。
HARNESS_REPORT_RECEIVED = "harness.report_received"

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
