"""Office API routes.

P4 implements CRUD endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/offices", tags=["Offices"])
