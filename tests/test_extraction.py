from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from rfq_app.quotation_reader import read_supplier_excel
from rfq_app.extractors import extract_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_excel(file_path):
    with file_path.open("rb") as file:
        result = read_supplier_excel(file)

    return (
        f"Supplier: {result.get('supplier')} | "
        f"Items: {len(result.get('items', []))}"
    )


def test_document(file_path):
    with file_path.open("rb") as file:
        text = extract_text(file)

    if not text or not text.strip():
        raise ValueError("No text extracted")

    return f"Extracted characters: {len(text)}"


def main():
    extensions = {".xlsx", ".xlsm", ".pdf", ".png", ".jpg", ".jpeg", ".txt"}

    files = [
        file for file in FIXTURES.iterdir()
        if file.is_file()
        and file.suffix.lower() in extensions
        and file.name.lower() != "readme_test_guide.txt"
    ]

    passed = 0
    failed = 0

    print("\nPROCUREFLOW EXTRACTION TEST")
    print("=" * 60)

    for file_path in sorted(files):
        try:
            if file_path.suffix.lower() in {".xlsx", ".xlsm"}:
                details = test_excel(file_path)
            else:
                details = test_document(file_path)

            print(f"\nPASS | {file_path.name}")
            print(f"       {details}")
            passed += 1

        except Exception as error:
            print(f"\nFAIL | {file_path.name}")
            print(f"       {type(error).__name__}: {error}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"TOTAL: {passed + failed}")
    print(f"PASSED: {passed}")
    print(f"FAILED: {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
