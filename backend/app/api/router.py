from fastapi import APIRouter

from app.api.admin.dashboard_router import router as admin_dashboard_router
from app.api.admin.router import router as admin_router
from app.api.admin.upload_router import router as admin_upload_router
from app.api.auth.oauth_router import oauth_start_router
from app.api.auth.router import router as auth_router
from app.api.auth.email_verification_router import router as email_verification_router
from app.api.auth.password_reset_router import router as password_reset_router
from app.api.auth.password_change_router import router as password_change_router
from app.api.auth.profile_router import router as profile_router
from app.api.auth.mypage_router import router as mypage_router
from app.api.auth.signup_router import router as signup_router
from app.api.consultation.router import router as consultation_router
from app.api.conversations.router import router as conversations_router
from app.api.documents.router import router as documents_router
from app.api.evaluations.router import router as evaluations_router
from app.api.llm.router import router as llm_router
from app.api.rag.router import router as rag_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(oauth_start_router, prefix="/auth/oauth", tags=["auth"])
api_router.include_router(signup_router, prefix="/auth", tags=["auth"])
api_router.include_router(email_verification_router, prefix="/auth", tags=["auth"])
api_router.include_router(password_reset_router, prefix="/auth", tags=["auth"])
api_router.include_router(password_change_router, prefix="/auth", tags=["auth"])
api_router.include_router(profile_router, prefix="/auth", tags=["auth"])
api_router.include_router(mypage_router, prefix="/auth", tags=["auth"])
api_router.include_router(conversations_router, prefix="/conversations", tags=["conversations"])
api_router.include_router(documents_router, prefix="/documents", tags=["documents"])
api_router.include_router(consultation_router, prefix="/consultation", tags=["consultation"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(admin_upload_router, prefix="/admin", tags=["admin"])
api_router.include_router(admin_dashboard_router, prefix="/admin/dashboard", tags=["admin", "dashboard"])
api_router.include_router(evaluations_router, prefix="/evaluations", tags=["evaluations"])
api_router.include_router(llm_router, prefix="/llm", tags=["llm"])
api_router.include_router(rag_router, prefix="/rag", tags=["rag"])
