from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from rfq_app.rfq_reader import read_rfq_excel
from rfq_app.quotation_reader import read_supplier_excel
from rfq_app.document_parser import parse_document_quote
from rfq_app.extractors import extract_text
from rfq_app.evaluator import evaluate_supplier

FIXTURES = Path(__file__).parent / "fixtures"
RFQ_FILE = PROJECT_ROOT / "data" / "samples" / "sample_rfq.xlsx"

SUPPLIER_FILES = [
    "01_Gulf_Industrial_Supplies_LLC.xlsx",
    "02_Desert_Star_Trading_LLC.pdf",
    "03_Apex_Bearing_House.png",
    "04_Metro_Industrial_Trading.xlsx",
    "05_Prime_Motion_Components.pdf",
    "06_Universal_Bearings_FZE.png",
    "07_Al_Noor_Mechanical_Supplies.xlsx",
    "08_Eastern_Technical_Stores.pdf",
    "09_Crescent_Industrial_LLC.png",
    "10_Vertex_Engineering_Trading.xlsx",
]


def load_supplier(file_path):
    if file_path.suffix.lower() in {".xlsx", ".xlsm"}:
        with file_path.open("rb") as file:
            return read_supplier_excel(file)

    with file_path.open("rb") as file:
        extracted_text = extract_text(file)

    return parse_document_quote(extracted_text, file_path.name)


def main():
    with RFQ_FILE.open("rb") as file:
        rfq = read_rfq_excel(file)

    print("\nPROCUREFLOW - FULL SUPPLIER EVALUATION")
    print("=" * 70)

    passed = 0
    failed = 0

    for filename in SUPPLIER_FILES:
        file_path = FIXTURES / filename

        try:
            supplier = load_supplier(file_path)

            if not supplier.get("items"):
                raise ValueError("No quotation items were extracted")

            result = evaluate_supplier(rfq["items"], supplier)

            print(f"\nSUPPLIER: {result.get('supplier')}")
            print(f"FILE: {filename}")
            print(f"ITEMS EVALUATED: {len(result.get('items', []))}")
            print(f"SCOPE COMPLETE: {result.get('coverage_complete')}")
            print(f"TECHNICALLY COMPLIANT: {result.get('technically_compliant')}")
            print(f"FULL QUANTITY MATCH: {result.get('full_quantity_match')}")
            print(f"ELIGIBLE FOR RANKING: {result.get('eligible_for_ranking')}")
            print(f"CURRENCY: {result.get('currency')}")
            print(f"VAT: {result.get('vat')}")
            print(f"VAT TYPE: {result.get('vat_type')}")
            print(f"VAT REVIEW REQUIRED: {result.get('vat_review_required')}")
            print(f"COMMERCIAL TOTAL: {result.get('commercial_total')}")

            for item in result.get("items", []):
                print(
                    "  ITEM:",
                    item.get("technical_status"),
                    "| QUANTITY:",
                    item.get("quantity_status"),
                )

            passed += 1

        except Exception as error:
            print(f"\nFAIL: {filename}")
            print(f"ERROR: {type(error).__name__}: {error}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"SUPPLIERS PROCESSED: {passed + failed}")
    print(f"SUCCESSFUL: {passed}")
    print(f"FAILED: {failed}")
    print("=" * 70)


if __name__ == "__main__":
    main()
