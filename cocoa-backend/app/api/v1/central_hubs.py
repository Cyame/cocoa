"""CentralHub API routes — collaborative surface, virtual filesystem, and vault.

> **15d-rename (2026-07-29)**: Renamed from `app/api/v1/central_hub.py`.
> Served at the new path `/central-hubs/{wid}/...`. No back-compat alias —
> callers must update URLs. (No prod data yet.)

Endpoints (15d+ canonical path /central_hub/...):
    GET    /central-hubs/{wid}                        Lazy-get CentralHub (was /central_hub/{wid})
    PATCH  /central-hubs/{wid}                        Update content/notes
    GET    /central-hubs/{wid}/fornix/files          List FornixFile (was /central_hub/{wid}/files)
    GET    /central-hubs/{wid}/fornix/files/{fid}    Get one FornixFile
    POST   /central-hubs/{wid}/fornix/files          Create file/directory
    PATCH  /central-hubs/{wid}/fornix/files/{fid}    Rename/move
    DELETE /central-hubs/{wid}/fornix/files/{fid}    Soft-delete
    GET    /central-hubs/{wid}/vault                  Lazy-get Vault
    GET    /central-hubs/{wid}/vault/entries          List vault entries
    POST   /central-hubs/{wid}/fornix/files/{fid}/archive  Archive file to Vault (was /central_hub/{wid}/files/{fid}/archive)
    GET    /{workspace_id}                        Lazy-get CentralHub
    PATCH  /{workspace_id}                        Update content/notes
    GET    /{workspace_id}/files                  List files (offset page)
    GET    /{workspace_id}/files/{file_id}        Get one file
    POST   /{workspace_id}/files                  Create file/directory
    PATCH  /{workspace_id}/files/{file_id}        Rename/move
    DELETE /{workspace_id}/files/{file_id}        Soft-delete
    GET    /{workspace_id}/vault                  Lazy-get Vault
    GET    /{workspace_id}/vault/entries          List vault entries
    POST   /{workspace_id}/files/{file_id}/archive  Archive file to Vault
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.errors import ConflictError, NotFoundError
from app.core.event_types import (
    FORNIX_FILE_ARCHIVED,
    FORNIX_FILE_CREATED,
    FORNIX_FILE_UPDATED,
)
from app.core.events import emit
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_workspace_permission
from app.models.central_hub import (
    BrainstemSchedule,
    CentralHub,
    CerebellumAgent,
    FornixFile,
    FrontalLobeKanban,
    Vault,
    VaultEntry,
)
from app.schemas.brain_regions import (
    BrainstemScheduleCreate,
    BrainstemScheduleOut,
    BrainstemScheduleUpdate,
    CerebellumAgentOut,
    CerebellumAgentUpdate,
    CerebellumRestartOut,
    FrontalLobeKanbanCreate,
    FrontalLobeKanbanOut,
    FrontalLobeKanbanUpdate,
)
from app.schemas.central_hub import CentralHubOut, CentralHubUpdate
from app.schemas.fornix_file import (
    FornixFileCreate,
    FornixFileOut,
    FornixFileUpdate,
)
from app.schemas.vault import VaultEntryOut, VaultOut

# 15d+ canonical path — no back-compat alias
router = APIRouter(prefix="/central-hubs", tags=["CentralHub"])
add_error_responses(router)


def _own_path(file: FornixFile) -> str:
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


async def _get_or_create_central_hub(
    db: DB, workspace_id: str
) -> CentralHub:
    result = await db.execute(
        select(CentralHub).where(
            CentralHub.workspace_id == workspace_id,
            CentralHub.deleted_at.is_(None),
        )
    )
    central_hub = result.scalar_one_or_none()
    if central_hub is None:
        central_hub = CentralHub(workspace_id=workspace_id, content=None, manual_notes=None)
        db.add(central_hub)
        await db.flush()
    return central_hub


async def _get_or_create_vault(db: DB, workspace_id: str) -> Vault:
    result = await db.execute(
        select(Vault).where(
            Vault.workspace_id == workspace_id,
            Vault.deleted_at.is_(None),
        )
    )
    vault = result.scalar_one_or_none()
    if vault is None:
        vault = Vault(workspace_id=workspace_id)
        db.add(vault)
        await db.flush()
    return vault


async def _validate_parent_directory(
    db: DB, workspace_id: str, parent_path: str | None
) -> None:
    if parent_path is None:
        return
    parent_dir_path, parent_name = _split_parent_path(parent_path)
    result = await db.execute(
        select(FornixFile)
        .where(
            FornixFile.workspace_id == workspace_id,
            FornixFile.parent_path == parent_dir_path,
            FornixFile.name == parent_name,
            FornixFile.is_directory,
            FornixFile.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError(
            "central_hub.parent_directory_not_found",
            "errors.central_hub.parent_directory_not_found",
            f"Parent directory '{parent_path}' not found in workspace '{workspace_id}'",
            details={"workspace_id": workspace_id, "parent_path": parent_path},
        )


# ---------------------------------------------------------------------------
# CentralHub
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}", response_model=CentralHubOut)
async def read_central_hub(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> CentralHub:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )
    central_hub = await _get_or_create_central_hub(db, workspace_id)
    await _get_or_create_vault(db, workspace_id)
    await db.commit()
    await db.refresh(central_hub)
    return central_hub


@router.patch("/{workspace_id}", response_model=CentralHubOut)
async def update_central_hub(
    workspace_id: str,
    body: CentralHubUpdate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> CentralHub:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )
    central_hub = await _get_or_create_central_hub(db, workspace_id)
    patch_data = body.model_dump(exclude_unset=True)
    for field, value in patch_data.items():
        setattr(central_hub, field, value)
    await db.commit()
    await db.refresh(central_hub)
    return central_hub


# ---------------------------------------------------------------------------
# FornixFile — read
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/files", response_model=OffsetPage[FornixFileOut])
async def list_files(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    parent_path: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )
    stmt = (
        select(FornixFile)
        .where(
            FornixFile.workspace_id == workspace_id,
            FornixFile.deleted_at.is_(None),
        )
        .order_by(FornixFile.name)
    )
    if parent_path is not None:
        stmt = stmt.where(FornixFile.parent_path == parent_path)
    return await paginate_offset(db, stmt, offset, limit)


@router.get("/{workspace_id}/files/{file_id}", response_model=FornixFileOut)
async def get_file(
    workspace_id: str,
    file_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> FornixFile:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )
    result = await db.execute(
        select(FornixFile).where(
            FornixFile.id == file_id,
            FornixFile.workspace_id == workspace_id,
            FornixFile.deleted_at.is_(None),
        )
    )
    file = result.scalar_one_or_none()
    if file is None:
        raise NotFoundError(
            "central_hub.fornix.file_not_found",
            "errors.central_hub.file_not_found",
            f"FornixFile '{file_id}' not found",
            details={"file_id": file_id, "workspace_id": workspace_id},
        )
    return file


# ---------------------------------------------------------------------------
# FornixFile — write
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/files",
    response_model=FornixFileOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_file(
    workspace_id: str,
    body: FornixFileCreate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> FornixFile:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )
    await _validate_parent_directory(db, workspace_id, body.parent_path)

    if body.is_directory and (body.content_type is not None or body.file_size is not None):
        raise ConflictError(
            "central_hub.directory_cannot_have_content",
            "errors.central_hub.directory_cannot_have_content",
            "Directory entries cannot have content_type or file_size",
        )

    # Pre-check for duplicate path at the same level
    existing = await db.execute(
        select(FornixFile).where(
            FornixFile.workspace_id == workspace_id,
            FornixFile.parent_path == body.parent_path,
            FornixFile.name == body.name,
            FornixFile.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "central_hub.fornix.duplicate_path",
            "errors.central_hub.fornix.duplicate_path",
            f"A file or directory named '{body.name}' already exists at '{body.parent_path or '/'}'",
            details={"workspace_id": workspace_id, "parent_path": body.parent_path, "name": body.name},
        )

    storage_key = body.storage_key if body.storage_key else str(uuid.uuid4())

    hub = (
        await db.execute(
            select(CentralHub).where(
                CentralHub.workspace_id == workspace_id,
                CentralHub.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if hub is None:
        hub = CentralHub(workspace_id=workspace_id)
        db.add(hub)
        await db.flush()

    file = FornixFile(
        workspace_id=workspace_id,
        central_hub_id=hub.id,
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
        FORNIX_FILE_CREATED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="fornix_file",  # 15d+ canonical (was "fornix_file" pre-rename)
        resource_id=file.id,
        payload={
            "workspace_id": workspace_id,
            "name": body.name,
            "parent_path": body.parent_path,
            "is_directory": body.is_directory,
        },
        session=db,
    )

    await db.commit()
    await db.refresh(file)
    return file


@router.patch("/{workspace_id}/files/{file_id}", response_model=FornixFileOut)
async def update_file(
    workspace_id: str,
    file_id: str,
    body: FornixFileUpdate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> FornixFile:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

    result = await db.execute(
        select(FornixFile).where(
            FornixFile.id == file_id,
            FornixFile.workspace_id == workspace_id,
            FornixFile.deleted_at.is_(None),
        )
    )
    file = result.scalar_one_or_none()
    if file is None:
        raise NotFoundError(
            "central_hub.fornix.file_not_found",
            "errors.central_hub.file_not_found",
            f"FornixFile '{file_id}' not found",
            details={"file_id": file_id, "workspace_id": workspace_id},
        )

    if body.parent_path is not None and body.parent_path != file.parent_path:
        await _validate_parent_directory(db, workspace_id, body.parent_path)

    patch_data = body.model_dump(exclude_unset=True)
    for field, value in patch_data.items():
        setattr(file, field, value)

    await emit(
        FORNIX_FILE_UPDATED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="fornix_file",  # 15d+ canonical (was "fornix_file" pre-rename)
        resource_id=file.id,
        payload={"workspace_id": workspace_id, "file_id": file_id},
        session=db,
    )

    await db.commit()
    await db.refresh(file)
    return file


@router.delete("/{workspace_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    workspace_id: str,
    file_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> None:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

    result = await db.execute(
        select(FornixFile).where(
            FornixFile.id == file_id,
            FornixFile.workspace_id == workspace_id,
            FornixFile.deleted_at.is_(None),
        )
    )
    file = result.scalar_one_or_none()
    if file is None:
        raise NotFoundError(
            "central_hub.fornix.file_not_found",
            "errors.central_hub.file_not_found",
            f"FornixFile '{file_id}' not found",
            details={"file_id": file_id, "workspace_id": workspace_id},
        )

    if file.is_directory:
        if file.parent_path:
            target_path = f"{file.parent_path}/{file.name}"
        else:
            target_path = f"/{file.name}"
        count_result = await db.execute(
            select(func.count()).select_from(FornixFile).where(
                FornixFile.workspace_id == workspace_id,
                FornixFile.parent_path == target_path,
                FornixFile.deleted_at.is_(None),
            )
        )
        if count_result.scalar_one() > 0:
            raise ConflictError(
                "central_hub.directory_not_empty",
                "errors.central_hub.directory_not_empty",
                f"Cannot delete directory '{target_path}' — it still contains files",
                details={"file_id": file_id, "path": target_path},
            )

    file.soft_delete()
    await db.commit()


# ---------------------------------------------------------------------------
# Vault
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/vault", response_model=VaultOut)
async def read_vault(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> Vault:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )
    vault = await _get_or_create_vault(db, workspace_id)
    await db.commit()
    await db.refresh(vault)
    return vault


@router.get("/{workspace_id}/vault/entries", response_model=OffsetPage[VaultEntryOut])
async def list_vault_entries(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    source_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )
    vault = await _get_or_create_vault(db, workspace_id)
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
    "/{workspace_id}/files/{file_id}/archive",
    response_model=VaultEntryOut,
    status_code=status.HTTP_201_CREATED,
)
async def archive_file_to_vault(
    workspace_id: str,
    file_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> VaultEntry:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )

    result = await db.execute(
        select(FornixFile)
        .where(
            FornixFile.id == file_id,
            FornixFile.workspace_id == workspace_id,
            FornixFile.deleted_at.is_(None),
        )
        .with_for_update()
    )
    file = result.scalar_one_or_none()
    if file is None:
        raise NotFoundError(
            "central_hub.fornix.file_not_found",
            "errors.central_hub.file_not_found",
            f"FornixFile '{file_id}' not found",
            details={"file_id": file_id, "workspace_id": workspace_id},
        )
    if file.is_directory:
        raise ConflictError(
            "central_hub.fornix.cannot_archive_directory",
            "errors.central_hub.fornix.cannot_archive_directory",
            f"Cannot archive directory '{file_id}'",
            details={"file_id": file_id},
        )

    vault_result = await db.execute(
        select(Vault).where(
            Vault.workspace_id == workspace_id,
            Vault.deleted_at.is_(None),
        )
    )
    vault = vault_result.scalar_one_or_none()
    if vault is None:
        vault = Vault(workspace_id=workspace_id)
        db.add(vault)
        await db.flush()

    entry = VaultEntry(
        vault_id=vault.id,
        source_type="fornix_file",  # 15d+ canonical (was "fornix_file" pre-rename)
        source_ref=file_id,
        archived_key=file.storage_key,
        archived_at=func.now(),
    )
    db.add(entry)

    file.soft_delete()

    await emit(
        FORNIX_FILE_ARCHIVED,
        actor_type="user",
        actor_id=current_user.user_id,
        resource_type="fornix_file",  # 15d+ canonical (was "fornix_file" pre-rename)
        resource_id=file_id,
        payload={
            "workspace_id": workspace_id,
            "vault_entry_id": entry.id,
            "storage_key": file.storage_key,
        },
        session=db,
    )

    await db.commit()
    await db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# Frontal lobe (Kanban)
# ---------------------------------------------------------------------------


async def _get_cerebellum(db: DB, workspace_id: str) -> CerebellumAgent:
    hub = await _get_or_create_central_hub(db, workspace_id)
    result = await db.execute(
        select(CerebellumAgent).where(
            CerebellumAgent.central_hub_id == hub.id,
            CerebellumAgent.deleted_at.is_(None),
        )
    )
    cerebellum = result.scalar_one_or_none()
    if cerebellum is None:
        cerebellum = CerebellumAgent(
            central_hub_id=hub.id,
            name="cerebellum",
            base_slug="cerebellum-baseclass",
            loop_status="idle",
        )
        db.add(cerebellum)
        await db.flush()
    return cerebellum


@router.get(
    "/{workspace_id}/frontal-lobe/kanbans",
    response_model=OffsetPage[FrontalLobeKanbanOut],
)
async def list_frontal_kanbans(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )
    hub = await _get_or_create_central_hub(db, workspace_id)
    stmt = (
        select(FrontalLobeKanban)
        .where(
            FrontalLobeKanban.central_hub_id == hub.id,
            FrontalLobeKanban.deleted_at.is_(None),
        )
        .order_by(FrontalLobeKanban.position)
    )
    return await paginate_offset(db, stmt, offset, limit)


@router.post(
    "/{workspace_id}/frontal-lobe/kanbans",
    response_model=FrontalLobeKanbanOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_frontal_kanban(
    workspace_id: str,
    body: FrontalLobeKanbanCreate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> FrontalLobeKanban:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )
    hub = await _get_or_create_central_hub(db, workspace_id)
    card = FrontalLobeKanban(central_hub_id=hub.id, **body.model_dump())
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return card


@router.patch(
    "/{workspace_id}/frontal-lobe/kanbans/{kanban_id}",
    response_model=FrontalLobeKanbanOut,
)
async def update_frontal_kanban(
    workspace_id: str,
    kanban_id: str,
    body: FrontalLobeKanbanUpdate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> FrontalLobeKanban:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )
    hub = await _get_or_create_central_hub(db, workspace_id)
    result = await db.execute(
        select(FrontalLobeKanban).where(
            FrontalLobeKanban.id == kanban_id,
            FrontalLobeKanban.central_hub_id == hub.id,
            FrontalLobeKanban.deleted_at.is_(None),
        )
    )
    card = result.scalar_one_or_none()
    if card is None:
        raise NotFoundError(
            "central_hub.frontal_kanban_not_found",
            "errors.central_hub.frontal_kanban_not_found",
            f"Kanban card '{kanban_id}' not found",
        )
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(card, field, value)
    await db.commit()
    await db.refresh(card)
    return card


@router.delete(
    "/{workspace_id}/frontal-lobe/kanbans/{kanban_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_frontal_kanban(
    workspace_id: str,
    kanban_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> None:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )
    hub = await _get_or_create_central_hub(db, workspace_id)
    result = await db.execute(
        select(FrontalLobeKanban).where(
            FrontalLobeKanban.id == kanban_id,
            FrontalLobeKanban.central_hub_id == hub.id,
            FrontalLobeKanban.deleted_at.is_(None),
        )
    )
    card = result.scalar_one_or_none()
    if card is None:
        raise NotFoundError(
            "central_hub.frontal_kanban_not_found",
            "errors.central_hub.frontal_kanban_not_found",
            f"Kanban card '{kanban_id}' not found",
        )
    card.soft_delete()
    await db.commit()


# ---------------------------------------------------------------------------
# Brainstem (schedules)
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/brainstem/schedules",
    response_model=OffsetPage[BrainstemScheduleOut],
)
async def list_brainstem_schedules(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OffsetPage:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )
    hub = await _get_or_create_central_hub(db, workspace_id)
    stmt = (
        select(BrainstemSchedule)
        .where(
            BrainstemSchedule.central_hub_id == hub.id,
            BrainstemSchedule.deleted_at.is_(None),
        )
        .order_by(BrainstemSchedule.name)
    )
    return await paginate_offset(db, stmt, offset, limit)


@router.post(
    "/{workspace_id}/brainstem/schedules",
    response_model=BrainstemScheduleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_brainstem_schedule(
    workspace_id: str,
    body: BrainstemScheduleCreate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> BrainstemSchedule:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )
    hub = await _get_or_create_central_hub(db, workspace_id)
    schedule = BrainstemSchedule(central_hub_id=hub.id, **body.model_dump())
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.patch(
    "/{workspace_id}/brainstem/schedules/{schedule_id}",
    response_model=BrainstemScheduleOut,
)
async def update_brainstem_schedule(
    workspace_id: str,
    schedule_id: str,
    body: BrainstemScheduleUpdate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> BrainstemSchedule:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )
    hub = await _get_or_create_central_hub(db, workspace_id)
    result = await db.execute(
        select(BrainstemSchedule).where(
            BrainstemSchedule.id == schedule_id,
            BrainstemSchedule.central_hub_id == hub.id,
            BrainstemSchedule.deleted_at.is_(None),
        )
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise NotFoundError(
            "central_hub.brainstem_schedule_not_found",
            "errors.central_hub.brainstem_schedule_not_found",
            f"Brainstem schedule '{schedule_id}' not found",
        )
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.delete(
    "/{workspace_id}/brainstem/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_brainstem_schedule(
    workspace_id: str,
    schedule_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> None:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )
    hub = await _get_or_create_central_hub(db, workspace_id)
    result = await db.execute(
        select(BrainstemSchedule).where(
            BrainstemSchedule.id == schedule_id,
            BrainstemSchedule.central_hub_id == hub.id,
            BrainstemSchedule.deleted_at.is_(None),
        )
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise NotFoundError(
            "central_hub.brainstem_schedule_not_found",
            "errors.central_hub.brainstem_schedule_not_found",
            f"Brainstem schedule '{schedule_id}' not found",
        )
    schedule.soft_delete()
    await db.commit()


# ---------------------------------------------------------------------------
# Cerebellum (1:1 central agent)
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/cerebellum", response_model=CerebellumAgentOut)
async def read_cerebellum(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> CerebellumAgent:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_view_workspace",
        x_organization_id=x_organization_id,
    )
    cerebellum = await _get_cerebellum(db, workspace_id)
    await db.commit()
    await db.refresh(cerebellum)
    return cerebellum


@router.patch("/{workspace_id}/cerebellum", response_model=CerebellumAgentOut)
async def update_cerebellum(
    workspace_id: str,
    body: CerebellumAgentUpdate,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> CerebellumAgent:
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_edit_workspace",
        x_organization_id=x_organization_id,
    )
    cerebellum = await _get_cerebellum(db, workspace_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(cerebellum, field, value)
    await db.commit()
    await db.refresh(cerebellum)
    return cerebellum


@router.post("/{workspace_id}/cerebellum/restart", response_model=CerebellumRestartOut)
async def restart_cerebellum(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> CerebellumRestartOut:
    """Mark cerebellum loop as restarting then idle (control-plane stub)."""
    await require_workspace_permission(
        db,
        current_user.user_id,
        workspace_id,
        "can_operate_workspace",
        x_organization_id=x_organization_id,
    )
    cerebellum = await _get_cerebellum(db, workspace_id)
    cerebellum.loop_status = "restarting"
    await db.flush()
    restarted_at = datetime.now(timezone.utc)
    cerebellum.loop_status = "idle"
    cerebellum.heartbeat_at = restarted_at
    await db.commit()
    return CerebellumRestartOut(
        cerebellum_id=cerebellum.id,
        loop_status=cerebellum.loop_status,
        restarted_at=restarted_at,
    )
