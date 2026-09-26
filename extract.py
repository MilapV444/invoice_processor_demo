import base64
import json
import os
from pathlib import Path

from models import Invoice


MODEL = "claude-sonnet-5"

EXTRACTION_PROMPT = """
Extract the invoice into JSON only. Do not make an approval, rejection, or hold decision.
Use null for a missing scalar value and [] for missing line items. Amounts are INR.
Missing means the field is not printed on the document at all. If a field is printed but
hard to read (blurred, smudged, cut off), return your best reading instead of null and give it
a low confidence. Confidence reflects how legibly the field itself is printed; if you had to
work a value out from other fields (for example, summing line items), confidence must be below 0.5.
Confidence must contain exactly these keys, with a number from 0.0 to 1.0 for every key:
vendor, invoice_no, date, po_ref, line_items, subtotal, tax, total.

Return this shape:
{
  "vendor": "string or null",
  "invoice_no": "string or null",
  "date": "YYYY-MM-DD or null",
  "po_ref": "string or null",
  "line_items": [{
    "description": "string",
    "quantity": 0,
    "unit_price": 0,
    "amount": 0
  }],
  "subtotal": 0,
  "tax": 0,
  "total": 0,
  "confidence": {
    "vendor": 0.0,
    "invoice_no": 0.0,
    "date": 0.0,
    "po_ref": 0.0,
    "line_items": 0.0,
    "subtotal": 0.0,
    "tax": 0.0,
    "total": 0.0
  }
}
""".strip()


def _api_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        import streamlit as st

        key = st.secrets.get("ANTHROPIC_API_KEY")
    except (ImportError, FileNotFoundError):
        key = None
    if not key:
        raise RuntimeError(
            "No Anthropic API key found. Add ANTHROPIC_API_KEY to .streamlit/secrets.toml "
            "or set it as an environment variable."
        )
    return key


def _json_object(response_text: str) -> dict[str, object]:
    text = response_text.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start = text.find("{")
    if start == -1:
        raise ValueError("Claude response did not contain a JSON object")
    value, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(value, dict):
        raise ValueError("Claude response JSON was not an object")
    return value


def extract_invoice(pdf_path: str | Path, api_key: str | None = None) -> Invoice:
    """Extract one invoice PDF into validated structured data."""
    path = Path(pdf_path)
    if path.suffix.lower() != ".pdf":
        raise ValueError("Input must be a PDF")
    if not path.is_file():
        raise FileNotFoundError(path)

    document = base64.b64encode(path.read_bytes()).decode("ascii")
    from anthropic import Anthropic

    client = Anthropic(
        api_key=api_key or _api_key(),
        default_headers={"Accept-Encoding": "identity"},
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": document,
                    },
                },
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    )
    text_blocks = [block.text for block in response.content if block.type == "text"]
    if not text_blocks:
        raise ValueError("Claude returned no text extraction")
    return Invoice.model_validate(_json_object("\n".join(text_blocks)))


if __name__ == "__main__":
    import sys

    print(extract_invoice(sys.argv[1]).model_dump_json(indent=2))