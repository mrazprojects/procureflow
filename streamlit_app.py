import io
import re

import pandas as pd
import plotly.express as px
import streamlit as st

from rfq_app.rfq_reader import read_rfq_excel
from rfq_app.quotation_reader import (
    read_supplier_excel,
    read_unstructured_quote,
)
from rfq_app.document_parser import parse_document_quote
from rfq_app.evaluator import evaluate_supplier
from rfq_app.report import build_report
from rfq_app.ai_pipeline import process_quote_text


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="ProcureFlow | RFQ Evaluation",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# CUSTOM STYLING
# =========================================================

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
    :root { --navy:#142B45; --blue:#2563A6; --muted:#64748B; --line:#E3EAF1; --canvas:#F4F7FB; }
    html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
    .stApp { background:var(--canvas); }
    [data-testid="stHeader"] { background:rgba(244,247,251,.92); }
    [data-testid="stSidebar"] { background:linear-gradient(180deg,#10263E 0%,#183B5D 100%); border-right:1px solid #24425E; }
    [data-testid="stSidebar"] * { color:#F3F7FC; }
    [data-testid="stSidebar"] [data-testid="stFileUploader"] { color:#172B43; }
    [data-testid="stSidebar"] hr { border-color:rgba(255,255,255,.16); }
    .brand-kicker { color:#6B8BAA;font-size:.72rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;margin-bottom:.4rem; }
    .hero-title { color:var(--navy);font-size:2.25rem;font-weight:700;letter-spacing:-.045em;line-height:1.12;margin:0; }
    .hero-subtitle { color:var(--muted);font-size:.98rem;margin-top:.55rem;margin-bottom:1.15rem; }
    .section-title { color:var(--navy);font-size:1.2rem;font-weight:700;margin-bottom:.15rem; }
    .section-caption { color:#718096;font-size:.88rem;margin-bottom:.9rem; }
    .step-label { color:var(--blue);font-size:.70rem;font-weight:700;letter-spacing:.13em;text-transform:uppercase; }
    div[data-testid="stMetric"] { background:#fff;border:1px solid var(--line);border-radius:14px;padding:17px 19px;box-shadow:0 3px 12px rgba(20,43,69,.045); }
    div[data-testid="stMetricLabel"] { color:#718096;font-weight:600; }
    div[data-testid="stMetricValue"] { color:var(--navy);font-weight:700; }
    div.stButton > button[kind="primary"], div[data-testid="stDownloadButton"] > button { background:#1D68A8;color:#fff;border:1px solid #1D68A8;border-radius:9px;font-weight:600;padding:.55rem 1.1rem; }
    div.stButton > button[kind="primary"]:hover, div[data-testid="stDownloadButton"] > button:hover { background:#155487;border-color:#155487;color:#fff; }
    div[data-testid="stFileUploader"] { background:#fff;border:1px dashed #AFC2D5;border-radius:13px;padding:12px; }
    div[data-testid="stDataFrame"] { border:1px solid var(--line);border-radius:11px;overflow:hidden; }
    div[data-testid="stExpander"] { background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden; }
    div[data-testid="stVerticalBlockBorderWrapper"] { border-color:var(--line)!important;border-radius:13px!important; }
    .status-note { background:#EAF2F9;border-left:4px solid #2874B8;border-radius:7px;padding:.8rem 1rem;color:#29445F;font-size:.9rem; }
    hr { border-color:#E2E8F0; }
    footer { visibility:hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.markdown("## ◈ ProcureFlow")
    st.caption("PROCUREMENT INTELLIGENCE")
    st.divider()

    st.markdown("### WORKFLOW")
    st.markdown(
        """
        **01**  Buyer RFQ

        **02**  Supplier quotations

        **03**  Technical & commercial review

        **04**  Evaluation report
        """
    )

    st.divider()
    st.markdown("### ABOUT THIS TOOL")
    st.caption(
        "A free procurement decision-support prototype that helps "
        "organise supplier quotations and compare bids."
    )
    st.info(
        "Runs locally without a paid AI API. Excel uses structured parsing; "
        "document quotations use rule-based extraction with local Qwen AI "
        "cross-checking. Human verification remains essential."
    )
    st.caption("Human review is required before any sourcing decision.")


# =========================================================
# HEADER
# =========================================================

header_left, header_right = st.columns([4, 1])
with header_left:
    st.markdown(
        '<div class="brand-kicker">PROCUREMENT INTELLIGENCE WORKSPACE</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<h1 class="hero-title">RFQ Evaluation</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="hero-subtitle">A single workspace to process quotations, '
        'validate supplier compliance and compare evaluated bids.</p>',
        unsafe_allow_html=True,
    )
with header_right:
    st.markdown(
        '<div style="text-align:right;padding-top:12px;">'
        '<span style="display:inline-block;background:#E7F3EC;color:#23734A;'
        'padding:7px 11px;border-radius:20px;font-size:12px;font-weight:700;">'
        '● LOCAL AI WORKSPACE</span><br>'
        '<span style="color:#718096;font-size:12px;">Human review enabled</span>'
        '</div>',
        unsafe_allow_html=True,
    )

st.divider()


# =========================================================
# STEP 1: BUYER RFQ UPLOAD
# =========================================================

st.markdown('<div class="step-label">STEP 01</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-title">Buyer Request for Quotation</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="section-caption">Start by uploading the buyer RFQ in Excel format.</div>',
    unsafe_allow_html=True,
)

rfq_file = st.file_uploader(
    "Upload buyer RFQ",
    type=["xlsx", "xlsm"],
    key="rfq_upload",
    help="Upload the buyer's RFQ Excel workbook.",
)

if rfq_file is None:
    st.info("Upload a buyer RFQ Excel file to begin the evaluation.")
    st.stop()

try:
    rfq = read_rfq_excel(rfq_file)
except Exception as error:
    st.error(f"Unable to read buyer RFQ: {error}")
    st.stop()

rfq_items = rfq.get("items", [])
if not rfq_items:
    st.error("The uploaded RFQ does not contain any readable line items.")
    st.stop()

rfq_table = pd.DataFrame(
    [
        {
            "Item No.": item.get("item_no"),
            "Description": item.get("description"),
            "Quantity": item.get("quantity"),
            "Unit": item.get("unit"),
            "Manufacturer": item.get("manufacturer"),
            "Model": item.get("model"),
            "Specifications": ", ".join(
                f"{key}: {value}"
                for key, value in item.get("specifications", {}).items()
            ),
        }
        for item in rfq_items
    ]
)

with st.container(border=True):
    col_a, col_b = st.columns([1, 3])
    with col_a:
        st.metric("RFQ line items", len(rfq_items))
    with col_b:
        st.markdown("**Buyer RFQ loaded successfully**")
        st.caption(f"Source file: {rfq_file.name}")

    st.dataframe(rfq_table, use_container_width=True, hide_index=True)

if rfq.get("errors"):
    st.warning("RFQ checks: " + " | ".join(rfq["errors"]))


# =========================================================
# STEP 2: SUPPLIER QUOTATION UPLOAD
# =========================================================

st.divider()
st.markdown('<div class="step-label">STEP 02</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-title">Supplier Quotations</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="section-caption">Upload one or more supplier responses for evaluation.</div>',
    unsafe_allow_html=True,
)

quotes = st.file_uploader(
    "Upload supplier quotation files",
    type=["xlsx", "xlsm", "pdf", "docx", "txt", "png", "jpg", "jpeg"],
    accept_multiple_files=True,
    key="supplier_upload",
    help="Supported: Excel, text-based PDF, Word, TXT and image files.",
)

if not quotes:
    st.info("Once you upload supplier quotations, the comparison will appear here.")
    st.stop()

suppliers = []
extracted_documents = []
processing_errors = []

for uploaded_file in quotes:
    try:
        filename = uploaded_file.name.lower()

        if filename.endswith((".xlsx", ".xlsm")):
            supplier_data = read_supplier_excel(uploaded_file)
            supplier_data["source_file"] = uploaded_file.name
            supplier_data["extraction_method"] = "Structured Excel"
            supplier_data["ai_extraction_success"] = False
            supplier_data["ai_fallback_used"] = False
            supplier_data["ai_discrepancies"] = []
            supplier_data["warnings"] = supplier_data.get("warnings", [])

            # Structured Excel is still subject to review when VAT needs checking.
            supplier_data["requires_human_review"] = bool(
                supplier_data.get("vat_review_required", False)
            )
            suppliers.append(supplier_data)

        else:
            extracted = read_unstructured_quote(uploaded_file)
            quotation_text = extracted.get("extracted_text", "") or ""

            pipeline_result = process_quote_text(
                quotation_text,
                filename=uploaded_file.name,
                use_ai=True,
            )

            if not pipeline_result.get("success"):
                extracted_documents.append(
                    {
                        "filename": uploaded_file.name,
                        "text": quotation_text,
                        "warnings": pipeline_result.get("warnings", []),
                        "extraction_method": pipeline_result.get(
                            "extraction_method", "Extraction failed"
                        ),
                        "ai_extraction_success": pipeline_result.get(
                            "ai_extraction_success", False
                        ),
                        "discrepancies": pipeline_result.get("discrepancies", []),
                    }
                )
                processing_errors.append(
                    f"{uploaded_file.name}: No usable quotation items were extracted. "
                    "Manual review is required."
                )
                continue

            supplier_data = pipeline_result["selected_data"]
            supplier_data["source_file"] = uploaded_file.name
            supplier_data["extraction_method"] = pipeline_result.get(
                "extraction_method", "Unknown"
            )
            supplier_data["ai_extraction_success"] = pipeline_result.get(
                "ai_extraction_success", False
            )
            supplier_data["ai_fallback_used"] = bool(
                pipeline_result.get(
                    "ai_fallback_used",
                    supplier_data.get("ai_fallback_used", False),
                )
            )
            supplier_data["ai_discrepancies"] = pipeline_result.get(
                "discrepancies", []
            )
            supplier_data["warnings"] = pipeline_result.get("warnings", [])
            supplier_data["requires_human_review"] = pipeline_result.get(
                "requires_human_review", False
            )

            suppliers.append(supplier_data)

            extracted_documents.append(
                {
                    "filename": uploaded_file.name,
                    "text": quotation_text,
                    "warnings": pipeline_result.get("warnings", []),
                    "extraction_method": pipeline_result.get(
                        "extraction_method", "Unknown"
                    ),
                    "ai_extraction_success": pipeline_result.get(
                        "ai_extraction_success", False
                    ),
                    "discrepancies": pipeline_result.get("discrepancies", []),
                }
            )

    except Exception as error:
        processing_errors.append(f"{uploaded_file.name}: {error}")

for message in processing_errors:
    st.warning(message)

if extracted_documents:
    with st.expander(
        "Review extracted document text, AI checks and warnings",
        expanded=False,
    ):
        st.caption(
            "Compare the extracted information with the original quotation. "
            "AI extraction and rule-based parsing do not confirm technical compliance."
        )

        for document in extracted_documents:
            st.markdown(f"**{document['filename']}**")
            st.caption(
                f"Extraction method: {document.get('extraction_method', 'Not available')} | "
                f"AI extraction successful: "
                f"{'Yes' if document.get('ai_extraction_success') else 'No'}"
            )

            if document.get("discrepancies"):
                st.warning("Differences detected between extraction methods:")
                st.dataframe(
                    pd.DataFrame(document["discrepancies"]),
                    use_container_width=True,
                    hide_index=True,
                )

            st.text_area(
                f"Extracted text — {document['filename']}",
                document["text"] or "No readable text found.",
                height=160,
                key=f"text_{document['filename']}",
            )

            for warning in document["warnings"]:
                st.warning(warning)

if not suppliers:
    st.error(
        "No structured supplier data is available for comparison. "
        "Review the extraction messages above."
    )
    st.stop()


# =========================================================
# STEP 3: SUPPLIER EVALUATION
# =========================================================

st.divider()
st.markdown('<div class="step-label">STEP 03</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-title">Evaluation Overview</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="section-caption">Review the supplier data captured by the application.</div>',
    unsafe_allow_html=True,
)

evaluations = []

for supplier in suppliers:
    evaluation = evaluate_supplier(rfq["items"], supplier)

    # The evaluator handles technical and quantity rules. This additional
    # gate prevents unresolved extraction/commercial issues from being ranked.
    review_reasons = []

    if supplier.get("ai_fallback_used"):
        review_reasons.append(
            "AI fallback was used because rule-based extraction found no usable items."
        )

    if supplier.get("requires_human_review"):
        review_reasons.append(
            "The extraction pipeline has flagged this quotation for human review."
        )

    if supplier.get("vat_review_required"):
        review_reasons.append("VAT information requires verification.")

    if supplier.get("freight_review_required"):
        review_reasons.append("Freight amount requires verification.")

    if supplier.get("discount_review_required"):
        review_reasons.append("Discount amount requires verification.")

    discrepancies = supplier.get("ai_discrepancies") or []
    if discrepancies:
        review_reasons.append(
            f"{len(discrepancies)} difference(s) were found between extraction methods."
        )

    evaluation["extraction_method"] = supplier.get(
        "extraction_method", "Structured Excel"
    )
    evaluation["ai_extraction_success"] = supplier.get(
        "ai_extraction_success", False
    )
    evaluation["ranking_review_reasons"] = review_reasons
    evaluation["ranking_review_required"] = bool(review_reasons)

    if review_reasons:
        evaluation["eligible_for_ranking"] = False

    evaluations.append(evaluation)

eligible = [
    evaluation
    for evaluation in evaluations
    if evaluation["eligible_for_ranking"]
]

total_quotations = len(evaluations)
eligible_count = len(eligible)
review_count = total_quotations - eligible_count

supplier_names = {
    str(supplier.get("supplier") or "Supplier not identified")
    .strip()
    .casefold()
    for supplier in suppliers
}
unique_supplier_count = len(supplier_names)

st.markdown("### Evaluation Snapshot")
metric1, metric2, metric3, metric4 = st.columns(4)
metric1.metric("RFQ Line Items", len(rfq_items))
metric2.metric("Quotations Processed", total_quotations)
metric3.metric("Eligible Quotations", eligible_count)
metric4.metric("Require Review", review_count)

st.caption(
    f"{unique_supplier_count} distinct supplier name(s) represented across "
    f"{total_quotations} processed quotation file(s). Each uploaded file is "
    "evaluated as a separate quotation record."
)

with st.expander("View extracted supplier line-item data", expanded=False):
    for supplier in suppliers:
        st.markdown(f"**{supplier.get('supplier', 'Supplier not identified')}**")
        st.dataframe(
            pd.DataFrame(supplier.get("items", [])),
            use_container_width=True,
            hide_index=True,
        )


# =========================================================
# STEP 4: SUPPLIER COMPARISON
# =========================================================

st.divider()
st.markdown('<div class="step-label">STEP 04</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-title">Supplier Comparison</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="section-caption">Compare commercial totals alongside scope and technical status.</div>',
    unsafe_allow_html=True,
)

summary = pd.DataFrame(
    [
        {
            "Supplier": evaluation["supplier"],
            "Quotation No.": evaluation.get("quote_number") or "Not provided",
            "Source File": suppliers[index].get("source_file") or "Not recorded",
            "Currency": evaluation["currency"],
            "Line Total": evaluation["quoted_line_total"],
            "Freight": evaluation["freight"],
            "Discount": evaluation["discount"],
            "VAT": evaluation["vat"],
            "Commercial Total": evaluation["commercial_total"],
            "Scope Complete": (
                "Yes" if evaluation["coverage_complete"] else "No"
            ),
            "Technically Compliant": (
                "Yes" if evaluation["technically_compliant"] else "Review"
            ),
            "Eligible": (
                "Yes" if evaluation["eligible_for_ranking"] else "No"
            ),
        }
        for index, evaluation in enumerate(evaluations)
    ]
)

st.dataframe(
    summary,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Line Total": st.column_config.NumberColumn(format="%.2f"),
        "Freight": st.column_config.NumberColumn(format="%.2f"),
        "Discount": st.column_config.NumberColumn(format="%.2f"),
        "VAT": st.column_config.NumberColumn(format="%.2f"),
        "Commercial Total": st.column_config.NumberColumn(format="%.2f"),
    },
)

if eligible:
    currencies = {evaluation["currency"] for evaluation in eligible}

    if len(currencies) == 1:
        chart_data = pd.DataFrame(
            [
                {
                    "Supplier": evaluation["supplier"],
                    "Evaluated total": evaluation["commercial_total"],
                }
                for evaluation in eligible
            ]
        )

        chart_col, result_col = st.columns([3, 2])

        with chart_col:
            st.markdown("**Commercial comparison — eligible quotations only**")
            fig = px.bar(
                chart_data,
                x="Supplier",
                y="Evaluated total",
                color="Supplier",
                text_auto=".2f",
            )
            fig.update_layout(
                showlegend=False,
                plot_bgcolor="white",
                paper_bgcolor="white",
                margin=dict(l=10, r=10, t=25, b=10),
                yaxis_title=f"Evaluated total ({next(iter(currencies))})",
                xaxis_title="",
            )
            st.plotly_chart(fig, use_container_width=True)

        winner = min(
            eligible,
            key=lambda evaluation: evaluation["commercial_total"],
        )

        with result_col:
            st.markdown("**Lowest evaluated eligible offer**")
            with st.container(border=True):
                st.caption("Lowest commercial total among eligible quotations")
                st.subheader(winner["supplier"])
                st.metric(
                    "Evaluated total",
                    f"{winner['commercial_total']:,.2f} {winner['currency']}",
                )
                st.success(
                    "Eligible for commercial ranking based on the current "
                    "evaluation rules. Final award decision requires human review."
                )
    else:
        st.warning(
            "Different currencies detected. Cross-currency ranking is disabled."
        )
else:
    st.warning(
        "No supplier currently meets both complete-scope and technical "
        "compliance requirements. Resolve outstanding clarifications before ranking."
    )


# =========================================================
# STEP 5: ITEM-WISE EVALUATION
# =========================================================

st.divider()
st.markdown('<div class="step-label">STEP 05</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-title">Item-wise Evaluation</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="section-caption">Inspect each supplier\'s quoted items and commercial terms.</div>',
    unsafe_allow_html=True,
)

for index, evaluation in enumerate(evaluations):
    source_name = suppliers[index].get("source_file") or "Source file not recorded"
    supplier_title = (
        f"{evaluation['supplier']} — "
        f"{evaluation['quote_number'] or 'Quote number not provided'} "
        f"— {source_name}"
    )

    with st.expander(supplier_title, expanded=False):
        status_col, total_col = st.columns([2, 1])

        with status_col:
            if evaluation["eligible_for_ranking"]:
                st.success("Eligible for ranking")
            else:
                st.warning("Not currently eligible — review required")

            if evaluation.get("ranking_review_reasons"):
                st.markdown("**Reasons requiring review:**")
                for reason in evaluation["ranking_review_reasons"]:
                    st.write(f"- {reason}")

            st.caption(
                f"Extraction method: {evaluation.get('extraction_method', 'Not recorded')} | "
                f"AI extraction successful: "
                f"{'Yes' if evaluation.get('ai_extraction_success') else 'No / Not used'}"
            )

        with total_col:
            st.metric(
                "Commercial total",
                f"{evaluation['commercial_total']:,.2f} {evaluation['currency']}",
            )

        delivery_col, payment_col = st.columns(2)
        delivery_col.write(
            f"**Delivery:** {evaluation['delivery'] or 'Not provided'}"
        )
        payment_col.write(
            f"**Payment:** {evaluation['payment'] or 'Not provided'}"
        )

        # Show item-level results in a readable table, then expose each
        # technical check directly instead of hiding it in a tooltip cell.
        item_records = evaluation.get("items", [])

        if item_records:
            st.markdown("### Item evaluation summary")

            summary_rows = []
            for item in item_records:
                summary_rows.append(
                    {
                        "RFQ item": item.get("rfq_item", "Not identified"),
                        "Supplier item": item.get("supplier_item", "Not identified"),
                        "Qty required": item.get("quantity_required"),
                        "Qty offered": item.get("quantity_offered"),
                        "Unit price": item.get("unit_price"),
                        "Line total": item.get("line_total"),
                        "Technical status": item.get("technical_status", "Review"),
                        "Quantity status": item.get("quantity_status", "Review"),
                        "Match score": item.get("match_score"),
                    }
                )

            st.dataframe(
                pd.DataFrame(summary_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Unit price": st.column_config.NumberColumn(format="%.2f"),
                    "Line total": st.column_config.NumberColumn(format="%.2f"),
                    "Match score": st.column_config.NumberColumn(format="%.1f"),
                },
            )

            st.markdown("### Specification checks")
            for item_number, item in enumerate(item_records, start=1):
                item_name = item.get("rfq_item") or item.get("supplier_item") or f"Item {item_number}"
                st.markdown(f"**Item {item_number}: {item_name}**")

                detail_text = str(item.get("details") or "")
                check_rows = []

                # Current evaluator details use semicolon-separated checks,
                # for example: manufacturer: required 'SKF', offered 'SKF' = MATCH.
                for part in detail_text.split(";"):
                    part = part.strip().rstrip(".")
                    match = re.match(
                        r"([^:]+):\s*required\s*'([^']*)',\s*offered\s*'([^']*)'\s*=\s*(.+)",
                        part,
                        flags=re.IGNORECASE,
                    )
                    if match:
                        check_rows.append(
                            {
                                "Specification": match.group(1).strip().replace("_", " ").title(),
                                "RFQ requirement": match.group(2).strip() or "Not specified",
                                "Supplier offer": match.group(3).strip() or "Not provided",
                                "Result": match.group(4).strip().upper(),
                            }
                        )

                if check_rows:
                    st.dataframe(
                        pd.DataFrame(check_rows),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Specification": st.column_config.TextColumn(width="medium"),
                            "RFQ requirement": st.column_config.TextColumn(width="medium"),
                            "Supplier offer": st.column_config.TextColumn(width="medium"),
                            "Result": st.column_config.TextColumn(width="small"),
                        },
                    )
                elif detail_text:
                    st.info(detail_text)
                else:
                    st.caption("No detailed specification checks were provided by the evaluator.")

                if item.get("quantity_status"):
                    st.caption(f"Quantity assessment: {item['quantity_status']}")

                st.divider()

        if evaluation.get("extra_items"):
            st.write(
                "**Additional items:**",
                ", ".join(evaluation["extra_items"]),
            )


# =========================================================
# STEP 6: HUMAN REVIEW
# =========================================================

st.divider()
st.markdown('<div class="step-label">STEP 06</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-title">Human Review & Verification</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="section-caption">Confirm that the source quotations have been checked before using the comparison.</div>',
    unsafe_allow_html=True,
)

st.warning(
    "Verify extracted descriptions, manufacturer, model, specifications, "
    "quantities, prices, currency, taxes and commercial terms against the "
    "original supplier quotations. The application does not make the final award decision."
)

review_columns = st.columns(2)
for index, evaluation in enumerate(evaluations):
    source_name = suppliers[index].get("source_file") or "Source file not recorded"
    quote_reference = evaluation.get("quote_number") or "Quote number not provided"

    with review_columns[index % 2]:
        st.checkbox(
            f"Reviewed: {evaluation['supplier']} | {quote_reference} | {source_name}",
            key=f"review_{index}",
        )


# =========================================================
# STEP 7: REPORT DOWNLOAD
# =========================================================

st.divider()
st.markdown('<div class="step-label">STEP 07</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-title">Export Evaluation Report</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="section-caption">Generate an Excel workbook containing the supplier evaluation results.</div>',
    unsafe_allow_html=True,
)

try:
    output = io.BytesIO()
    build_report(evaluations).save(output)
    report_bytes = output.getvalue()

    st.download_button(
        label="⬇  Download Supplier Comparison Report",
        data=report_bytes,
        file_name="RFQ_Supplier_Comparison_Report.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        type="primary",
    )
except Exception as error:
    st.error(f"Report generation failed: {error}")


# =========================================================
# FOOTER
# =========================================================

st.divider()
st.caption(
    "ProcureFlow | Procurement automation prototype | "
    "Rule-based evaluation | Human verification required"
)
