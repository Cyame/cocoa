"""Resolve OrganizationProvider → env vars for Instance Host / pi."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base_class import BaseClass
from app.models.base_class_provider_default import BaseClassProviderDefault
from app.models.entity import Entity
from app.models.instance import Instance
from app.models.organization import Namespace, Organization
from app.models.organization_provider import OrganizationProvider
from app.services.llm.org_provider import resolve_api_key

logger = logging.getLogger(__name__)

# Map Eyot / models.dev provider ids → pi env API key names
# (see @earendil-works/pi-coding-agent docs/providers.md).
_PROVIDER_ENV_KEYS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "google": "GEMINI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "xai": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together": "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "kimi": "KIMI_API_KEY",
    "kimi-coding": "KIMI_API_KEY",
}


def _pi_env_key_for_provider(provider: OrganizationProvider) -> str:
    candidates = [
        (provider.catalog_provider_id or "").lower(),
        (provider.slug or "").lower(),
        (provider.name or "").lower(),
    ]
    for raw in candidates:
        if raw in _PROVIDER_ENV_KEYS:
            return _PROVIDER_ENV_KEYS[raw]
        for key, env_name in _PROVIDER_ENV_KEYS.items():
            if key in raw:
                return env_name
    # OpenAI-compatible / unknown → OPENAI_API_KEY (+ base URL)
    if provider.request_format in ("completion", "response"):
        return "OPENAI_API_KEY"
    if provider.request_format == "anthropic":
        return "ANTHROPIC_API_KEY"
    if provider.request_format == "gemini":
        return "GEMINI_API_KEY"
    return "OPENAI_API_KEY"


def _pi_provider_id(provider: OrganizationProvider) -> str:
    return (provider.catalog_provider_id or provider.slug or "openai").strip()


def provider_to_pi_env(
    provider: OrganizationProvider,
    *,
    model: str | None = None,
) -> dict[str, str]:
    """Build pod env so ``pi --mode rpc`` can authenticate."""
    try:
        api_key = resolve_api_key(provider.api_key_ref)
    except Exception as exc:  # noqa: BLE001
        logger.warning("resolve_api_key failed for provider=%s: %s", provider.id, exc)
        return {}

    env_name = _pi_env_key_for_provider(provider)
    out: dict[str, str] = {env_name: api_key}

    # Dual-write common aliases so openai-compatible gateways still work.
    if env_name != "OPENAI_API_KEY" and provider.request_format in (
        "completion",
        "response",
    ):
        out.setdefault("OPENAI_API_KEY", api_key)

    if provider.base_url:
        out["OPENAI_BASE_URL"] = provider.base_url.rstrip("/")
        # pi custom / openai-compatible often honors this too
        out["PI_BASE_URL"] = provider.base_url.rstrip("/")

    model_id = (model or provider.default_model or "").strip()
    provider_id = _pi_provider_id(provider)
    if model_id:
        out["PI_MODEL"] = model_id
        # Prefer provider/model form when not already namespaced
        if "/" not in model_id:
            out["PI_MODEL"] = f"{provider_id}/{model_id}"
    out["PI_PROVIDER"] = provider_id
    return out


async def _load_org_for_instance(
    db: AsyncSession, instance: Instance
) -> Organization | None:
    entity = await db.get(Entity, instance.entity_id)
    if entity is None or entity.deleted_at is not None:
        return None
    ns = await db.get(Namespace, entity.namespace_id)
    if ns is None or ns.deleted_at is not None:
        return None
    return await db.get(Organization, ns.org_id)


async def resolve_provider_for_instance(
    db: AsyncSession, instance_id: str
) -> tuple[OrganizationProvider | None, str | None]:
    """Pick (provider, model) for an Instance: BaseClass default → org system hub."""
    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        return None, None

    entity = await db.get(Entity, instance.entity_id)
    if entity is None or entity.deleted_at is not None:
        return None, None

    # 1) BaseClass provider default via preset_slug
    if entity.preset_slug:
        bc = (
            await db.execute(
                select(BaseClass).where(
                    BaseClass.slug == entity.preset_slug,
                    BaseClass.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if bc is not None:
            binding = (
                await db.execute(
                    select(BaseClassProviderDefault).where(
                        BaseClassProviderDefault.base_class_id == bc.id,
                        BaseClassProviderDefault.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if binding is not None:
                provider = await db.get(OrganizationProvider, binding.provider_id)
                if (
                    provider is not None
                    and provider.deleted_at is None
                    and provider.enabled
                ):
                    return provider, binding.model

    # 2) Org system hub / cerebellum default
    org = await _load_org_for_instance(db, instance)
    if org is None or org.deleted_at is not None:
        return None, None

    for pid, model in (
        (org.system_hub_provider_id, org.system_hub_model),
        (org.cerebellum_default_provider_id, org.cerebellum_default_model),
    ):
        if not pid:
            continue
        provider = await db.get(OrganizationProvider, pid)
        if provider is None or provider.deleted_at is not None or not provider.enabled:
            continue
        return provider, model or provider.default_model

    # 3) Any enabled org provider
    row = (
        await db.execute(
            select(OrganizationProvider)
            .where(
                OrganizationProvider.organization_id == org.id,
                OrganizationProvider.enabled.is_(True),
                OrganizationProvider.deleted_at.is_(None),
            )
            .order_by(OrganizationProvider.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None, None
    return row, row.default_model


async def resolve_pi_env_for_instance(
    db: AsyncSession, instance_id: str
) -> dict[str, str]:
    """Env fragment injected into Instance pods for pi auth + model."""
    provider, model = await resolve_provider_for_instance(db, instance_id)
    if provider is None:
        logger.info("no org provider for instance_id=%s; pi env empty", instance_id)
        return {}
    env = provider_to_pi_env(provider, model=model)
    logger.info(
        "pi env resolved instance_id=%s provider=%s model=%s keys=%s",
        instance_id,
        provider.slug,
        env.get("PI_MODEL"),
        sorted(k for k in env if k.endswith("_KEY") or k.endswith("_TOKEN")),
    )
    return env


def redact_env_for_snapshot(env: dict[str, Any]) -> dict[str, Any]:
    """Avoid persisting raw API keys in DeployRecord.config_snapshot."""
    out: dict[str, Any] = {}
    for k, v in env.items():
        key_u = str(k).upper()
        if any(s in key_u for s in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            out[k] = "***"
        else:
            out[k] = v
    return out
