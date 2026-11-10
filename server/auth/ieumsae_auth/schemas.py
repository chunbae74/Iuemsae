from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class EmailCodeReq(Strict):
    email: EmailStr
    purpose: Literal["signup"] = "signup"


class EmailVerifyReq(Strict):
    email: EmailStr
    purpose: Literal["signup"] = "signup"
    code: str = Field(pattern=r"^\d{6}$")


class Consents(Strict):
    terms: bool
    privacy: bool
    sensitiveVoice: bool
    sensitiveProfile: bool = False
    ttsOverseas: bool = False


class Communication(Strict):


    speechLevel: int | None = Field(default=None, ge=1, le=3)
    comprehensionLevel: int | None = Field(default=None, ge=1, le=3)
    showToListener: bool = True


class SignupReq(Strict):
    loginId: str = Field(min_length=4, max_length=20)
    password: str = Field(min_length=1, max_length=64)
    emailToken: str = Field(max_length=2048)
    consents: Consents
    communication: Communication | None = None


class CommunicationUpdateReq(Communication):
    consent: bool


class TtsConsentReq(Strict):
    agree: bool


class LoginReq(Strict):
    loginId: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=64)

    deviceId: str | None = Field(default=None, max_length=36)


class RefreshReq(Strict):
    refreshToken: str = Field(max_length=128)


class PasswordChangeReq(Strict):
    currentPassword: str = Field(min_length=1, max_length=64)
    newPassword: str = Field(min_length=1, max_length=64)


class FindIdReq(Strict):
    email: EmailStr


class ResetRequestReq(Strict):
    loginId: str = Field(min_length=1, max_length=20)
    email: EmailStr


class ResetConfirmReq(Strict):
    loginId: str = Field(min_length=1, max_length=20)
    code: str = Field(pattern=r"^\d{6}$")
    newPassword: str = Field(min_length=1, max_length=64)


class DeviceRegisterReq(Strict):
    challenge: str = Field(max_length=128)
    publicKey: str = Field(max_length=512)
    keyAttestationChain: list[str] = Field(min_length=1, max_length=8)
    integrityToken: str | None = Field(default=None, max_length=8192)
    sdkInt: int = Field(ge=21, le=100)


class DeleteUserReq(Strict):
    password: str = Field(min_length=1, max_length=64)
