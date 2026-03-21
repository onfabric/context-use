from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: str = Field(alias="Date")
    description: str = Field(alias="Description")
    money_out: str = Field("", alias="Money Out")
    money_in: str = Field("", alias="Money In")
    balance: str = Field("", alias="Balance")
