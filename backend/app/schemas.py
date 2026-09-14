from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class PartyInput(Input):
    name: str = Field(min_length=1, max_length=80)
    size: StrictInt = Field(ge=1, le=30)


class PartyEdit(PartyInput):
    version: StrictInt = Field(ge=1)


class ActionInput(Input):
    action: Literal["ready", "seat", "no_show", "cancel", "return", "undo"]
    version: StrictInt = Field(ge=1)


class SettingsInput(Input):
    is_open: StrictBool
    version: StrictInt = Field(ge=1)
