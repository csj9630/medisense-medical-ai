import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.generated import Users


class AuthRepository:
    """인증 기능에 필요한 DB 접근만 담당합니다."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def find_user_by_email(self, email: str) -> Users | None:
        return self.db.scalar(select(Users).where(Users.email == email))

    def find_user_by_id(self, user_id: str) -> Users | None:
        return self.db.get(Users, UUID(user_id))

    def find_user_by_oauth(self, provider: str, oauth_id: str) -> Users | None:
        return self.db.scalar(
            select(Users).where(Users.auth_provider == provider, Users.oauth_id == oauth_id)
        )

    def create_oauth_user(
        self, *, provider: str, oauth_id: str, email: str, profile_image_url: str | None
    ) -> Users:
        # Google/GitHub가 이미 이메일 소유를 검증했으므로 is_email_verified=True로
        # 바로 시작한다(로컬 회원가입처럼 별도 이메일 인증 절차가 필요 없음).
        user = Users(
            email=email,
            password_hash=None,
            auth_provider=provider,
            oauth_id=oauth_id,
            profile_image_url=profile_image_url,
            is_email_verified=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def link_oauth_identity(
        self, user: Users, *, provider: str, oauth_id: str, profile_image_url: str | None
    ) -> Users:
        """이미 다른 방식(로컬 비밀번호 또는 다른 OAuth provider)으로 가입된
        이메일에 새 provider를 연결한다. 로컬 회원가입(이메일 인증 필수)과
        Google/GitHub(그쪽에서 이미 검증한 이메일만 받음) 전부 "그 이메일의 실제
        소유자"라는 걸 이미 증명한 상태라, 같은 이메일이면 같은 사람으로 보고
        자동으로 이어준다 - 처음엔 자동 병합을 안 했었는데(계정 탈취 우려), 실제로
        본인이 Google/GitHub 둘 다 같은 이메일을 쓰는 흔한 경우에 로그인 자체가
        막혀서 오히려 더 큰 문제였다(2026-09-03 실사용 중 발견).

        주의: `auth_provider`/`oauth_id` 컬럼이 사용자당 하나뿐이라(스키마상
        provider를 여러 개 동시에 저장 못 함), 이 함수를 부를 때마다 "가장 최근에
        로그인에 사용한 방식"으로 덮어쓴다. 로컬 비밀번호 로그인은 password_hash만
        보므로 이 컬럼이 바뀌어도 영향받지 않는다 - password_hash는 안 건드린다.
        """
        user.auth_provider = provider
        user.oauth_id = oauth_id
        user.is_email_verified = True
        if profile_image_url:
            user.profile_image_url = profile_image_url
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete_user(self, user: Users) -> None:
        self.db.delete(user)
        self.db.commit()

    def create_guest_user(self) -> Users:
        # 로그인 수단이 없는 임시 계정. email UNIQUE 제약을 만족시키려고 플레이스홀더
        # 도메인 + uuid를 쓴다 (실제로 발송/수신되지 않는 주소).
        # 주의: .local/.invalid/.test 등은 email-validator가 예약 도메인으로 막아버려서
        # (EmailStr 검증 실패) 못 쓴다 — .internal은 통과한다.
        placeholder_email = f"guest-{uuid.uuid4()}@guest.thegpt.internal"
        user = Users(
            email=placeholder_email,
            password_hash=None,
            auth_provider="guest",
            is_email_verified=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
