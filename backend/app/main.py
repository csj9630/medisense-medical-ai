from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.admin.upload_router import register_upload_error_handlers
from app.api.auth.oauth_router import oauth_callback_router
from app.api.router import api_router
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger

logger = get_logger("main")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)
    # Google/GitHub OAuth 콜백은 /api 접두사 없이 루트에 마운트한다 - Google/GitHub
    # 콘솔에 등록한 redirect_uri(Cloudflare Worker가 그대로 프록시)와 경로가 정확히
    # 같아야 하기 때문이다(app/api/auth/oauth_router.py 상단 설명 참고).
    app.include_router(oauth_callback_router, tags=["auth"])
    register_upload_error_handlers(app)

    @app.exception_handler(Exception)
    async def log_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        # HTTPException(401/404/429 등 의도된 실패)은 여기까지 안 옴 — 진짜 버그/DB
        # 오류 같은 처리 못한 예외만 여기서 함수명(엔드포인트)+시각+에러내용으로 기록.
        logger.exception("처리되지 않은 예외: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "서버 오류가 발생했습니다."})

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/db", tags=["health"])
    def database_health_check(db: Session = Depends(get_db)) -> dict[str, str]:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}

    # 로컬 전용 OCR/RAG 실험 페이지 (backend/local_lab/, git에 안 올라감).
    # 팀원 로컬엔 이 폴더 자체가 없으니 없으면 조용히 건너뛴다 — 실수로 커밋되거나
    # 다른 사람 환경에서 import 에러로 서버가 죽는 일이 없게 하기 위함.
    if settings.app_env == "local":
        try:
            from local_lab.router import router as local_lab_router

            app.include_router(local_lab_router, prefix="/local-lab", tags=["local-lab"])
            logger.info("로컬 AI 랩 라우터 마운트됨: /local-lab")
        except ImportError:
            pass

    return app


app = create_app()
