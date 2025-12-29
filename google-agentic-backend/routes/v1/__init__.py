from fastapi import APIRouter
from .auth.auth import router as auth_router
from .playground.playground import router as playground_router


v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(playground_router)