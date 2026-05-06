"""Student profile API for progress tracking."""
from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import JSONResponse

from ..services import profile_service


router = APIRouter(prefix="/api/profile", tags=["profile-api"])


@router.get("/progress")
async def get_profile_progress(request: Request):
    """Get progress data for the logged-in student's profile."""
    profile_token = request.cookies.get(profile_service.PROFILE_COOKIE)
    if not profile_token:
        raise HTTPException(status_code=401, detail="not logged in")
    
    profile = profile_service.get_profile_by_token(profile_token)
    if not profile:
        raise HTTPException(status_code=404, detail="profile not found")
    
    progress = profile_service.get_profile_progress_data(profile["id"])
    return JSONResponse(content={
        "profile": profile,
        "progress": progress,
    })