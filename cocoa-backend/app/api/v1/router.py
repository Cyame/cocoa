"""Version 1 API aggregation router (PRD-v2 paths)."""

from fastapi import APIRouter

from app.api.v1.ai_genes import router as ai_genes_router
from app.api.v1.account import router as account_router
from app.api.v1.auth import router as auth_router
from app.api.v1.base_classes import router as base_classes_router
from app.api.v1.central_hubs import router as central_hubs_router
from app.api.v1.composer import router as composer_router
from app.api.v1.deploy import router as deploy_router
from app.api.v1.entities import router as entities_router
from app.api.v1.events import router as events_router
from app.api.v1.harness import router as harness_router
from app.api.v1.instances import router as instances_router
from app.api.v1.internal import router as internal_router
from app.api.v1.learning import router as learning_router
from app.api.v1.memory import router as memory_router
from app.api.v1.messaging import router as messaging_router
from app.api.v1.namespaces import router as namespaces_router
from app.api.v1.namespace_contracts import router as namespace_contracts_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.provider_catalog import router as provider_catalog_router
from app.api.v1.model_catalog import router as model_catalog_router
from app.api.v1.system_hub import router as system_hub_router
from app.api.v1.tunnel import router as tunnel_router
from app.api.v1.user_genes import router as user_genes_router
from app.api.v1.users import router as users_router
from app.api.v1.workspace_live_status import router as workspace_live_status_router
from app.api.v1.workspaces import router as workspaces_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(account_router)
api_router.include_router(auth_router)
api_router.include_router(ai_genes_router)
api_router.include_router(base_classes_router)
api_router.include_router(central_hubs_router)
api_router.include_router(composer_router)
api_router.include_router(deploy_router)
api_router.include_router(entities_router)
api_router.include_router(events_router)
api_router.include_router(harness_router)
api_router.include_router(instances_router)
api_router.include_router(internal_router)
api_router.include_router(learning_router)
api_router.include_router(memory_router)
api_router.include_router(messaging_router)
api_router.include_router(model_catalog_router)
api_router.include_router(namespaces_router)
api_router.include_router(namespace_contracts_router)
api_router.include_router(organizations_router)
api_router.include_router(provider_catalog_router)
api_router.include_router(system_hub_router)
api_router.include_router(tunnel_router)
api_router.include_router(user_genes_router)
api_router.include_router(users_router)
api_router.include_router(workspace_live_status_router)
api_router.include_router(workspaces_router)
