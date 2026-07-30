"""Implicit System hub — description assist (PRD-v3).

POST /system-hub/generate-description
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.api.v1.organizations import _get_default_org
from app.core.errors import ValidationError
from app.core.openapi import add_error_responses
from app.models.organization_provider import OrganizationProvider
from app.schemas.organization import GenerateDescriptionOut, GenerateDescriptionRequest
from app.services.llm.llm_client import LLMError
from app.services.llm.org_provider import build_llm_client_from_org_provider

router = APIRouter(prefix="/system-hub", tags=["SystemHub"])
add_error_responses(router)

_SYSTEM_PROMPT = (
    "你是 Cocoa 平台的文案助手（System 中枢）。"
    "根据用户给定的眷属（Entity）信息，产出一段简洁的中文 description，供创建表单使用。\n\n"
    "约束：\n"
    "- 输出纯描述正文，不要标题、不要 markdown、不要引号包裹整段\n"
    "- 约 50–400 字（职能简单可短、复杂可写满；优先写清职责边界与协作方式）；"
    "语气专业、可执行，避免空泛口号与 emoji\n"
    "- 紧扣名称与角色定位；不要编造未给出的组织机密或具体内部系统名\n"
    "- 若提供了「当前描述」，在保留原意与关键事实的前提下改写得更清晰、具体；"
    "不要无故删掉已有专有名词\n\n"
    "只输出最终 description 正文。"
)

@router.post("/generate-description", response_model=GenerateDescriptionOut)
async def generate_description(
    body: GenerateDescriptionRequest,
    db: DB,
    current_user: CurrentUserDep,
) -> GenerateDescriptionOut:
    org = await _get_default_org(db)
    if not org.system_hub_provider_id or not org.system_hub_model:
        raise ValidationError(
            "system_hub.not_configured",
            "errors.system_hub.not_configured",
            "System hub provider is not configured — set it in world settings",
        )

    result = await db.execute(
        select(OrganizationProvider).where(
            OrganizationProvider.id == org.system_hub_provider_id,
            OrganizationProvider.deleted_at.is_(None),
            OrganizationProvider.enabled.is_(True),
        )
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise ValidationError(
            "system_hub.provider_unavailable",
            "errors.system_hub.provider_unavailable",
            "System hub provider is missing or disabled",
        )

    current = (body.description or "").strip()
    user_block = (
        f"眷属名称：{body.name}\n"
        f"当前描述：{'（空 — 请全新生成）' if not current else current}"
    )

    try:
        client = build_llm_client_from_org_provider(
            provider, model=org.system_hub_model
        )
        resp = await client.complete(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_block},
            ],
            max_tokens=800,
            temperature=0.5,
            model=org.system_hub_model,
        )
    except LLMError as exc:
        raise ValidationError(
            "system_hub.generation_failed",
            exc.message_key,
            exc.message,
        ) from exc

    text = (resp.content or "").strip()
    if not text:
        raise ValidationError(
            "system_hub.empty_response",
            "errors.system_hub.empty_response",
            "System hub returned an empty description",
        )
    return GenerateDescriptionOut(description=text)
