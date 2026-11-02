
from pathlib import Path
import re
from openpyxl import load_workbook
from .extractors import extract_text


def norm(value):
    if value is None:
        return ""

    text = str(value).strip().lower()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find(headers, names):
    return next((h for h in headers if h in names), None)


def parse_amount(value):
    if value in (None, ""):
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    cleaned = str(value).replace(",", "").strip()
    cleaned = re.sub(r"[^\d.\-]", "", cleaned)

    return float(cleaned) if cleaned else 0.0


def parse_vat_info(value, label=""):
    """
    Identify whether an Excel VAT value represents:
    - a percentage
    - a fixed currency amount
    - an ambiguous value requiring human review
    """
    raw = str(value).strip() if value is not None else ""
    label_text = norm(label)
    raw_lower = raw.lower()

    amount = parse_amount(value)

    if value in (None, ""):
        return {
            "vat": 0.0,
            "vat_type": "unknown",
            "vat_rate": None,
            "vat_review_required": True,
            "vat_raw": raw
        }

    # Explicit percentage in either the column label or value.
    if (
        "%" in raw
        or "%" in label_text
        or "percentage" in label_text
        or "rate" in label_text
    ):
        return {
            "vat": amount,
            "vat_type": "percentage",
            "vat_rate": amount,
            "vat_review_required": False,
            "vat_raw": raw
        }

    # Explicit VAT amount or currency amount.
    if (
        "amount" in label_text
        or re.search(r"\b(AED|USD|EUR|GBP|SAR|QAR|OMR|KWD|INR)\b", raw, re.I)
        or "₹" in raw
        or "$" in raw
        or "€" in raw
    ):
        return {
            "vat": amount,
            "vat_type": "fixed",
            "vat_rate": None,
            "vat_review_required": False,
            "vat_raw": raw
        }

    # A plain number such as 5 is ambiguous.
    return {
        "vat": amount,
        "vat_type": "unknown",
        "vat_rate": None,
        "vat_review_required": True,
        "vat_raw": raw
    }


