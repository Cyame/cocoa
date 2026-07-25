"""Blackboard API routes.

P6 implements blackboard endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/blackboard", tags=["Blackboard"])
