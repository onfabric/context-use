from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cardmember: str = Field(alias="Cardmember")
    transaction_date: str = Field(alias="Transaction Date")
    process_date: str = Field(alias="Process Date")
    description: str = Field(alias="Description")
    foreign_spend_amount: str = Field("", alias="Foreign Spend Amount")
    foreign_spend_currency: str = Field("", alias="Foreign Spend Currency")
    amount: str = Field(alias="Amount")
    cr: str = Field("", alias="CR")
