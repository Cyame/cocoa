"""BlackboardFile schemas — virtual filesystem inside a Blackboard."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class BlackboardFileCreate(BaseModel):
    """Create a file or directory inside a Blackboard."""

    office_id: str
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


class BlackboardFileUpdate(BaseModel):
    """Rename or move a BlackboardFile (parent_path is the new parent directory)."""

    name: str | None = None
    parent_path: str | None = None


class BlackboardFileOut(BaseModel):
    """Read-only representation of a BlackboardFile."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    office_id: str
    name: str
    parent_path: str | None
    storage_key: str
    content_type: str | None
    file_size: int | None
    is_directory: bool
    uploader_user_id: str | None
    uploader_instance_id: str | None
    created_at: datetime
