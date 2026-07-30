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

_KIND_LABELS = {
    "entity": "眷属（Entity）",
    "world": "世界（Organization）",
    "namespace": "次元（Namespace）",
    "gene": "人类基因（UserGene）",
    "generic": "对象",
}

_COMMON_OUTPUT_RULES = (
    "输出约束：\n"
    "- 只输出最终 description 正文\n"
    "- 不要标题、不要 markdown、不要引号包裹整段、不要 emoji\n"
    "- 若提供了「当前描述」，在保留原意与关键事实的前提下改写得更清晰、具体；"
    "不要无故删掉已有专有名词\n"
    "- 不要编造未给出的组织机密、内部系统名或虚构细节"
)

_SYSTEM_PROMPTS: dict[str, str] = {
    "entity": (
        "你是 Cocoa 平台的文案助手（System 中枢）。\n"
        "任务：为眷属（Entity）写一段创建/编辑表单用的中文 description。\n\n"
        "内容重点：\n"
        "- 说清这个眷属的职能边界：擅长什么、不负责什么\n"
        "- 写清与人 / 其他眷属 / 空间主脑的协作方式\n"
        "- 语气专业、可执行；避免空泛口号\n"
        "- 约 50–400 字：职能简单可短，复杂可写满\n\n"
        f"{_COMMON_OUTPUT_RULES}"
    ),
    "world": (
        "你是 Cocoa 平台的文案助手（System 中枢）。\n"
        "任务：为世界（Organization）写一段设置页用的中文 description。\n\n"
        "内容重点：\n"
        "- 概括这个世界的定位：服务谁、覆盖什么业务/场景域\n"
        "- 点出治理边界（用户、次元、智能系统配置等）而不展开操作手册\n"
        "- 语气沉稳、偏组织说明，不要写成营销文案\n"
        "- 约 40–200 字\n\n"
        f"{_COMMON_OUTPUT_RULES}"
    ),
    "namespace": (
        "你是 Cocoa 平台的文案助手（System 中枢）。\n"
        "任务：为次元（Namespace）写一段创建/编辑表单用的中文 description。\n\n"
        "内容重点：\n"
        "- 说清这个次元承载的场景分区（例如编码协作、社媒运营、研究实验）\n"
        "- 点出空间 / 神职 / 眷属在此次元内大致如何协作\n"
        "- 与世界描述区分：世界是租户边界，次元是场景分区\n"
        "- 语气专业、可执行；约 40–250 字\n\n"
        f"{_COMMON_OUTPUT_RULES}"
    ),
    "gene": (
        "你是 Cocoa 平台的文案助手（System 中枢）。\n"
        "任务：为人类基因（UserGene / 权限包）写一段目录用的中文 description。\n\n"
        "内容重点：\n"
        "- 说明这个基因包授予什么能力范围、适合挂给谁\n"
        "- 若名称像 can_* 权限，按「单权限说明」写；若是身份包，按「管理层级」写\n"
        "- 不要罗列未给出的权限 slug；不要写成法律条款\n"
        "- 语气简洁、偏权限说明；约 30–150 字\n\n"
        f"{_COMMON_OUTPUT_RULES}"
    ),
    "generic": (
        "你是 Cocoa 平台的文案助手（System 中枢）。\n"
        "任务：根据名称与已有描述，产出一段简洁的中文 description，供创建/编辑表单使用。\n\n"
        "内容重点：\n"
        "- 紧扣名称与角色定位，写清用途与边界\n"
        "- 语气专业、可执行；避免空泛口号\n"
        "- 约 40–300 字\n\n"
        f"{_COMMON_OUTPUT_RULES}"
    ),
}


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

    kind = (body.kind or "entity").strip().lower()
    if kind not in _SYSTEM_PROMPTS:
        kind = "generic"
    system_prompt = _SYSTEM_PROMPTS[kind]
    current = (body.description or "").strip()
    user_block = (
        f"对象类型：{_KIND_LABELS[kind]}\n"
        f"名称：{body.name}\n"
        f"当前描述：{'（空 — 请全新生成）' if not current else current}"
    )

    try:
        client = build_llm_client_from_org_provider(
            provider, model=org.system_hub_model
        )
        resp = await client.complete(
            [
                {"role": "system", "content": system_prompt},
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
