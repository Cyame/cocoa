"""Blackboard API routes — collaborative surface, virtual filesystem, and vault.

Endpoints:
    GET    /{office_id}                        Lazy-get Blackboard
    PATCH  /{office_id}                        Update content/notes
    GET    /{office_id}/files                  List files (offset page)
    GET    /{office_id}/files/{file_id}        Get one file
    POST   /{office_id}/files                  Create file/directory
    PATCH  /{office_id}/files/{file_id}        Rename/move
    DELETE /{office_id}/files/{file_id}        Soft-delete
    GET    /{office_id}/vault                  Lazy-get Vault
    GET    /{office_id}/vault/entries          List vault entries
    POST   /{office_id}/files/{file_id}/archive  Archive file to Vault
"""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError
from app.core.event_types import (
    BLACKBOARD_FILE_ARCHIVED,
    BLACKBOARD_FILE_CREATED,
    BLACKBOARD_FILE_UPDATED,
)
from app.core.events import emit
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_office_role
from app.models.blackboard import Blackboard, BlackboardFile, Vault, VaultEntry
from app.schemas.blackboard import BlackboardOut, BlackboardUpdate
from app.schemas.blackboard_file import (
    BlackboardFileCreate,
    BlackboardFileOut,
    BlackboardFileUpdate,
)
from app.schemas.vault import VaultEntryOut, VaultOut

router = APIRouter(prefix="/blackboard", tags=["Blackboard"])
add_error_responses(router)


def _own_path(file: BlackboardFile) -> str:
    if file.parent_path:
        return f"{file.parent_path}/{file.name}"
    return file.name


def _split_parent_path(parent_path: str | None) -> tuple[str | None, str]:
    if not parent_path:
        return None, ""
    clean = parent_path.strip("/")
    if not clean:
        return None, ""
    dirname = os.path.dirname(clean)
    basename = os.path.basename(clean)
    dirname_str: str | None = "/" + dirname if dirname else None
    return dirname_str, basename


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_or_create_blackboard(
    db: DB, office_id: str
) -> Blackboard:
    result = await db.execute(
        select(Blackboard).where(
            Blackboard.office_id == office_id,
            Blackboard.deleted_at.is_(None),
        )
    )
    blackboard = result.scalar_one_or_none()
    if blackboard is None:
        blackboard = Blackboard(office_id=office_id, content=None, manual_notes=None)
        db.add(blackboard)
        await db.flush()
    return blackboard


async def _get_or_create_vault(db: DB, office_id: str) -> Vault:
    result = await db.execute(
        select(Vault).where(
            Vault.office_id == office_id,
            Vault.deleted_at.is_(None),
        )
    )
    vault = result.scalar_one_or_none()
    if vault is None:
        vault = Vault(office_id=office_id)
        db.add(vault)
        await db.flush()
    return vault


