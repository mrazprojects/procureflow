from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rfq_app.rfq_reader import read_rfq_excel
from rfq_app.quotation_reader import read_supplier_excel
from rfq_app.document_parser import parse_document_quote
from rfq_app.extractors import extract_text
from rfq_app.evaluator import evaluate_supplier

FIXTURES = ROOT / "tests" / "fixtures"
RFQ_FILE = ROOT / "data" / "samples" / "sample_rfq.xlsx"

EXPECTED = {
    "01_Gulf_Industrial_Supplies_LLC.xlsx": {
        "technical": ["COMPLIANT", "COMPLIANT"],
        "quantity": ["FULL QUANTITY MATCH", "FULL QUANTITY MATCH"],
        "eligible": True,
    },
    "02_Desert_Star_Trading_LLC.pdf": {
        "technical": ["CLARIFICATION REQUIRED", "CLARIFICATION REQUIRED"],
        "quantity": ["FULL QUANTITY MATCH", "FULL QUANTITY MATCH"],
        "eligible": False,
    },
    "03_Apex_Bearing_House.png": {
        "technical": ["NON-COMPLIANT", "NON-COMPLIANT"],
        "quantity": ["FULL QUANTITY MATCH", "FULL QUANTITY MATCH"],
        "eligible": False,
    },
    "04_Metro_Industrial_Trading.xlsx": {
        "technical": ["NON-COMPLIANT", "COMPLIANT"],
        "quantity": ["FULL QUANTITY MATCH", "FULL QUANTITY MATCH"],
        "eligible": False,
    },
    "05_Prime_Motion_Components.pdf": {
        "technical": ["NON-COMPLIANT", "CLARIFICATION REQUIRED"],
        "quantity": ["FULL QUANTITY MATCH", "FULL QUANTITY MATCH"],
        "eligible": False,
        "vat": 337.0,
    },
    "06_Universal_Bearings_FZE.png": {
        "technical": ["CLARIFICATION REQUIRED", "CLARIFICATION REQUIRED"],
        "quantity": ["FULL QUANTITY MATCH", "FULL QUANTITY MATCH"],
        "eligible": False,
    },
    "07_Al_Noor_Mechanical_Supplies.xlsx": {
        "technical": ["CLARIFICATION REQUIRED", "CLARIFICATION REQUIRED"],
        "quantity": ["FULL QUANTITY MATCH", "FULL QUANTITY MATCH"],
        "eligible": False,
    },
    "08_Eastern_Technical_Stores.pdf": {
        "technical": ["CLARIFICATION REQUIRED", "CLARIFICATION REQUIRED"],
        "quantity": ["PARTIAL QUOTATION", "PARTIAL QUOTATION"],
        "eligible": False,
    },
    "09_Crescent_Industrial_LLC.png": {
        "technical": ["CLARIFICATION REQUIRED", "NON-COMPLIANT"],
        "quantity": ["FULL QUANTITY MATCH", "FULL QUANTITY MATCH"],
        "eligible": False,
    },
    "10_Vertex_Engineering_Trading.xlsx": {
        "technical": ["COMPLIANT", "CLARIFICATION REQUIRED"],
        "quantity": ["FULL QUANTITY MATCH", "FULL QUANTITY MATCH"],
        "eligible": False,
        "vat": 357.5,
    },
}


def load_supplier(path):
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        with path.open("rb") as f:
            return read_supplier_excel(f)

    with path.open("rb") as f:
        text = extract_text(f)

    return parse_document_quote(text, path.name)


def main():
    with RFQ_FILE.open("rb") as f:
        rfq = read_rfq_excel(f)

    passed = 0
    failed = 0

    print("\nPROCUREFLOW REGRESSION TEST")
    print("=" * 65)

    for filename, expected in EXPECTED.items():
        try:
            supplier = load_supplier(FIXTURES / filename)
            result = evaluate_supplier(rfq["items"], supplier)

            actual_technical = [
                item.get("technical_status")
                for item in result["items"]
            ]

            actual_quantity = [
                item.get("quantity_status")
                for item in result["items"]
            ]

            errors = []

            if actual_technical != expected["technical"]:
                errors.append(
                    f"Technical expected {expected['technical']}, "
                    f"got {actual_technical}"
                )

            if actual_quantity != expected["quantity"]:
                errors.append(
                    f"Quantity expected {expected['quantity']}, "
                    f"got {actual_quantity}"
                )

            if result.get("eligible_for_ranking") != expected["eligible"]:
                errors.append(
                    f"Eligibility expected {expected['eligible']}, "
                    f"got {result.get('eligible_for_ranking')}"
                )

            if "vat" in expected:
                actual_vat = float(result.get("vat") or 0)

                if abs(actual_vat - expected["vat"]) > 0.01:
                    errors.append(
                        f"VAT expected {expected['vat']}, got {actual_vat}"
                    )

            if errors:
                print(f"\nFAIL | {filename}")
                for error in errors:
                    print("  -", error)
                failed += 1
            else:
                print(f"\nPASS | {filename}")
                passed += 1

        except Exception as error:
            print(f"\nERROR | {filename}")
            print(f"  {type(error).__name__}: {error}")
            failed += 1

    print("\n" + "=" * 65)
    print(f"TESTS PASSED: {passed}")
    print(f"TESTS FAILED: {failed}")
    print("=" * 65)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
