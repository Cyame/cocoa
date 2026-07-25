"""Employee API routes.

P4 implements CRUD endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/employees", tags=["Employees"])
