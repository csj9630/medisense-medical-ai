from pydantic import BaseModel, Field, model_validator


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
    new_password_confirm: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.new_password_confirm:
            raise ValueError("새 비밀번호 확인이 일치하지 않습니다.")
        return self


class ChangePasswordResponse(BaseModel):
    message: str
