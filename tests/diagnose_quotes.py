from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rfq_app.extractors import extract_text
from rfq_app.document_parser import parse_document_quote
from rfq_app.rfq_reader import read_rfq_excel
from rfq_app.evaluator import evaluate_supplier

fixtures = ROOT / "tests" / "fixtures"

with (ROOT / "data" / "samples" / "sample_rfq.xlsx").open("rb") as f:
    rfq = read_rfq_excel(f)

files = [
    "02_Desert_Star_Trading_LLC.pdf",
    "09_Crescent_Industrial_LLC.png",
]

for name in files:
    print("\n" + "=" * 65)
    print("FILE:", name)

    path = fixtures / name

    with path.open("rb") as f:
        extracted_text = extract_text(f)

    supplier = parse_document_quote(extracted_text, name)
    result = evaluate_supplier(rfq["items"], supplier)

    print("\nEXTRACTED TEXT:")
    print(extracted_text)

    print("\nVAT INFORMATION:")
    for key in [
        "vat", "vat_type", "vat_rate",
        "vat_review_required", "vat_raw"
    ]:
        print(key, ":", supplier.get(key))

    print("\nITEM EVALUATION:")
    for item in result["items"]:
        print("\nRFQ ITEM:", item.get("rfq_item"))
        print("SUPPLIER ITEM:", item.get("supplier_item"))
        print("STATUS:", item.get("technical_status"))
        print("DETAILS:", item.get("details"))
