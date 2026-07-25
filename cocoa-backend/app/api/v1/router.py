"""Version 1 API aggregation router.

Sub-routers are registered by P4-P10. P3 provides only the aggregation point.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.employee_presets import router as employee_presets_router
from app.api.v1.employees import router as employees_router
from app.api.v1.messaging import router as messaging_router
from app.api.v1.offices import router as offices_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(employee_presets_router)
api_router.include_router(employees_router)
api_router.include_router(offices_router)
api_router.include_router(messaging_router)
