
import re
from difflib import SequenceMatcher


MISSING_VALUES = {
    "", "not stated", "not specified", "n/a",
    "na", "none", "unknown", "-"
}


def norm(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def safe_number(value):
    if value is None or norm(value) in MISSING_VALUES:
        return None

    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def parse_dimensions(value):
    if value is None:
        return {}

    numbers = re.findall(r"\d+(?:\.\d+)?", str(value))

    if len(numbers) < 3:
        return {}

    return {
        "inner diameter": f"{float(numbers[0]):g} mm",
        "outer diameter": f"{float(numbers[1]):g} mm",
        "width": f"{float(numbers[2]):g} mm",
    }


def expand_dimensions(specifications):
    result = {}

    for key, value in (specifications or {}).items():
        clean_key = norm(key)

        if clean_key == "dimensions":
            result.update(parse_dimensions(value))
        else:
            result[clean_key] = value

    return result


def normalise_unit(value):
    unit = norm(value)

    aliases = {
        "pcs": "pc",
        "pieces": "pc",
        "piece": "pc",
        "nos": "no",
        "numbers": "no",
        "number": "no",
        "kgs": "kg",
        "kilograms": "kg",
        "litres": "l",
        "liters": "l",
    }

    return aliases.get(unit, unit)


def compare(required, offered, field=None):
    required_value = norm(required)
    offered_value = norm(offered)

    if required_value in MISSING_VALUES:
        return "NOT SPECIFIED"

    if offered_value in MISSING_VALUES:
        return "CLARIFICATION REQUIRED"

    if field == "unit":
        required_value = normalise_unit(required)
        offered_value = normalise_unit(offered)

    if field in {"inner diameter", "outer diameter", "width"}:
        required_number = safe_number(required_value.replace("mm", ""))
        offered_number = safe_number(offered_value.replace("mm", ""))

        if required_number is not None and offered_number is not None:
            return (
                "MATCH"
                if required_number == offered_number
                else "MISMATCH"
            )

    if field == "model" and required_value != offered_value:
        required_base = re.sub(r"[^a-z0-9]", "", required_value)
        offered_base = re.sub(r"[^a-z0-9]", "", offered_value)

        if (
            required_base
            and offered_base
            and (
                required_base.startswith(offered_base)
                or offered_base.startswith(required_base)
            )
        ):
            return "CLARIFICATION REQUIRED"

    return "MATCH" if required_value == offered_value else "MISMATCH"


def match_item(rfq_item, offers, used_ids, threshold=0.65):
    best_offer = None
    best_score = -999

    required_description = norm(rfq_item.get("description"))
    required_model = norm(rfq_item.get("model"))
    required_manufacturer = norm(rfq_item.get("manufacturer"))

    for offer in offers:
        if id(offer) in used_ids:
            continue

        description_score = SequenceMatcher(
            None,
            required_description,
            norm(offer.get("description")),
        ).ratio()

        score = description_score

        offered_model = norm(offer.get("model"))
        offered_manufacturer = norm(offer.get("manufacturer"))

        if required_model:
            if offered_model == required_model:
                score += 3
            elif offered_model:
                score -= 0.5
            else:
                score -= 0.25

        if required_manufacturer:
            if offered_manufacturer == required_manufacturer:
                score += 0.5
            elif offered_manufacturer:
                score -= 0.25

        if score > best_score:
            best_score = score
            best_offer = offer

    if best_offer is None or best_score < threshold:
        return None, best_score

    return best_offer, best_score


def calculate_vat(supplier, taxable_base):
    """
    Calculate VAT using the parser's VAT type.

    Percentage VAT: taxable_base * rate / 100
    Fixed VAT: use the stated amount.
    Unknown VAT: do not guess; flag for human review.

    Legacy structured Excel quotations without vat_type retain
    their previous fixed-amount interpretation.
    """
    vat_value = safe_number(supplier.get("vat"))
    vat_type = norm(supplier.get("vat_type"))
    vat_rate = safe_number(supplier.get("vat_rate"))

    if vat_type == "percentage":
        if vat_rate is None or vat_rate < 0:
            return 0, True, "VAT percentage is invalid; manual review required."

        amount = taxable_base * vat_rate / 100
        return round(amount, 2), False, f"VAT calculated at {vat_rate:g}%."

    if vat_type == "fixed":
        if vat_value is None or vat_value < 0:
            return 0, True, "Fixed VAT amount is invalid; manual review required."

        return round(vat_value, 2), False, "Fixed VAT amount applied."

    if vat_type == "unknown":
        return 0, True, "VAT type is unclear; manual review required."

    # Backward compatibility for existing structured Excel quotations.
    if vat_value is None:
        return 0, True, "VAT amount is missing; manual review required."

    if vat_value < 0:
        return 0, True, "VAT amount is invalid; manual review required."

    return round(vat_value, 2), False, "Existing fixed VAT amount applied."


def evaluate_supplier(rfq_items, supplier):
    results = []
    used_ids = set()
    supplier_items = supplier.get("items") or []

    for rfq in rfq_items:
        offer, score = match_item(
            rfq,
            supplier_items,
            used_ids,
        )

        if offer is None:
            results.append({
                "rfq_item": rfq.get("description", "Unknown item"),
                "supplier_item": "NOT QUOTED",
                "quantity_required": safe_number(rfq.get("quantity")),
                "quantity_offered": None,
                "unit_price": None,
                "line_total": None,
                "match_score": round(score, 3),
                "technical_status": "SCOPE GAP",
                "quantity_status": "NOT QUOTED",
                "details": "No matching unused supplier quotation line found.",
            })
            continue

        used_ids.add(id(offer))

        required_specs = {
            "manufacturer": rfq.get("manufacturer"),
            "model": rfq.get("model"),
            **(rfq.get("specifications") or {}),
        }

        offered_specs = {
            "manufacturer": offer.get("manufacturer"),
            "model": offer.get("model"),
            **(offer.get("specifications") or {}),
        }

        required_specs = expand_dimensions(required_specs)
        offered_specs = expand_dimensions(offered_specs)

        checks = []

        for key, required_value in required_specs.items():
            if norm(required_value) in MISSING_VALUES:
                continue

            offered_value = offered_specs.get(norm(key))
            status = compare(
                required_value,
                offered_value,
                field=norm(key),
            )

            checks.append({
                "field": key,
                "required": required_value,
                "offered": offered_value,
                "status": status,
            })

        required_unit = rfq.get("unit")
        offered_unit = offer.get("unit")

        if norm(required_unit) not in MISSING_VALUES:
            unit_status = compare(
                required_unit,
                offered_unit,
                field="unit",
            )

            checks.append({
                "field": "unit",
                "required": required_unit,
                "offered": offered_unit,
                "status": unit_status,
            })

        statuses = [check["status"] for check in checks]

        if "MISMATCH" in statuses:
            technical_status = "NON-COMPLIANT"
        elif "CLARIFICATION REQUIRED" in statuses:
            technical_status = "CLARIFICATION REQUIRED"
        elif checks:
            technical_status = "COMPLIANT"
        else:
            technical_status = "REVIEW REQUIRED"

        required_qty = safe_number(rfq.get("quantity"))
        offered_qty = safe_number(offer.get("quantity"))

        if required_qty is None or offered_qty is None:
            quantity_status = "CLARIFICATION REQUIRED"
            quantity_note = (
                "Quantity information is missing or invalid. "
                "Confirm required and offered quantities."
            )
        elif offered_qty < required_qty:
            quantity_status = "PARTIAL QUOTATION"
            quantity_note = (
                f"Partial quotation: required {required_qty:g}, "
                f"offered {offered_qty:g}. "
                "Excluded from full-scope ranking."
            )
        elif offered_qty > required_qty:
            quantity_status = "CLARIFICATION REQUIRED"
            quantity_note = (
                f"Excess quantity: required {required_qty:g}, "
                f"offered {offered_qty:g}. Confirm whether this is the MOQ "
                "and whether the supplier can supply the exact required quantity."
            )
        else:
            quantity_status = "FULL QUANTITY MATCH"
            quantity_note = "Full quantity match."

        unit_price = safe_number(offer.get("unit_price"))

        line_total = (
            offered_qty * unit_price
            if offered_qty is not None and unit_price is not None
            else None
        )

        details = "; ".join(
            f"{check['field']}: required '{check['required']}', "
            f"offered '{check['offered']}' = {check['status']}"
            for check in checks
        )

        if not details:
            details = "No technical fields available for comparison."

        details = f"{details}; {quantity_note}"

        results.append({
            "rfq_item": rfq.get("description", "Unknown item"),
            "supplier_item": offer.get("description", "Unknown item"),
            "quantity_required": required_qty,
            "quantity_offered": offered_qty,
            "unit_price": unit_price,
            "line_total": line_total,
            "match_score": round(score, 3),
            "technical_status": technical_status,
            "quantity_status": quantity_status,
            "details": details,
        })

    extra_items = [
        item.get("description", "Unknown item")
        for item in supplier_items
        if id(item) not in used_ids
    ]

    scope_complete = all(
        item["technical_status"] != "SCOPE GAP"
        for item in results
    )

    technically_compliant = all(
        item["technical_status"] == "COMPLIANT"
        for item in results
    )

    full_quantity_match = all(
        item["quantity_status"] == "FULL QUANTITY MATCH"
        for item in results
    )

    evaluated_line_total = sum(
        item["line_total"] or 0
        for item in results
    )

    freight = safe_number(supplier.get("freight"))
    discount = safe_number(supplier.get("discount"))

    freight = freight if freight is not None else 0
    discount = discount if discount is not None else 0

    taxable_base = evaluated_line_total + freight - discount

    if taxable_base < 0:
        taxable_base = 0

    vat, vat_review_required, vat_calculation_note = calculate_vat(
        supplier,
        taxable_base,
    )

    commercial_total = taxable_base + vat

    eligible_for_ranking = (
        scope_complete
        and technically_compliant
        and full_quantity_match
    )

    return {
        "supplier": supplier.get("supplier", "Unknown supplier"),
        "quote_number": supplier.get("quote_number"),
        "currency": supplier.get("currency", "Not specified"),
        "delivery": supplier.get("delivery"),
        "payment": supplier.get("payment"),
        "items": results,
        "extra_items": extra_items,
        "coverage_complete": scope_complete,
        "technically_compliant": technically_compliant,
        "full_quantity_match": full_quantity_match,
        "quoted_line_total": evaluated_line_total,
        "freight": freight,
        "discount": discount,
        "vat": vat,
        "vat_type": supplier.get("vat_type"),
        "vat_rate": supplier.get("vat_rate"),
        "vat_review_required": vat_review_required,
        "vat_calculation_note": vat_calculation_note,
        "taxable_base": taxable_base,
        "commercial_total": commercial_total,
        "eligible_for_ranking": eligible_for_ranking,
    }
