from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    model_config = ConfigDict(extra="ignore")

    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class Invoice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vendor: str | None = None
    invoice_no: str | None = None
    date: str | None = None
    po_ref: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    confidence: dict[str, float]

    @field_validator("line_items", mode="before")
    @classmethod
    def null_line_items_means_none(cls, value: object) -> object:
        return [] if value is None else value

    @model_validator(mode="after")
    def confidence_covers_every_field(self) -> "Invoice":
        # A field Claude gave no confidence for is treated as unreadable (0.0),
        # so the confidence rule holds it for a human instead of crashing.
        self.confidence = {name: self.confidence.get(name, 0.0) for name in EXTRACTION_FIELDS}
        return self
