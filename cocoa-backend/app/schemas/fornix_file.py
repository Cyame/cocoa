"""FornixFile schemas — 穹窿脑区 (virtual filesystem inside a CentralHub).

> **15d-rename (2026-07-29)**: Renamed from `fornix_file.py`. Class names
> `FornixFileCreate` / `FornixFileUpdate` / `FornixFileOut` are 15d+
> canonical. No back-compat aliases.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class FornixFileCreate(BaseModel):
    """Create a file or directory inside the 穹窿 (fornix) brain of a CentralHub."""

    workspace_id: str
    name: str
    parent_path: str | None = None
    storage_key: str = ""
    content_type: str | None = None
    file_size: int | None = None
    is_directory: bool = False

    @field_validator("name")
    @classmethod
    def name_max_length(cls, v: str) -> str:
        if len(v) > 255:
            msg = f"name must be at most 255 characters, got {len(v)}"
            raise ValueError(msg)
        return v


class FornixFileUpdate(BaseModel):
    """Rename or move a FornixFile (parent_path is the new parent directory)."""

    name: str | None = None
    parent_path: str | None = None


class FornixFileOut(BaseModel):
    """Read-only representation of a FornixFile."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    parent_path: str | None
    storage_key: str
    content_type: str | None
    file_size: int | None
    is_directory: bool
    uploader_user_id: str | None
    uploader_instance_id: str | None
    created_at: datetime