async def _validate_parent_directory(
    db: DB, office_id: str, parent_path: str | None
) -> None:
    if parent_path is None:
        return
    parent_dir_path, parent_name = _split_parent_path(parent_path)
    result = await db.execute(
        select(BlackboardFile)
        .where(
            BlackboardFile.office_id == office_id,
            BlackboardFile.parent_path == parent_dir_path,
            BlackboardFile.name == parent_name,
            BlackboardFile.is_directory,
            BlackboardFile.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError(
            "blackboard.parent_directory_not_found",
            "errors.blackboard.parent_directory_not_found",
            f"Parent directory '{parent_path}' not found in office '{office_id}'",
            details={"office_id": office_id, "parent_path": parent_path},
        )


# ---------------------------------------------------------------------------
# Blackboard
# ---------------------------------------------------------------------------


@router.get("/{office_id}", response_model=BlackboardOut)
async def read_blackboard(
    office_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Blackboard:
    await require_office_role(db, current_user.user_id, office_id, "viewer")
    blackboard = await _get_or_create_blackboard(db, office_id)
    await _get_or_create_vault(db, office_id)
    await db.commit()
    await db.refresh(blackboard)
    return blackboard


@router.patch("/{office_id}", response_model=BlackboardOut)
async def update_blackboard(
    office_id: str,
    body: BlackboardUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> Blackboard:
    await require_office_role(db, current_user.user_id, office_id, "editor")
    blackboard = await _get_or_create_blackboard(db, office_id)
    patch_data = body.model_dump(exclude_unset=True)
    for field, value in patch_data.items():
        setattr(blackboard, field, value)
    await db.commit()
    await db.refresh(blackboard)
    return blackboard


# ---------------------------------------------------------------------------
# BlackboardFile — read
# ---------------------------------------------------------------------------


@router.get("/{office_id}/files", response_model=OffsetPage[BlackboardFileOut])
async def list_files(
    office_id: str,
    db: DB,
    current_user: CurrentUserDep,
    parent_path: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage:
    await require_office_role(db, current_user.user_id, office_id, "viewer")
    stmt = (
        select(BlackboardFile)
        .where(
            BlackboardFile.office_id == office_id,
            BlackboardFile.deleted_at.is_(None),
        )
        .order_by(BlackboardFile.name)
    )
    if parent_path is not None:
        stmt = stmt.where(BlackboardFile.parent_path == parent_path)
    return await paginate_offset(db, stmt, offset, limit)


@router.get("/{office_id}/files/{file_id}", response_model=BlackboardFileOut)
async def get_file(
    office_id: str,
    file_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> BlackboardFile:
    await require_office_role(db, current_user.user_id, office_id, "viewer")
    result = await db.execute(
        select(BlackboardFile).where(
            BlackboardFile.id == file_id,
            BlackboardFile.office_id == office_id,
            BlackboardFile.deleted_at.is_(None),
        )
    )
    file = result.scalar_one_or_none()
    if file is None:
        raise NotFoundError(
            "blackboard.file_not_found",
            "errors.blackboard.file_not_found",
            f"BlackboardFile '{file_id}' not found",
            details={"file_id": file_id, "office_id": office_id},
        )
    return file


# ---------------------------------------------------------------------------
# BlackboardFile — write
# ---------------------------------------------------------------------------


@router.post(
    "/{office_id}/files",
    response_model=BlackboardFileOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_file(
    office_id: str,
    body: BlackboardFileCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> BlackboardFile:
    await require_office_role(db, current_user.user_id, office_id, "editor")
    await _validate_parent_directory(db, office_id, body.parent_path)

    if body.is_directory and (body.content_type is not None or body.file_size is not None):
        raise ConflictError(
            "blackboard.directory_cannot_have_content",
            "errors.blackboard.directory_cannot_have_content",
            "Directory entries cannot have content_type or file_size",
        )

    # Pre-check for duplicate path at the same level
    existing = await db.execute(
        select(BlackboardFile).where(
            BlackboardFile.office_id == office_id,
            BlackboardFile.parent_path == body.parent_path,
            BlackboardFile.name == body.name,
            BlackboardFile.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "blackboard.duplicate_path",
            "errors.blackboard.duplicate_path",
            f"A file or directory named '{body.name}' already exists at '{body.parent_path or '/'}'",
            details={"office_id": office_id, "parent_path": body.parent_path, "name": body.name},
        )

    storage_key = body.storage_key if body.storage_key else str(uuid.uuid4())

    file = BlackboardFile(
        office_id=office_id,
        name=body.name,
        parent_path=body.parent_path,
        storage_key=storage_key,
        content_type=body.content_type,
        file_size=body.file_size,
        is_directory=body.is_directory,
        uploader_user_id=current_user.user_id,
    )
    db.add(file)

    await emit(
        BLACKBOARD_FILE_CREATED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="blackboard_file",
        resource_id=file.id,
        payload={
            "office_id": office_id,
            "name": body.name,
            "parent_path": body.parent_path,
            "is_directory": body.is_directory,
        },
        session=db,
    )

    await db.commit()
    await db.refresh(file)
    return file


@router.patch("/{office_id}/files/{file_id}", response_model=BlackboardFileOut)
async def update_file(
    office_id: str,
    file_id: str,
    body: BlackboardFileUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> BlackboardFile:
    await require_office_role(db, current_user.user_id, office_id, "editor")

    result = await db.execute(
        select(BlackboardFile).where(
            BlackboardFile.id == file_id,
            BlackboardFile.office_id == office_id,
            BlackboardFile.deleted_at.is_(None),
        )
    )
    file = result.scalar_one_or_none()
    if file is None:
        raise NotFoundError(
            "blackboard.file_not_found",
            "errors.blackboard.file_not_found",
            f"BlackboardFile '{file_id}' not found",
            details={"file_id": file_id, "office_id": office_id},
        )

    if body.parent_path is not None and body.parent_path != file.parent_path:
        await _validate_parent_directory(db, office_id, body.parent_path)

    patch_data = body.model_dump(exclude_unset=True)
    for field, value in patch_data.items():
        setattr(file, field, value)

    await emit(
        BLACKBOARD_FILE_UPDATED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="blackboard_file",
        resource_id=file.id,
        payload={"office_id": office_id, "file_id": file_id},
        session=db,
    )

    await db.commit()
    await db.refresh(file)
    return file


@router.delete("/{office_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    office_id: str,
    file_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    await require_office_role(db, current_user.user_id, office_id, "editor")

    result = await db.execute(
        select(BlackboardFile).where(
            BlackboardFile.id == file_id,
            BlackboardFile.office_id == office_id,
            BlackboardFile.deleted_at.is_(None),
        )
    )
    file = result.scalar_one_or_none()
    if file is None:
        raise NotFoundError(
            "blackboard.file_not_found",
            "errors.blackboard.file_not_found",
            f"BlackboardFile '{file_id}' not found",
            details={"file_id": file_id, "office_id": office_id},
        )

    if file.is_directory:
        if file.parent_path:
            target_path = f"{file.parent_path}/{file.name}"
        else:
            target_path = f"/{file.name}"
        count_result = await db.execute(
            select(func.count()).select_from(BlackboardFile).where(
                BlackboardFile.office_id == office_id,
                BlackboardFile.parent_path == target_path,
                BlackboardFile.deleted_at.is_(None),
            )
        )
        if count_result.scalar_one() > 0:
            raise ConflictError(
                "blackboard.directory_not_empty",
                "errors.blackboard.directory_not_empty",
                f"Cannot delete directory '{target_path}' — it still contains files",
                details={"file_id": file_id, "path": target_path},
            )

    file.soft_delete()
    await db.commit()


# ---------------------------------------------------------------------------
# Vault
# ---------------------------------------------------------------------------


@router.get("/{office_id}/vault", response_model=VaultOut)
async def read_vault(
    office_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> Vault:
    await require_office_role(db, current_user.user_id, office_id, "viewer")
    vault = await _get_or_create_vault(db, office_id)
    await db.commit()
    await db.refresh(vault)
    return vault


@router.get("/{office_id}/vault/entries", response_model=OffsetPage[VaultEntryOut])
async def list_vault_entries(
    office_id: str,
    db: DB,
    current_user: CurrentUserDep,
    source_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage:
    await require_office_role(db, current_user.user_id, office_id, "viewer")
    vault = await _get_or_create_vault(db, office_id)
    stmt = (
        select(VaultEntry)
        .where(
            VaultEntry.vault_id == vault.id,
            VaultEntry.deleted_at.is_(None),
        )
        .order_by(VaultEntry.archived_at.desc())
    )
    if source_type is not None:
        stmt = stmt.where(VaultEntry.source_type == source_type)
    return await paginate_offset(db, stmt, offset, limit)


@router.post(
    "/{office_id}/files/{file_id}/archive",
    response_model=VaultEntryOut,
    status_code=status.HTTP_201_CREATED,
)
async def archive_file_to_vault(
    office_id: str,
    file_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> VaultEntry:
    await require_office_role(db, current_user.user_id, office_id, "editor")

    result = await db.execute(
        select(BlackboardFile)
        .where(
            BlackboardFile.id == file_id,
            BlackboardFile.office_id == office_id,
            BlackboardFile.deleted_at.is_(None),
        )
        .with_for_update()
    )
    file = result.scalar_one_or_none()
    if file is None:
        raise NotFoundError(
            "blackboard.file_not_found",
            "errors.blackboard.file_not_found",
            f"BlackboardFile '{file_id}' not found",
            details={"file_id": file_id, "office_id": office_id},
        )
    if file.is_directory:
        raise ConflictError(
            "blackboard.cannot_archive_directory",
            "errors.blackboard.cannot_archive_directory",
            f"Cannot archive directory '{file_id}'",
            details={"file_id": file_id},
        )

    vault_result = await db.execute(
        select(Vault).where(
            Vault.office_id == office_id,
            Vault.deleted_at.is_(None),
        )
    )
    vault = vault_result.scalar_one_or_none()
    if vault is None:
        vault = Vault(office_id=office_id)
        db.add(vault)
        await db.flush()

    entry = VaultEntry(
        vault_id=vault.id,
        source_type="blackboard_file",
        source_ref=file_id,
        archived_key=file.storage_key,
        archived_at=func.now(),
    )
    db.add(entry)

    file.soft_delete()

    await emit(
        BLACKBOARD_FILE_ARCHIVED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="blackboard_file",
        resource_id=file_id,
        payload={
            "office_id": office_id,
            "vault_entry_id": entry.id,
            "storage_key": file.storage_key,
        },
        session=db,
    )

    await db.commit()
    await db.refresh(entry)
    return entry
