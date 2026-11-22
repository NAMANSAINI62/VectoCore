from fastapi import APIRouter
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.users import router as users_router
from app.api.v1.endpoints.chatbot import router as chatbot_router
from app.api.v1.endpoints.cache import router as cache_router

api_router = APIRouter()

# Register API v1 routers
api_router.include_router(health_router, prefix="", tags=["Health"])
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(chatbot_router)
api_router.include_router(cache_router)