def read_supplier_excel(file):
    name = getattr(file, "name", str(file))

    if Path(name).suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError(
            "Use Excel .xlsx/.xlsm for structured quotation comparison."
        )

    if hasattr(file, "seek"):
        file.seek(0)

    wb = load_workbook(file, data_only=True)
    ws = wb.active

    # Find the row containing the quotation item column headers.
    header_row = None
    headers = []

    for row_number in range(1, min(ws.max_row, 30) + 1):
        candidate = [
            norm(cell.value) for cell in ws[row_number]
        ]

        has_description = any(
            value in {
                "description",
                "item description",
                "material description",
                "product description",
                "item"
            }
            for value in candidate
        )

        has_quantity = any(
            value in {"quantity", "qty"}
            for value in candidate
        )

        has_price = any(
            value.startswith("unit price")
            or value in {"rate", "unit rate", "price"}
            for value in candidate
        )

        if has_description and has_quantity and has_price:
            header_row = row_number
            headers = [
                value or f"blank_{i}"
                for i, value in enumerate(candidate)
            ]
            break

    if header_row is None:
        wb.close()
        raise ValueError(
            "Could not locate the item header row. "
            "Required columns: Description, Quantity and Unit Price."
        )

    def col(*names):
        return find(headers, set(names))

    desc = col(
        "item description",
        "description",
        "material description",
        "product description",
        "item"
    )

    qty = col("quantity", "qty")

    price = next(
        (
            h for h in headers
            if h.startswith("unit price")
            or h in {"rate", "unit rate", "price"}
        ),
        None
    )

    mapping = {
        "supplier": col(
            "supplier name", "supplier",
            "vendor name", "vendor"
        ),
        "quote": col(
            "quotation number", "quote number",
            "quotation no", "quote no"
        ),
        "currency": col("currency"),
        "unit": col("unit", "uom"),
        "manufacturer": col("manufacturer", "make", "brand"),
        "model": col("model", "model number", "part number"),
        "freight": col("freight", "shipping", "transport"),
        "discount": col("discount"),
        "vat": col(
            "vat",
            "vat %",
            "vat (%)",
            "vat rate",
            "vat percentage",
            "vat amount",
            "tax"
        ),
        "delivery": col(
            "delivery days", "delivery", "lead time"
        ),
        "payment": col("payment terms", "payment")
    }

    known = {
        desc,
        qty,
        price,
        *[value for value in mapping.values() if value]
    }

    spec_cols = [
        h for h in headers
        if h not in known and not h.startswith("blank_")
    ]

    # Read supplier metadata from the quotation header section.
    meta = {}

    for row in ws.iter_rows(
        min_row=1,
        max_row=header_row - 1,
        values_only=True
    ):
        for index in range(0, len(row) - 1):
            label = norm(row[index])
            value = row[index + 1]

            if value in (None, ""):
                continue

            if label in {
                "supplier", "supplier name",
                "vendor", "vendor name"
            }:
                meta["supplier"] = value

            elif label in {
                "quotation no", "quotation number",
                "quote no", "quote number"
            }:
                meta["quote"] = value

            elif label == "currency":
                meta["currency"] = value

            elif label in {"freight", "shipping", "transport"}:
                meta["freight"] = value

            elif label == "discount":
                meta["discount"] = value

            elif label in {
                "vat", "vat %", "vat (%)",
                "vat rate", "vat percentage",
                "vat amount", "tax"
            }:
                meta["vat"] = value
                meta["vat_label"] = label

            elif label in {"delivery", "delivery days", "lead time"}:
                meta["delivery"] = value

            elif label in {"payment", "payment terms"}:
                meta["payment"] = value

    # The supplier name may also be displayed in the first cell.
    if not meta.get("supplier"):
        first_value = ws.cell(1, 1).value

        if first_value:
            meta["supplier"] = str(first_value).strip()

    rows = []
    vat_column_values = []

    for row in ws.iter_rows(
        min_row=header_row + 1,
        values_only=True
    ):
        if not any(value is not None for value in row):
            continue

        data = dict(zip(headers, row))

        description = data.get(desc)

        # Capture a VAT value if VAT is supplied as a separate column.
        if mapping["vat"]:
            column_vat = data.get(mapping["vat"])
            if column_vat not in (None, ""):
                vat_column_values.append(column_vat)

        if description in (None, ""):
            continue

        try:
            quantity = parse_amount(data.get(qty))
            unit_price = parse_amount(data.get(price))

            if quantity <= 0 or unit_price < 0:
                continue

        except (TypeError, ValueError):
            continue

        rows.append({
            "description": str(description).strip(),
            "quantity": quantity,
            "unit_price": unit_price,
            "unit": (
                data.get(mapping["unit"])
                if mapping["unit"] else None
            ),
            "manufacturer": (
                data.get(mapping["manufacturer"])
                if mapping["manufacturer"] else None
            ),
            "model": (
                data.get(mapping["model"])
                if mapping["model"] else None
            ),
            "specifications": {
                column: data[column]
                for column in spec_cols
                if data.get(column) not in (None, "")
            }
        })

    wb.close()

    if not rows:
        raise ValueError("No valid quotation line items found.")

    # Prefer VAT metadata. If unavailable, use the VAT column.
    vat_value = meta.get("vat")
    vat_label = meta.get("vat_label", "")

    if vat_value is None and vat_column_values:
        unique_vat_values = list(dict.fromkeys(vat_column_values))

        if len(unique_vat_values) == 1:
            vat_value = unique_vat_values[0]
            vat_label = mapping["vat"]

    vat_info = parse_vat_info(vat_value, vat_label)

    return {
        "supplier": (
            meta.get("supplier") or Path(name).stem
        ),
        "quote_number": meta.get("quote"),
        "currency": meta.get("currency") or "Not specified",
        "freight": parse_amount(meta.get("freight")),
        "discount": parse_amount(meta.get("discount")),
        "vat": vat_info["vat"],
        "vat_type": vat_info["vat_type"],
        "vat_rate": vat_info["vat_rate"],
        "vat_review_required": vat_info["vat_review_required"],
        "vat_raw": vat_info["vat_raw"],
        "delivery": meta.get("delivery"),
        "payment": meta.get("payment"),
        "items": rows,
        "source_file": name
    }


def read_unstructured_quote(file):
    return {
        "source_file": file.name,
        "extracted_text": extract_text(file)
    }
