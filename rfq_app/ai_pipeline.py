
from copy import deepcopy

from rfq_app.document_parser import parse_document_quote
from rfq_app.ai_extractor import extract_quote_with_ai
from rfq_app.ai_normalizer import normalise_ai_quote


def _value(data, key):
    """Safely read a value from an extraction dictionary."""
    if not isinstance(data, dict):
        return None
    return data.get(key)


def _compare_values(rule_value, ai_value):
    """Compare two values without treating missing values as mismatches."""
    if rule_value is None or ai_value is None:
        return None

    rule_text = str(rule_value).strip().lower()
    ai_text = str(ai_value).strip().lower()

    if not rule_text or not ai_text:
        return None

    return rule_text != ai_text


def compare_extractions(rule_data, ai_data):
    """Compare rule-based and AI extraction results."""

    discrepancies = []

    fields = [
        "supplier",
        "quote_number",
        "currency",
        "freight",
        "discount",
        "delivery",
        "payment",
        "vat",
        "vat_type",
    ]

    for field in fields:
        rule_value = _value(rule_data, field)
        ai_value = _value(ai_data, field)

        different = _compare_values(rule_value, ai_value)

        if different:
            discrepancies.append({
                "field": field,
                "rule_based": rule_value,
                "ai_extracted": ai_value,
                "message": f"Different values found for {field}.",
            })

    rule_items = rule_data.get("items", []) or []
    ai_items = ai_data.get("items", []) or []

    if len(rule_items) != len(ai_items):
        discrepancies.append({
            "field": "item_count",
            "rule_based": len(rule_items),
            "ai_extracted": len(ai_items),
            "message": "The extracted item counts do not match.",
        })

    item_fields = [
        "description",
        "manufacturer",
        "model",
        "quantity",
        "unit",
        "unit_price",
    ]

    for index, (rule_item, ai_item) in enumerate(
        zip(rule_items, ai_items), start=1
    ):
        for field in item_fields:
            rule_value = rule_item.get(field)
            ai_value = ai_item.get(field)

            different = _compare_values(rule_value, ai_value)

            if different:
                discrepancies.append({
                    "field": f"item_{index}_{field}",
                    "rule_based": rule_value,
                    "ai_extracted": ai_value,
                    "message": (
                        f"Item {index}: different values found for {field}."
                    ),
                })

        rule_specs = rule_item.get("specifications", {}) or {}
        ai_specs = ai_item.get("specifications", {}) or {}

        for field in ("dimensions", "material"):
            different = _compare_values(
                rule_specs.get(field),
                ai_specs.get(field),
            )

            if different:
                discrepancies.append({
                    "field": f"item_{index}_{field}",
                    "rule_based": rule_specs.get(field),
                    "ai_extracted": ai_specs.get(field),
                    "message": (
                        f"Item {index}: different {field} specifications."
                    ),
                })

    return discrepancies


def prepare_ai_fallback(ai_data):
    """
    Prepare AI extraction for downstream evaluation.

    Missing freight and discount are represented as zero only to prevent
    arithmetic errors. Review flags ensure these values are not treated
    as confirmed commercial information.
    """

    data = deepcopy(ai_data)

    freight_missing = data.get("freight") is None
    discount_missing = data.get("discount") is None

    if freight_missing:
        data["freight"] = 0.0

    if discount_missing:
        data["discount"] = 0.0

    data["freight_review_required"] = freight_missing
    data["discount_review_required"] = discount_missing

    data["ai_fallback_used"] = True
    data["requires_human_review"] = True
    data["eligible_for_ranking"] = False

    warnings = data.get("warnings", []) or []

    if freight_missing:
        warnings.append(
            "Freight was not confirmed. Verify the supplier quotation."
        )

    if discount_missing:
        warnings.append(
            "Discount was not confirmed. Verify the supplier quotation."
        )

    data["warnings"] = list(dict.fromkeys(warnings))

    return data


def process_quote_text(text, filename="quotation.txt", use_ai=True):
    """
    Run rule-based and AI extraction on supplier quotation text.

    Rule-based extraction remains the primary method.
    AI is used for cross-checking and as a fallback when necessary.
    """

    result = {
        "success": False,
        "selected_data": None,
        "rule_based_data": None,
        "ai_data": None,
        "extraction_method": None,
        "ai_extraction_success": False,
        "discrepancies": [],
        "warnings": [],
        "requires_human_review": False,
    }

    if not text or not str(text).strip():
        result["warnings"].append("No quotation text was provided.")
        return result

    # --------------------------------------------------
    # 1. Rule-based extraction
    # --------------------------------------------------

    try:
        rule_result = parse_document_quote(text, filename)

        if isinstance(rule_result, dict):
            result["rule_based_data"] = rule_result

    except Exception as error:
        result["warnings"].append(
            f"Rule-based extraction failed: {error}"
        )

    rule_data = result["rule_based_data"] or {}

    rule_items = rule_data.get("items", []) or []

    # --------------------------------------------------
    # 2. AI extraction
    # --------------------------------------------------

    if use_ai:
        try:
            raw_ai_result = extract_quote_with_ai(text)

            if isinstance(raw_ai_result, dict):
                normalised_result = normalise_ai_quote(raw_ai_result)

                if isinstance(normalised_result, dict):
                    if normalised_result.get("success"):
                        result["ai_data"] = (
                            normalised_result.get("supplier_data")
                        )

                        result["ai_extraction_success"] = bool(
                            result["ai_data"]
                        )

                    else:
                        error_message = normalised_result.get(
                            "error",
                            "AI extraction did not return usable items.",
                        )
                        result["warnings"].append(
                            f"AI extraction: {error_message}"
                        )

        except Exception as error:
            result["warnings"].append(
                f"AI extraction failed: {error}"
            )

    ai_data = result["ai_data"] or {}
    ai_items = ai_data.get("items", []) or []

    # --------------------------------------------------
    # 3. Select the primary extraction
    # --------------------------------------------------

    if rule_items:
        selected_data = deepcopy(rule_data)
        result["extraction_method"] = "Rule-based"

        # Compare both methods when AI extraction is available.
        if ai_items:
            result["discrepancies"] = compare_extractions(
                rule_data,
                ai_data,
            )

            if result["discrepancies"]:
                result["requires_human_review"] = True

    elif ai_items:
        selected_data = prepare_ai_fallback(ai_data)
        result["extraction_method"] = "AI fallback"
        result["requires_human_review"] = True

        result["warnings"].append(
            "AI fallback was used because rule-based extraction "
            "did not identify usable quotation items. "
            "Review all extracted information before evaluation."
        )

    else:
        selected_data = None
        result["extraction_method"] = "Failed"

        result["warnings"].append(
            "Neither rule-based nor AI extraction identified usable items."
        )

    # --------------------------------------------------
    # 4. Carry review information into the final result
    # --------------------------------------------------

    if selected_data:
        selected_data.setdefault("warnings", [])

        if result["discrepancies"]:
            selected_data["requires_human_review"] = True

        result["warnings"].extend(
            selected_data.get("warnings", [])
        )

        if selected_data.get("freight_review_required"):
            result["requires_human_review"] = True

        if selected_data.get("discount_review_required"):
            result["requires_human_review"] = True

        if selected_data.get("vat_review_required"):
            result["requires_human_review"] = True

        if selected_data.get("requires_human_review"):
            result["requires_human_review"] = True

        result["selected_data"] = selected_data
        result["success"] = True

    # --------------------------------------------------
    # 5. Remove duplicate warnings
    # --------------------------------------------------

    result["warnings"] = list(
        dict.fromkeys(result["warnings"])
    )

    return result
