from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    profile_image_url: str | None
    is_email_verified: bool
    is_admin: bool
    created_at: datetime | None
    # 소셜 로그인(구글/깃허브)·게스트 계정은 password_hash가 없다 - 프론트가 이
    # 값으로 "비밀번호 변경" 메뉴나 탈퇴 시 비밀번호 입력란을 보여줄지 정한다
    # (auth_provider 문자열을 프론트가 직접 나열해서 판단하지 않도록, 실제로
    # 비밀번호가 있는지만 딱 알려준다).
    has_password: bool


class UsageSummaryResponse(BaseModel):
    consultation_count: int
    last_consultation_at: datetime | None


class DeleteAccountRequest(BaseModel):
    # 소셜 로그인/게스트 계정은 비밀번호가 없어서 생략 가능하다(MyPageService.
    # delete_account가 has_password 여부로 검증을 건너뜀).
    password: str | None = Field(default=None, min_length=1)


class DeleteAccountResponse(BaseModel):
    message: str


class DeleteConsultationsResponse(BaseModel):
    message: str
    deleted_count: int


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class LinkGuestHistoryRequest(BaseModel):
    # 로그인 직전까지 쓰던 게스트 토큰. 로그인/회원가입 자체와는 무관한 별도
    # 호출이라, 유효하지 않거나 이미 만료된 토큰이 와도 로그인 흐름을 막지 않는다
    # (AuthService.link_guest_history가 조용히 0건 처리).
    guest_token: str


class LinkGuestHistoryResponse(BaseModel):
    linked_conversation_count: int
