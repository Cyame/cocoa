"""Instance API routes.

P7 implements lifecycle endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/instances", tags=["Instances"])
