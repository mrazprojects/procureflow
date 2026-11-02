from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill,Alignment
from openpyxl.utils import get_column_letter

def build_report(evaluations):
    wb=Workbook(); ws=wb.active; ws.title="Supplier Summary"
    ws.append(["Supplier","Quote No","Currency","Line Total","Freight","Discount","VAT","Commercial Total","Delivery","Payment","Scope Complete","Technical Status","Eligible"])
    for e in evaluations:
        ws.append([e["supplier"],e["quote_number"],e["currency"],e["quoted_line_total"],e["freight"],e["discount"],e["vat"],e["commercial_total"],e["delivery"],e["payment"],"YES" if e["coverage_complete"] else "NO","COMPLIANT" if e["technically_compliant"] else "REVIEW / NON-COMPLIANT","YES" if e["eligible_for_ranking"] else "NO"])
    detail=wb.create_sheet("Item Comparison")
    detail.append(["Supplier","RFQ Item","Supplier Item","Required Qty","Offered Qty","Unit Price","Line Total","Match Score","Technical Status","Details"])
    for e in evaluations:
        for x in e["items"]:
            detail.append([e["supplier"],x["rfq_item"],x["supplier_item"],x["quantity_required"],x["quantity_offered"],x["unit_price"],x["line_total"],x["match_score"],x["technical_status"],x["details"]])
    extra=wb.create_sheet("Additional Items"); extra.append(["Supplier","Additional Quoted Item"])
    for e in evaluations:
        for x in e["extra_items"]: extra.append([e["supplier"],x])
    for sh in wb.worksheets:
        sh.freeze_panes="A2"; sh.auto_filter.ref=sh.dimensions
        for c in sh[1]:
            c.font=Font(bold=True,color="FFFFFF"); c.fill=PatternFill("solid",fgColor="1F4E78"); c.alignment=Alignment(wrap_text=True)
        for col in sh.columns:
            letter=get_column_letter(col[0].column)
            sh.column_dimensions[letter].width=min(max(max(len(str(c.value or "")) for c in col)+2,12),48)
    return wb
