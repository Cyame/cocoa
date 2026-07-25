"""Messaging API routes.

P5 implements messaging endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/messaging", tags=["Messaging"])
