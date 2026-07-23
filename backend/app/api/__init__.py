from fastapi import APIRouter

from app.api import files, jobs

api_router = APIRouter()
api_router.include_router(jobs.router)
api_router.include_router(files.router)
