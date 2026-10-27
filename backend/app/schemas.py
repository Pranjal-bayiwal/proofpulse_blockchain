import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from .security import password_problems

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


class RegisterIn(BaseModel):
    username: str
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    organization: str | None = Field(default=None, max_length=120)
    password: str

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        v = v.strip()
        if not USERNAME_RE.match(v):
            raise ValueError("Username must be 3-32 characters: letters, digits, dot, dash or underscore")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        problems = password_problems(v)
        if problems:
            raise ValueError("Password needs " + ", ".join(problems))
        return v

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        return v.strip()


class LoginIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)  # username or email
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v: str) -> str:
        problems = password_problems(v)
        if problems:
            raise ValueError("Password needs " + ", ".join(problems))
        return v


class ApprovalRequestIn(BaseModel):
    approvers: list[str] = Field(min_length=1, max_length=10)  # usernames
    version_no: int | None = None


class DecisionIn(BaseModel):
    approve: bool
    comment: str = Field(default="", max_length=500)


class RevokeIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class HashVerifyIn(BaseModel):
    sha256: str

    @field_validator("sha256")
    @classmethod
    def _hex(cls, v: str) -> str:
        v = v.strip().lower().removeprefix("0x")
        if not re.fullmatch(r"[0-9a-f]{64}", v):
            raise ValueError("Expected a 64-character SHA-256 hex string")
        return v


class UserAdminPatch(BaseModel):
    is_active: bool | None = None
    role: str | None = Field(default=None, pattern="^(user|admin)$")
