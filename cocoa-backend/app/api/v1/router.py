"""Version 1 API aggregation router.

Sub-routers are registered by P4-P10. P3 provides only the aggregation point.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.blackboard import router as blackboard_router
from app.api.v1.corridor_node import router as corridor_node_router
from app.api.v1.deploy import router as deploy_router
from app.api.v1.employee_presets import router as employee_presets_router
from app.api.v1.employees import router as employees_router
from app.api.v1.events import router as events_router
from app.api.v1.harness import router as harness_router
from app.api.v1.instances import router as instances_router
from app.api.v1.learning import router as learning_router
from app.api.v1.memory import router as memory_router
from app.api.v1.messaging import router as messaging_router
from app.api.v1.office_live_status import router as office_live_status_router
from app.api.v1.offices import router as offices_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(blackboard_router)
api_router.include_router(corridor_node_router)
api_router.include_router(deploy_router)
api_router.include_router(employee_presets_router)
api_router.include_router(employees_router)
api_router.include_router(events_router)
api_router.include_router(harness_router)
api_router.include_router(instances_router)
api_router.include_router(learning_router)
api_router.include_router(memory_router)
api_router.include_router(messaging_router)
api_router.include_router(office_live_status_router)
api_router.include_router(offices_router)
