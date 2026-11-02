from pathlib import Path
from openpyxl import load_workbook

def norm(v):
    return str(v).strip().lower().replace("_", " ").replace("-", " ") if v is not None else ""

def find(headers, names):
    return next((h for h in headers if h in names), None)

def read_rfq_excel(file):
    name = getattr(file, "name", str(file))
    if Path(name).suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("RFQ must be an Excel .xlsx or .xlsm file.")
    if hasattr(file, "seek"): file.seek(0)
    wb = load_workbook(file, data_only=True)
    ws = wb.active
    headers = [norm(c.value) or f"blank_{i}" for i,c in enumerate(ws[1])]
    desc = find(headers, {"item description","description","material description","product description","item"})
    qty = find(headers, {"quantity","qty","required quantity"})
    if not desc or not qty:
        wb.close()
        raise ValueError("Required columns: Item Description and Quantity.")
    itemno = find(headers, {"item no","item number","sl no","line no"})
    unit = find(headers, {"unit","uom","unit of measure"})
    make = find(headers, {"manufacturer","make","brand"})
    model = find(headers, {"model","model number","part number","part no"})
    known = {desc,qty,itemno,unit,make,model}
    specs_cols = [h for h in headers if h not in known and not h.startswith("blank_")]
    items, errors = [], []
    for rn,row in enumerate(ws.iter_rows(min_row=2, values_only=True),2):
        if not any(v is not None for v in row): continue
        d = dict(zip(headers,row))
        if not d.get(desc):
            errors.append(f"Row {rn}: missing description."); continue
        try:
            q=float(d.get(qty))
            if q <= 0: raise ValueError
        except (TypeError,ValueError):
            errors.append(f"Row {rn}: invalid quantity."); continue
        items.append({
            "item_no": d.get(itemno) if itemno and d.get(itemno) is not None else len(items)+1,
            "description": str(d[desc]).strip(), "quantity": q,
            "unit": d.get(unit) if unit else None,
            "manufacturer": d.get(make) if make else None,
            "model": d.get(model) if model else None,
            "specifications": {c:d[c] for c in specs_cols if d.get(c) not in (None,"")}
        })
    sheet=ws.title
    wb.close()
    if not items: raise ValueError("No valid RFQ items found.")
    return {"items":items,"errors":errors,"source_sheet":sheet,"total_items":len(items)}
