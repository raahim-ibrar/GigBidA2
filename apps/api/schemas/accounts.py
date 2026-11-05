from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return str(value).casefold()


class Account(BaseModel):
    id: str
    email: str
    csrf_token: str


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=100)
    persona: Literal["own", "ai_ml", "full_stack", "data_analyst"] = "own"
    hourly_floor: Decimal = Field(gt=0, le=100000, decimal_places=2)
    weekly_connects_budget: int = Field(ge=0, le=100000)
    saved_searches: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("display_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A display name is required")
        return value.strip()

    @field_validator("saved_searches")
    @classmethod
    def clean_searches(cls, values: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 500 for item in values):
            raise ValueError("Searches must be non-empty and no longer than 500 characters")
        return list(dict.fromkeys(item.strip() for item in values))


class Profile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    display_name: str
    persona: str
    hourly_floor: Decimal
    weekly_connects_budget: int
    saved_searches: list[str]
    onboarding_complete: bool
