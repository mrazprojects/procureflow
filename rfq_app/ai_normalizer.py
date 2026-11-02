
import re


MISSING_VALUES = {
    "",
    "none",
    "null",
    "unknown",
    "not stated",
    "not specified",
    "n/a",
    "na",
    "-",
}


def clean_text(value):
    """Convert a value into clean text without inventing missing data."""
    if value is None:
        return None

    text = str(value).strip()

    if text.lower() in MISSING_VALUES:
        return None

    return text


def parse_number(value):
    """
    Safely extract a numeric value.

    Examples:
    '1,250.50' -> 1250.50
    'AED 500'  -> 500.0
    '5%'       -> 5.0
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    if text.lower() in MISSING_VALUES:
        return None

    text = text.replace(",", "")

    match = re.search(r"-?\d+(?:\.\d+)?", text)

    if not match:
        return None

    try:
        return float(match.group())
    except (ValueError, TypeError):
        return None


def parse_vat(value):
    """
    Identify whether VAT is a percentage, fixed amount or unclear.

    Examples:
    '5%'       -> percentage
    'AED 50'   -> fixed
    '50'       -> unknown
    None       -> unknown
    """
    if value is None:
        return {
            "vat": None,
            "vat_type": "unknown",
            "vat_rate": None,
            "vat_raw": None,
            "vat_review_required": True,
        }

    raw = str(value).strip()

    if raw.lower() in MISSING_VALUES:
        return {
            "vat": None,
            "vat_type": "unknown",
            "vat_rate": None,
            "vat_raw": raw,
            "vat_review_required": True,
        }

    number = parse_number(raw)

    if number is None or number < 0:
        return {
            "vat": None,
            "vat_type": "unknown",
            "vat_rate": None,
            "vat_raw": raw,
            "vat_review_required": True,
        }

    if "%" in raw:
        return {
            "vat": number,
            "vat_type": "percentage",
            "vat_rate": number,
            "vat_raw": raw,
            "vat_review_required": False,
        }

    currency_codes = (
        "AED", "USD", "EUR", "GBP", "INR",
        "SAR", "QAR", "OMR", "BHD", "KWD",
    )

    upper_raw = raw.upper()

    if any(code in upper_raw for code in currency_codes):
        return {
            "vat": number,
            "vat_type": "fixed",
            "vat_rate": None,
            "vat_raw": raw,
            "vat_review_required": False,
        }

    return {
        "vat": number,
        "vat_type": "unknown",
        "vat_rate": None,
        "vat_raw": raw,
        "vat_review_required": True,
    }


def normalise_item(item, index, warnings):
    """Convert one AI-extracted quotation item into a standard structure."""

    if not isinstance(item, dict):
        warnings.append(
            f"Quotation item {index} has an invalid data structure."
        )
        return None

    description = clean_text(item.get("description"))

    if not description:
        warnings.append(
            f"Quotation item {index} has no description."
        )

    quantity = parse_number(item.get("quantity"))
    unit_price = parse_number(item.get("unit_price"))

    unit = clean_text(item.get("unit"))
    manufacturer = clean_text(item.get("manufacturer"))
    model = clean_text(item.get("model"))
    dimensions = clean_text(item.get("dimensions"))
    material = clean_text(item.get("material"))

    specifications = {}

    if dimensions:
        specifications["dimensions"] = dimensions

    if material:
        specifications["material"] = material

    if quantity is None:
        warnings.append(
            f"Quotation item {index}: quantity is missing or unclear."
        )

    if unit_price is None:
        warnings.append(
            f"Quotation item {index}: unit price is missing or unclear."
        )

    if not unit:
        warnings.append(
            f"Quotation item {index}: unit of measurement is missing."
        )

    missing_information = item.get("missing_information") or []

    if isinstance(missing_information, str):
        missing_information = [missing_information]

    clarification_points = item.get("clarification_points") or []

    if isinstance(clarification_points, str):
        clarification_points = [clarification_points]

    return {
        "description": description or f"Unidentified item {index}",
        "manufacturer": manufacturer,
        "model": model,
        "specifications": specifications,
        "quantity": quantity,
        "unit": unit,
        "unit_price": unit_price,
        "missing_information": missing_information,
        "clarification_points": clarification_points,
    }


def normalise_ai_quote(ai_data):
    """
    Convert Qwen AI extraction into ProcureFlow supplier format.

    Supports both direct and nested AI response structures.

    Missing information remains missing.
    No technical compliance or supplier ranking is performed here.
    """

    warnings = []

    if not isinstance(ai_data, dict):
        return {
            "success": False,
            "error": "AI response is not a valid JSON object.",
            "supplier_data": None,
            "warnings": warnings,
        }

    # Handle nested response returned by ai_extractor.py:
    # {"success": True, "data": {"supplier": "...", "items": [...]}}
    if isinstance(ai_data.get("data"), dict):
        ai_data = ai_data["data"]

    supplier = clean_text(ai_data.get("supplier"))
    quote_number = clean_text(ai_data.get("quote_number"))
    currency = clean_text(ai_data.get("currency"))

    if not supplier:
        warnings.append("Supplier name was not identified.")

    if not quote_number:
        warnings.append("Quotation number was not identified.")

    if not currency:
        warnings.append("Quotation currency was not identified.")

    # Commercial values
    freight_raw = ai_data.get("freight")
    discount_raw = ai_data.get("discount")

    freight = parse_number(freight_raw)
    discount = parse_number(discount_raw)

    if freight is None:
        warnings.append(
            "Freight is missing or unclear. Confirm whether freight is "
            "included, excluded or separately chargeable."
        )

    if discount is None:
        warnings.append(
            "Discount is missing or unclear. Confirm whether a discount "
            "applies."
        )

    if freight is not None and freight < 0:
        warnings.append("Freight value is negative and requires review.")
        freight = None

    if discount is not None and discount < 0:
        warnings.append("Discount value is negative and requires review.")
        discount = None

    # VAT
    vat_info = parse_vat(ai_data.get("vat_raw"))

    if vat_info["vat_review_required"]:
        warnings.append(
            "VAT is missing or its calculation basis is unclear. "
            "Manual verification is required."
        )

    # Quotation items
    raw_items = ai_data.get("items")

    if not isinstance(raw_items, list):
        warnings.append(
            "AI response does not contain a valid quotation items list."
        )
        raw_items = []

    items = []

    for index, item in enumerate(raw_items, start=1):
        normalised = normalise_item(item, index, warnings)

        if normalised:
            items.append(normalised)

    if not items:
        warnings.append(
            "No usable quotation items were extracted."
        )

    # Preserve AI clarification points
    clarification_points = ai_data.get("clarification_points") or []

    if isinstance(clarification_points, str):
        clarification_points = [clarification_points]

    if not isinstance(clarification_points, list):
        clarification_points = []
        warnings.append(
            "Quotation-level clarification points have an invalid format."
        )

    supplier_data = {
        "supplier": supplier or "Unknown supplier",
        "quote_number": quote_number,
        "currency": currency or "Not specified",

        "freight": freight,
        "discount": discount,

        "vat": vat_info["vat"],
        "vat_type": vat_info["vat_type"],
        "vat_rate": vat_info["vat_rate"],
        "vat_raw": vat_info["vat_raw"],
        "vat_review_required": vat_info["vat_review_required"],

        "delivery": clean_text(ai_data.get("delivery")),
        "payment": clean_text(ai_data.get("payment")),

        "items": items,

        "warnings": warnings,
        "clarification_points": clarification_points,

        "requires_human_review": bool(warnings)
        or bool(clarification_points),
    }

    return {
        "success": bool(items),
        "error": None if items else "No usable quotation items extracted.",
        "supplier_data": supplier_data,
        "warnings": warnings,
    }
