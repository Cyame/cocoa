"""Learning API routes.

P10 implements learning endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/learning", tags=["Learning"])
