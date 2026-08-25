from fastapi import APIRouter

from app.api.v1.routes import courses, system

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(courses.router, prefix="/courses", tags=["courses"])

