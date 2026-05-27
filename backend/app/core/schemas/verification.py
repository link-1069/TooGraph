from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VerificationCommand(BaseModel):
    name: str = ""
    command: str = Field(..., min_length=1)
    args: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True, extra="forbid")
