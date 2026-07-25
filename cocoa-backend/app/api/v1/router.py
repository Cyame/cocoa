"""Version 1 API aggregation router.

Sub-routers are registered by P4-P10. P3 provides only the aggregation point.
"""

from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")
