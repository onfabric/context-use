from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(alias="Type")
    product: str = Field(alias="Product")
    started_date: str = Field(alias="Started Date")
    completed_date: str = Field("", alias="Completed Date")
    description: str = Field(alias="Description")
    amount: str = Field(alias="Amount")
    fee: str = Field(alias="Fee")
    currency: str = Field(alias="Currency")
    state: str = Field(alias="State")
    balance: str = Field("", alias="Balance")
