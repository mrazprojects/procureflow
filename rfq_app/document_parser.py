
import re
from pathlib import Path


def clean_text(text):
    """Normalise extracted PDF, Word, TXT or OCR text."""
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n[ ]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_field(patterns, text):
    """Return the first captured value matching supplied patterns."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def parse_number(value):
    """Convert a number containing commas or currency symbols to float."""
    if value is None:
        return None

    cleaned = re.sub(r"[^\d.\-]", "", str(value).strip())

    if not cleaned or cleaned in {".", "-", "-."}:
        return None

    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def parse_vat(text):
    """
    Identify VAT as a percentage, fixed amount, or unclear value.

    Examples:
      VAT: 5%       -> percentage
      VAT: AED 5    -> fixed amount
      VAT: 5        -> unclear
    """
    pattern = re.compile(
        r"\b(?:VAT|tax)\s*[:\-]?\s*"
        r"(?:(AED|USD|EUR|GBP|SAR|QAR|OMR|KWD|INR)\s*)?"
        r"([0-9,]+(?:\.\d+)?)\s*(%)?",
        re.IGNORECASE,
    )

    match = pattern.search(text)

    if not match:
        return {
            "vat": 0,
            "vat_type": "unknown",
            "vat_rate": None,
            "vat_review_required": True,
            "vat_raw": None,
        }

    currency = match.group(1)
    amount = parse_number(match.group(2))
    percent_sign = match.group(3)

    raw_value = match.group(0).strip()

    if amount is None:
        vat_type = "unknown"
        rate = None
        review = True

    elif percent_sign:
        vat_type = "percentage"
        rate = amount
        review = False

    elif currency:
        vat_type = "fixed"
        rate = None
        review = False

    else:
        # A bare number is ambiguous. Do not guess whether it is
        # a percentage or a fixed currency amount.
        vat_type = "unknown"
        rate = None
        review = True

    return {
        "vat": amount if amount is not None else 0,
        "vat_type": vat_type,
        "vat_rate": rate,
        "vat_review_required": review,
        "vat_raw": raw_value,
    }


def _first_nonempty_line(text):
    for line in text.splitlines():
        value = line.strip(" \t|:-")
        if value:
            return value
    return None


def _parse_pipe_rows(lines):
    """Parse pipe-delimited quotation rows."""
    items = []

    for line in lines:
        parts = [part.strip() for part in line.split("|")]

        if len(parts) < 3:
            continue

        heading = " ".join(parts).casefold()
        if "description" in heading and (
            "quantity" in heading or "qty" in heading
        ):
            continue

        item = None

        if len(parts) >= 8:
            quantity = parse_number(parts[3])
            unit_price = parse_number(parts[5])

            if quantity is not None and unit_price is not None:
                item = {
                    "description": parts[0],
                    "manufacturer": parts[1] or None,
                    "model": parts[2] or None,
                    "quantity": quantity,
                    "unit": parts[4] or None,
                    "unit_price": unit_price,
                    "specifications": {
                        "dimensions": parts[6],
                        "material": parts[7],
                    },
                }

        if item is None:
            quantity = parse_number(parts[1])
            unit_price = parse_number(parts[2])

            if quantity is not None and unit_price is not None:
                item = {
                    "description": parts[0],
                    "manufacturer": None,
                    "model": None,
                    "quantity": quantity,
                    "unit": None,
                    "unit_price": unit_price,
                    "specifications": {},
                }

        if (
            item
            and item["description"]
            and item["quantity"] > 0
            and item["unit_price"] >= 0
        ):
            items.append(item)

    return items


def _parse_stacked_rows(lines):
    """Parse PDF tables where cells are extracted as separate lines."""
    items = []

    normalized = [
        re.sub(r"\s+", " ", value.strip().casefold())
        for value in lines
    ]

    six_column_headers = [
        "description", "manufacturer / model", "qty",
        "unit price", "dimensions", "material",
    ]

    seven_column_headers = [
        "description", "manufacturer / model", "qty", "unit",
        "unit price", "dimensions", "material",
    ]

    start = None
    column_count = None

    for index in range(len(normalized)):
        if normalized[index:index + 7] == seven_column_headers:
            start = index + 7
            column_count = 7
            break

        if normalized[index:index + 6] == six_column_headers:
            start = index + 6
            column_count = 6
            break

    if start is None:
        return items

    data_lines = []

    stop_pattern = re.compile(
        r"^(?:line\s+total|sub\s*total|freight|shipping|transport|"
        r"discount|vat|tax|grand\s+total|total)\b",
        re.IGNORECASE,
    )

    for line in lines[start:]:
        value = line.strip()

        if not value:
            continue

        if stop_pattern.match(value):
            break

        data_lines.append(value)

    for index in range(
        0, len(data_lines) - column_count + 1, column_count
    ):
        row = data_lines[index:index + column_count]

        if column_count == 7:
            (
                description, make_model, qty_text, unit_text,
                price_text, dimensions, material
            ) = row
            unit = unit_text.strip() or None
        else:
            (
                description, make_model, qty_text,
                price_text, dimensions, material
            ) = row
            unit = None

        qty_match = re.match(
            r"^\s*([\d,]+(?:\.\d+)?)\s*([A-Za-z]+)?\s*$",
            qty_text,
        )

        if qty_match:
            quantity = parse_number(qty_match.group(1))

            if not unit and qty_match.group(2):
                unit = qty_match.group(2)
        else:
            quantity = parse_number(qty_text)

        unit_price = parse_number(price_text)

        if quantity is None or unit_price is None or quantity <= 0:
            continue

        manufacturer = None
        model = None

        if "/" in make_model:
            manufacturer_part, model_part = make_model.split("/", 1)
            manufacturer = manufacturer_part.strip() or None
            model = model_part.strip() or None
        else:
            manufacturer = make_model.strip() or None

        items.append({
            "description": description,
            "manufacturer": manufacturer,
            "model": model,
            "quantity": quantity,
            "unit": unit,
            "unit_price": unit_price,
            "specifications": {
                "dimensions": dimensions,
                "material": material,
            },
        })

    return items


def _parse_ocr_rows(lines):
    """Parse OCR text where each quotation item is one text line."""
    items = []

    number_pattern = r"[\d,]+(?:\.\d+)?"
    dimension_pattern = r"\d+(?:\s*[x×]\s*\d+){1,3}\s*(?:mm|cm|in)?"

    row_pattern = re.compile(
        rf"^(?P<description>.+?)\s+"
        rf"(?P<make_model>[A-Za-z0-9][A-Za-z0-9&()._-]*\s*/\s*"
        rf"[A-Za-z0-9][A-Za-z0-9&()._-]*)\s+"
        rf"(?P<quantity>{number_pattern})\s+"
        rf"(?P<unit_price>{number_pattern})\s+"
        rf"(?P<dimensions>{dimension_pattern})\s+"
        rf"(?P<material>.+)$",
        re.IGNORECASE,
    )

    stop_pattern = re.compile(
        r"^(?:line\s+total|sub\s*total|freight|shipping|transport|"
        r"discount|vat|tax|grand\s+total|total)\b",
        re.IGNORECASE,
    )

    for line in lines:
        value = line.strip()

        if not value or "|" in value or stop_pattern.match(value):
            continue

        match = row_pattern.match(value)

        if not match:
            continue

        quantity = parse_number(match.group("quantity"))
        unit_price = parse_number(match.group("unit_price"))

        if quantity is None or quantity <= 0 or unit_price is None:
            continue

        manufacturer, model = match.group("make_model").split("/", 1)

        items.append({
            "description": match.group("description").strip(),
            "manufacturer": manufacturer.strip() or None,
            "model": model.strip() or None,
            "quantity": quantity,
            "unit": None,
            "unit_price": unit_price,
            "specifications": {
                "dimensions": match.group("dimensions").strip(),
                "material": match.group("material").strip(),
            },
        })

    return items


def _parse_inline_rows(lines):
    """Parse simple description, quantity and unit-price rows."""
    items = []

    for line in lines:
        value = line.strip()

        if not value or "|" in value:
            continue

        if re.search(
            r"\b(line total|freight|discount|vat|tax|grand total)\b",
            value,
            re.I,
        ):
            continue

        match = re.match(
            r"^(.*?)\s{2,}(\d+(?:\.\d+)?)\s{2,}"
            r"(?:AED\s*)?([\d,]+(?:\.\d{1,2})?)$",
            value,
            re.IGNORECASE,
        )

        if match:
            description, quantity_text, price_text = match.groups()
            quantity = parse_number(quantity_text)
            unit_price = parse_number(price_text)

            if quantity and unit_price is not None:
                items.append({
                    "description": description.strip(),
                    "manufacturer": None,
                    "model": None,
                    "quantity": quantity,
                    "unit": None,
                    "unit_price": unit_price,
                    "specifications": {},
                })

    return items


def _parse_labelled_rows(lines):
    """
    Parse quotation items where each field appears on a separate line.

    Example:
    Description: Bearing
    Manufacturer: SKF
    Model: 6205
    Quantity: 100
    Unit: Nos
    Unit Price: AED 39
    """

    items = []
    current = {}

    field_aliases = {
        "description": "description",
        "item description": "description",
        "manufacturer": "manufacturer",
        "make": "manufacturer",
        "model": "model",
        "part number": "model",
        "dimensions": "dimensions",
        "size": "dimensions",
        "material": "material",
        "quantity": "quantity",
        "qty": "quantity",
        "unit": "unit",
        "uom": "unit",
        "unit price": "unit_price",
        "price": "unit_price",
        "rate": "unit_price",
    }

    def save_current():
        if not current.get("description"):
            return

        quantity = parse_number(current.get("quantity"))
        unit_price = parse_number(current.get("unit_price"))

        if quantity is None or quantity <= 0 or unit_price is None:
            return

        specifications = {}

        if current.get("dimensions"):
            specifications["dimensions"] = current["dimensions"]

        if current.get("material"):
            specifications["material"] = current["material"]

        items.append({
            "description": current["description"],
            "manufacturer": current.get("manufacturer"),
            "model": current.get("model"),
            "quantity": quantity,
            "unit": current.get("unit"),
            "unit_price": unit_price,
            "specifications": specifications,
        })

    for line in lines:
        value = line.strip()

        if not value:
            continue

        match = re.match(
            r"^([A-Za-z][A-Za-z /_-]*)\s*:\s*(.+)$",
            value
        )

        if not match:
            continue

        label = re.sub(
            r"\s+",
            " ",
            match.group(1).strip().lower()
        )

        field = field_aliases.get(label)

        if not field:
            continue

        field_value = match.group(2).strip()

        if field == "description":
            if current:
                save_current()

            current = {"description": field_value}
        elif current:
            current[field] = field_value

    if current:
        save_current()

    return items

def parse_document_quote(text, filename):
    """Extract supplier, commercial metadata and line items."""
    text = clean_text(text)
    lines = [line.strip() for line in text.splitlines()]

    supplier = extract_field(
        [
            r"^(?:supplier|vendor|company)\s*name\s*[:\-]\s*(.+)$",
            r"^(?:supplier|vendor|company)\s*[:\-]\s*(.+)$",
        ],
        text,
    )

    if not supplier:
        first_line = _first_nonempty_line(text)

        if first_line and not re.search(
            r"^(quotation|quote|currency|description|supplier|vendor)\b",
            first_line,
            re.IGNORECASE,
        ):
            supplier = first_line

    quote_number = extract_field(
        [
            r"^\s*(?:quotation|quote)\s*(?:number|no\.?|#)?\s*[:\-]\s*"
            r"([A-Z0-9][A-Z0-9/\-_]*)",
            r"^\s*(?:quotation|quote)\s*#\s*"
            r"([A-Z0-9][A-Z0-9/\-_]*)",
        ],
        text,
    )

    currency = extract_field(
        [
            r"\bcurrency\s*[:\-]\s*([A-Z]{3})\b",
            r"\b(AED|USD|EUR|GBP|SAR|QAR|OMR|KWD|INR)\b",
        ],
        text,
    )

    freight_text = extract_field(
        [
            r"\b(?:freight|shipping|transport)\s*[:\-]\s*"
            r"(?:[A-Z]{3}\s*)?([0-9,]+(?:\.\d+)?)"
        ],
        text,
    )

    discount_text = extract_field(
        [
            r"\bdiscount\s*[:\-]\s*"
            r"(?:[A-Z]{3}\s*)?([0-9,]+(?:\.\d+)?)"
        ],
        text,
    )

    vat_data = parse_vat(text)

    delivery = extract_field(
        [
            r"\b(?:delivery|lead\s*time)\s*[:\-]\s*(.*?)"
            r"(?=\s+payment(?:\s+terms?)?\s*[:\-]|"
            r"\s+currency\s*[:\-]|\s+freight\s*[:\-]|"
            r"\s+discount\s*[:\-]|\s+VAT\s*[:\-]|"
            r"\s+tax\s*[:\-]|[|\n]|$)"
        ],
        text,
    )

    payment = extract_field(
        [
            r"\bpayment(?:\s+terms?)?\s*[:\-]\s*(.*?)"
            r"(?=\s+delivery\s*[:\-]|\s+lead\s*time\s*[:\-]|"
            r"\s+currency\s*[:\-]|\s+freight\s*[:\-]|"
            r"\s+discount\s*[:\-]|\s+VAT\s*[:\-]|"
            r"\s+tax\s*[:\-]|[|\n]|$)"
        ],
        text,
    )

    items = _parse_pipe_rows(lines)

    if not items:
        items = _parse_stacked_rows(lines)

    if not items:
        items = _parse_ocr_rows(lines)

    if not items:
        items = _parse_inline_rows(lines)

    if not items:
        items = _parse_labelled_rows(lines)
    if not items:
        items = _parse_labelled_rows(lines)

    warnings = []

    if not supplier:
        warnings.append("Supplier name was not identified.")

    if not quote_number:
        warnings.append("Quotation number was not identified.")

    if not items:
        warnings.append(
            "No structured quotation lines were identified. Manual review is required."
        )

    if items and any(
        not item.get("manufacturer") or not item.get("model")
        for item in items
    ):
        warnings.append("Some manufacturer or model details are missing.")

    if items and any(not item.get("specifications") for item in items):
        warnings.append("Some technical specifications are missing.")

    if freight_text is None:
        warnings.append(
            "Freight was not identified; verify whether freight is included or excluded."
        )

    if discount_text is None:
        warnings.append("Discount was not identified; verify the supplier quotation.")

    if vat_data["vat_review_required"]:
        warnings.append(
            "VAT type or amount is unclear or missing; manual review is required."
        )

    return {
        "supplier": supplier or Path(filename).stem,
        "quote_number": quote_number,
        "currency": currency or "Not specified",
        "freight": parse_number(freight_text) if freight_text is not None else 0,
        "discount": parse_number(discount_text) if discount_text is not None else 0,
        "vat": vat_data["vat"],
        "vat_type": vat_data["vat_type"],
        "vat_rate": vat_data["vat_rate"],
        "vat_review_required": vat_data["vat_review_required"],
        "vat_raw": vat_data["vat_raw"],
        "delivery": delivery.strip() if delivery else None,
        "payment": payment.strip() if payment else None,
        "items": items,
        "source_file": filename,
        "warnings": warnings,
        "requires_human_review": True,
    }
