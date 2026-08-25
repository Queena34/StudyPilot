from fastapi import APIRouter

from app.api.v1.routes import courses, documents, practice, progress, system, tutor

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(courses.router, prefix="/courses", tags=["courses"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(tutor.router, prefix="/courses", tags=["tutor"])
api_router.include_router(practice.router, tags=["practice"])
api_router.include_router(progress.router, prefix="/courses", tags=["progress"])
