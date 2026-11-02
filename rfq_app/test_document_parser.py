from rfq_app.document_parser import parse_document_quote

sample_text = """
Supplier Name: Desert Star Trading LLC
Quotation Number: DST-2026-102
Currency: AED
Delivery: 14 days
Payment Terms: 30 days

Deep Groove Ball Bearing | 100 | 43
Deep Groove Ball Bearing | 50 | 50

Freight: 100
Discount: 0
VAT: 0
"""

result = parse_document_quote(
    sample_text,
    "sample_supplier.pdf"
)

print("SUPPLIER:", result["supplier"])
print("QUOTE:", result["quote_number"])
print("CURRENCY:", result["currency"])
print("ITEMS:", result["items"])
print("FREIGHT:", result["freight"])
print("WARNINGS:", result["warnings"])