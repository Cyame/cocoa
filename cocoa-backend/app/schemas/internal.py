"""v4.7 H6 internal DTOs for the inject queue and structured reports.

These schemas back the Harness↔Workspace collaboration protocol surface
(``.omo/plans/v4-7-harness-collab.md``). The endpoint wiring lives in
later v4.7 slices; this module only declares the DTOs plus the V47-10
tldr hard-validation rules they share with the inject-queue service.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.core.errors import EyotError

DeliveryMode = Literal["notify", "soft_inject", "wake"]
InjectKind = Literal[
    "collab_inject", "gene_inject", "capability_inject", "cerebellum_route"
]
InjectOutcome = Literal["ok", "blocked", "failed"]

# V47-10: 两个数字用途不同，禁止合并成一个阈值。
TLDR_MAX_CHARS = 200
PROSE_THRESHOLD_CHARS = 240

_ERROR_TLDR_TOO_LONG = "errors.internal.tldr_too_long"
_ERROR_TLDR_REQUIRED = "errors.internal.tldr_required"


class ContentRef(BaseModel):
    """Typed reference to a deliverable location (v4.7 label is new)."""

    scope: Literal["hub", "instance"]
    path: str
    label: str | None = Field(default=None, description="Human label for the ref")


class InjectEnqueueRequest(BaseModel):
    """Body for enqueueing an inject to one instance."""

    kind: InjectKind
    delivery_mode: DeliveryMode
    tldr: str | None = Field(
        default=None, description="Max 200 chars; required when prose exceeds 240"
    )
    content_refs: list[ContentRef] = Field(default_factory=list)
    gene_ids: list[str] = Field(default_factory=list)
    capability_ids: list[str] = Field(default_factory=list)
    report: dict[str, Any] | None = Field(
        default=None,
        description="Shape: {outcome, changes[], validation[], blockers[]}",
    )

    @model_validator(mode="after")
    def _apply_tldr_rules(self) -> Self:
        validate_tldr(self.tldr, prose_length=report_prose_length(self.report))
        return self


class ReportRequest(BaseModel):
    """Structured ``report_event`` sent by an instance to the Workspace."""

    tldr: str | None = None
    outcome: InjectOutcome
    changes: list[str] = Field(default_factory=list)
    validation: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    content_refs: list[ContentRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _apply_tldr_rules(self) -> Self:
        prose = sum(len(s) for lst in (self.changes, self.validation, self.blockers) for s in lst)
        validate_tldr(self.tldr, prose_length=prose)
        return self


class AckRequest(BaseModel):
    """Body for a host acking delivered inject queue rows."""

    queue_ids: list[str] = Field(..., min_length=1)


class HubReadRequest(BaseModel):
    """Body for ``POST /internal/hub/read`` — mount-contract hub file reads.

    ``workspace_id`` is explicit because internal endpoints carry no JWT / org
    context; the caller (agent pod) resolves it from its own Instance row.
    """

    workspace_id: str
    refs: list[ContentRef] = Field(..., min_length=1)


class HubWriteRequest(BaseModel):
    """Body for ``POST /internal/hub/write``.

    ``scope="shared"`` dual-writes the FornixFile row (uploader = instance)
    and the ``<FORNIX_ROOT>/<workspace_id>/shared/`` mirror — the work →
    shared promote path. ``scope="work"`` validates the pod-local ``work/``
    path and records an audit event only (work files are pod-private per
    v4.5 ``data/work/`` — never mirrored to the backend).
    """

    workspace_id: str
    instance_id: str
    scope: Literal["work", "shared"]
    path: str
    content: str


class InternalReportRequest(ReportRequest):
    """Body for ``POST /internal/report`` — ReportRequest + caller identity."""

    workspace_id: str
    instance_id: str


def _list_string_length(items: Any) -> int:
    """Total character length of the string entries in ``items`` (0 if not a list)."""
    if not isinstance(items, list):
        return 0
    return sum(len(item) for item in items if isinstance(item, str))


def report_prose_length(report: Any) -> int:
    """V47-10: report.changes + report.validation + report.blockers lengths."""
    if not isinstance(report, dict):
        return 0
    return sum(_list_string_length(report.get(key)) for key in ("changes", "validation", "blockers"))


def compute_prose_length(payload: Any) -> int:
    """V47-10: payload ``text``/``body`` lengths plus nested report prose."""
    if not isinstance(payload, dict):
        return 0
    text_len = sum(
        len(payload[key]) for key in ("text", "body") if isinstance(payload.get(key), str)
    )
    return text_len + report_prose_length(payload.get("report"))


def validate_tldr(tldr: str | None, *, prose_length: int) -> None:
    """Enforce the V47-10 tldr rules; raise ``EyotError`` (400) on violation.

    - ``tldr``, when provided, must be <= 200 characters.
    - Prose above 240 characters requires a non-empty ``tldr``.
    """
    if tldr is not None and len(tldr) > TLDR_MAX_CHARS:
        raise EyotError(
            error_code="internal.tldr_too_long",
            message_key=_ERROR_TLDR_TOO_LONG,
            message=f"tldr exceeds {TLDR_MAX_CHARS} characters",
            status_code=400,
            details={"max_length": TLDR_MAX_CHARS, "actual_length": len(tldr)},
        )
    if prose_length > PROSE_THRESHOLD_CHARS and not (tldr and tldr.strip()):
        raise EyotError(
            error_code="internal.tldr_required",
            message_key=_ERROR_TLDR_REQUIRED,
            message=f"tldr is required when prose exceeds {PROSE_THRESHOLD_CHARS} characters",
            status_code=400,
            details={"prose_length": prose_length, "threshold": PROSE_THRESHOLD_CHARS},
        )
