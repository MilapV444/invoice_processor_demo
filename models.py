from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


EXTRACTION_FIELDS = (
    "vendor",
    "invoice_no",
    "date",
    "po_ref",
    "line_items",
    "subtotal",
    "tax",
    "total",
)


class LineItem(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class Invoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor: str | None = None
    invoice_no: str | None = None
    date: str | None = None
    po_ref: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    confidence: dict[str, float]

    @model_validator(mode="after")
    def confidence_covers_every_field(self) -> "Invoice":
        missing = set(EXTRACTION_FIELDS) - set(self.confidence)
        unexpected = set(self.confidence) - set(EXTRACTION_FIELDS)
        if missing or unexpected:
            raise ValueError(
                f"Confidence keys must match extraction fields; missing={sorted(missing)}, "
                f"unexpected={sorted(unexpected)}"
            )
        return self
