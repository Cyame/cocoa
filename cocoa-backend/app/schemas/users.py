"""User administration schemas (PRD-v3-post)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

IdentityKey = Literal["system", "org", "namespace", "workspace", "member"]


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    identity: IdentityKey = "member"

    @field_validator("username")
    @classmethod
    def username_strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Username must not be empty")
        return v


class UserUpdate(BaseModel):
    email: str | None = None
    identity: IdentityKey | None = None


class UserIdentitySet(BaseModel):
    identity: IdentityKey


class UserExtraGenesSet(BaseModel):
    """Replace non-identity (extra) genes with this list of gene ids."""

    gene_ids: list[str] = Field(default_factory=list)


class UserGeneRef(BaseModel):
    id: str
    slug: str
    name: str
    locked: bool


class UserOut(BaseModel):
    id: str
    username: str
    email: str
    is_super_admin: bool
    identity: IdentityKey | None
    locked_genes: list[UserGeneRef] = Field(default_factory=list)
    extra_genes: list[UserGeneRef] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserCreateOut(UserOut):
    """Create response includes one-time plaintext password."""

    temporary_password: str


class AccountOut(BaseModel):
    id: str
    username: str
    email: str
    is_super_admin: bool
    identity: IdentityKey | None
    locked_genes: list[UserGeneRef] = Field(default_factory=list)
    extra_genes: list[UserGeneRef] = Field(default_factory=list)


class AccountUpdate(BaseModel):
    email: str | None = None


class AccountPasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v
