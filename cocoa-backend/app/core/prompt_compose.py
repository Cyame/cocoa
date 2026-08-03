"""Compose Instance SYSTEM prompt: BaseClass template + Entity role; caps from Entity.

World hub (org system hub / cerebellum LLM) may reorganize the draft into a
coherent SYSTEM.md. Fallback is the deterministic scaffold.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_COMPOSE_INSTRUCTIONS = """你是 Cocoa 世界中枢。请把下面的结构化素材整理成一份化身 SYSTEM 提示词（Markdown）。

硬性要求：
1. 神职（BaseClass）只是静态模板：说明「运行形式 / 思维模式」，不要把它当成实时能力清单。
2. 眷族（Entity）才是身份主体：角色、职责、场景目标必须以眷族为准。
3. 能力与基因系统必须全部继承自眷族列出的内容；禁止把神职默认能力/基因并进生效清单。
4. 输出只要最终 SYSTEM 正文，不要前言、不要解释你的整理过程。
"""


def _knowledge_block(knowledge) -> str:
    """Render the ``## 知识`` section body from resolved knowledge entries.

    Each entry is rendered as ``- {title}：{body}`` (falling back to whichever
    of title / body is present). Accepts plain dicts (API items) or ORM
    objects; the body is inserted verbatim as inert scaffold text.
    """
    if not knowledge:
        return ""
    lines: list[str] = []
    for item in knowledge:
        if isinstance(item, dict):
            title = item.get("title") or ""
            body = item.get("body") or ""
        else:
            title = getattr(item, "title", None) or ""
            body = getattr(item, "body", None) or ""
        if title and body:
            lines.append(f"- {title}：{body}")
        elif title:
            lines.append(f"- {title}")
        elif body:
            lines.append(f"- {body}")
    return "\n".join(lines)


def build_prompt_scaffold(
    agent_config: dict[str, Any], *, knowledge=None
) -> str:
    """Deterministic SYSTEM.md scaffold (no LLM).

    *knowledge* is an optional iterable of resolved knowledge entries
    (dicts or ORM objects with ``key`` / ``title`` / ``body`` / ``scope``);
    when provided, a ``## 知识`` section is appended. Backward compatible:
    callers that omit it get the previous scaffold verbatim.
    """
    base_name = agent_config.get("baseclass_name") or agent_config.get("baseclass_slug") or "神职"
    base_form = (
        agent_config.get("baseclass_operating_form")
        or agent_config.get("baseclass_template_prompt")
        or ""
    ).strip()
    entity_name = agent_config.get("entity_name") or agent_config.get("entity_slug") or "眷族"
    entity_role = (
        agent_config.get("entity_role_prompt")
        if agent_config.get("entity_role_prompt") is not None
        else agent_config.get("system_prompt")
    )
    entity_role_text = (entity_role or "").strip() or f"你是眷族「{entity_name}」。"
    caps = agent_config.get("default_capabilities") or []
    genes = agent_config.get("default_gene_refs") or []

    caps_block = (
        "\n".join(f"- {json.dumps(c, ensure_ascii=False) if not isinstance(c, str) else c}" for c in caps)
        if caps
        else "- （眷族未配置能力）"
    )
    genes_block = (
        "\n".join(f"- {g}" for g in genes) if genes else "- （眷族未配置基因）"
    )

    knowledge_block = _knowledge_block(knowledge)
    knowledge_section = (
        f"## 知识\n\n{knowledge_block}\n\n" if knowledge_block else ""
    )

    return (
        f"# 身份\n\n"
        f"你是眷族 **{entity_name}**。"
        f"神职 **{base_name}** 仅提供静态运行形式模板，不是你的能力来源。\n\n"
        f"## 神职运行形式（静态模板）\n\n"
        f"{base_form or '（无额外模板说明）'}\n\n"
        f"## 眷族角色与职责\n\n"
        f"{entity_role_text}\n\n"
        f"## 能力（仅继承自眷族）\n\n"
        f"{caps_block}\n\n"
        f"## 基因（仅继承自眷族）\n\n"
        f"{genes_block}\n\n"
        f"{knowledge_section}"
    )


async def compose_system_prompt_with_world_hub(
    db: AsyncSession,
    *,
    instance_id: str,
    agent_config: dict[str, Any],
) -> str:
    """Return SYSTEM.md body: world-hub LLM polish when available, else scaffold."""
    knowledge = None
    try:
        from app.core.knowledge import resolve_knowledge_for_instance
        from app.models.instance import Instance

        inst = await db.get(Instance, instance_id)
        if inst is not None and inst.deleted_at is None:
            knowledge = await resolve_knowledge_for_instance(db, inst)
    except Exception:  # noqa: BLE001
        logger.exception(
            "knowledge resolve failed; scaffold without it instance_id=%s",
            instance_id,
        )
    scaffold = build_prompt_scaffold(agent_config, knowledge=knowledge)
    try:
        from app.services.llm.instance_pi_env import resolve_provider_for_instance
        from app.services.llm.org_provider import build_llm_client_from_org_provider

        provider, model = await resolve_provider_for_instance(db, instance_id)
        if provider is None:
            return scaffold
        client = build_llm_client_from_org_provider(provider, model=model)
        user_content = (
            f"{_COMPOSE_INSTRUCTIONS}\n\n"
            f"## 素材\n\n{scaffold}\n\n"
            f"## agent_config JSON\n\n"
            f"```json\n{json.dumps(agent_config, ensure_ascii=False, indent=2)[:12000]}\n```\n"
        )
        resp = await client.complete(
            messages=[
                {"role": "system", "content": "You organize Cocoa Instance SYSTEM prompts."},
                {"role": "user", "content": user_content},
            ],
            model=model or provider.default_model,
        )
        text = (resp.content or "").strip()
        if text:
            logger.info(
                "world-hub composed SYSTEM.md instance_id=%s chars=%s",
                instance_id,
                len(text),
            )
            return text
    except Exception:  # noqa: BLE001
        logger.exception(
            "world-hub prompt compose failed; using scaffold instance_id=%s",
            instance_id,
        )
    return scaffold


def pi_project_settings_json() -> str:
    """Project ``.pi/settings.json`` — minimal; RPC trust via ``--approve`` + global."""
    return json.dumps({"compaction": {"enabled": False}}, indent=2) + "\n"


def pi_global_settings_json() -> str:
    """Global ``~/.pi/agent/settings.json`` so RPC loads project ``.pi`` resources."""
    return json.dumps({"defaultProjectTrust": "always"}, indent=2) + "\n"
