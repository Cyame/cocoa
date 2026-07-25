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

# ---------------------------------------------------------------------------
# Messaging (emit points in P5)
# ---------------------------------------------------------------------------

MESSAGING_MESSAGE_SENT = "messaging.message_sent"
MESSAGING_DELIVERY_BLOCKED = "messaging.delivery_blocked"
MESSAGING_ACTIVATION_TRIGGERED = "messaging.activation_triggered"

# ---------------------------------------------------------------------------
# Blackboard (emit points in P6)
# ---------------------------------------------------------------------------

BLACKBOARD_FILE_CREATED = "blackboard.file_created"
BLACKBOARD_FILE_UPDATED = "blackboard.file_updated"
BLACKBOARD_FILE_ARCHIVED = "blackboard.file_archived"

# ---------------------------------------------------------------------------
# Memory (emit points in P6)
# ---------------------------------------------------------------------------

MEMORY_ENTRY_APPENDED = "memory.entry_appended"

# ---------------------------------------------------------------------------
# Instance lifecycle (emit points in P7)
# ---------------------------------------------------------------------------

INSTANCE_CREATED = "instance.created"
INSTANCE_DEPLOYING = "instance.deploying"
INSTANCE_RUNNING = "instance.running"
INSTANCE_RESTARTING = "instance.restarting"
INSTANCE_FAILED = "instance.failed"
INSTANCE_DELETED = "instance.deleted"
