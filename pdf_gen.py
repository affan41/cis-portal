import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER

DARK = colors.HexColor("#2e3a4f")
GREY = colors.HexColor("#666666")
LIGHT_LINE = colors.HexColor("#cccccc")


def _fmt(n):
    return f"{n:,.2f}"


def generate_cis_pdf(
    contractor_name,
    contractor_address,
    paye_ref,
    period_label,
    tax_month_ended,
    subcontractor_name,
    utr,
    verification_number,
    invoices,
    totals,
):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
    )

    # Styles
    title_style = ParagraphStyle("title", fontSize=18, textColor=DARK, fontName="Helvetica-Bold", leading=22)
    subtitle_style = ParagraphStyle("subtitle", fontSize=13, textColor=DARK, fontName="Helvetica-Bold", leading=18)
    section_style = ParagraphStyle("section", fontSize=13, textColor=DARK, fontName="Helvetica-Bold", leading=18, spaceBefore=14)
    normal = ParagraphStyle("normal", fontSize=9, textColor=DARK, fontName="Helvetica", leading=12)
    small_grey = ParagraphStyle("smallgrey", fontSize=8.5, textColor=GREY, fontName="Helvetica", leading=11)
    footer_style = ParagraphStyle("footer", fontSize=7.5, textColor=GREY, fontName="Helvetica", alignment=TA_LEFT)
    footer_right = ParagraphStyle("footerR", fontSize=7.5, textColor=GREY, fontName="Helvetica", alignment=TA_RIGHT)

    story = []

    # --- Header ---
    story.append(Paragraph("Construction Industry Scheme", title_style))
    story.append(Paragraph("Payment and Deduction Statement", title_style))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"<b>{contractor_name}</b>", subtitle_style))
    story.append(Paragraph(f"For the period {period_label}", subtitle_style))
    story.append(Spacer(1, 8 * mm))

    # --- Contractor details ---
    story.append(Paragraph("<b>Contractor details</b>", section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT_LINE, spaceAfter=4))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(f"<b>{contractor_name}</b>", normal))
    story.append(Paragraph(contractor_address, small_grey))
    story.append(Spacer(1, 4 * mm))

    info_data = [
        ["Payment and deduction made in tax month ended", tax_month_ended],
        ["Employer's PAYE reference", paye_ref],
    ]
    info_table = Table(info_data, colWidths=[95 * mm, 75 * mm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), GREY),
        ("TEXTCOLOR", (1, 0), (1, -1), DARK),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (0, 0), (-1, 0), 0.3, LIGHT_LINE),
        ("LINEBELOW", (0, 1), (-1, 1), 0.3, LIGHT_LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8 * mm))

    # --- Subcontractor details ---
    story.append(Paragraph("<b>Subcontractor details</b>", section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT_LINE, spaceAfter=4))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(f"<b>{subcontractor_name}</b>", normal))
    story.append(Spacer(1, 3 * mm))

    # Two-column layout: left = UTR/SVN, right = amounts
    sub_data = [
        ["Unique taxpayers reference", utr or "—", "Gross paid (excl VAT) (A)", _fmt(totals["gross"])],
        ["Verification number", verification_number or "—", "Less cost of materials", _fmt(totals["materials"])],
        ["", "", "Less non-CIS", _fmt(totals["non_cis"])],
        ["", "", "Liable to deduction", _fmt(totals["liable"])],
        ["", "", "Deducted (B)", _fmt(totals["cis_deduction"])],
        ["", "", "Paid (A - B)", _fmt(totals["paid"])],
    ]
    sub_table = Table(sub_data, colWidths=[45 * mm, 40 * mm, 45 * mm, 40 * mm])
    sub_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), GREY),
        ("TEXTCOLOR", (2, 0), (2, -1), GREY),
        ("TEXTCOLOR", (1, 0), (1, -1), DARK),
        ("TEXTCOLOR", (3, 0), (3, -1), DARK),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, 0), 0.3, LIGHT_LINE),
        ("LINEBELOW", (0, 1), (-1, 1), 0.3, LIGHT_LINE),
        ("LINEBELOW", (2, 2), (3, 2), 0.3, LIGHT_LINE),
        ("LINEBELOW", (2, 3), (3, 3), 0.3, LIGHT_LINE),
        ("LINEBELOW", (2, 4), (3, 4), 0.3, LIGHT_LINE),
        ("LINEBELOW", (2, 5), (3, 5), 0.3, LIGHT_LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (3, 0), (3, -1), 0),
    ]))
    story.append(sub_table)
    story.append(Spacer(1, 10 * mm))

    # --- Source invoices ---
    story.append(Paragraph("<b>Source invoices</b>", section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT_LINE, spaceAfter=4))
    story.append(Spacer(1, 2 * mm))

    inv_header = ["Reference", "Payment date", "Gross\n(A)", "Materials", "Non-CIS", "Labour", "CIS\n(B)", "Paid\n(A - B)"]
    inv_rows = [inv_header]
    for inv in invoices:
        inv_rows.append([
            inv["reference"],
            inv["payment_date"],
            _fmt(inv["gross"]),
            _fmt(inv["materials"]),
            _fmt(inv["non_cis"]),
            _fmt(inv["labour"]),
            _fmt(inv["cis_deduction"]),
            _fmt(inv["paid"]),
        ])

    col_w = [26 * mm, 26 * mm, 20 * mm, 20 * mm, 18 * mm, 22 * mm, 18 * mm, 22 * mm]
    inv_table = Table(inv_rows, colWidths=col_w, repeatRows=1)
    n = len(inv_rows)
    inv_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), GREY),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, LIGHT_LINE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, LIGHT_LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(inv_table)

    # --- Footer ---
    story.append(Spacer(1, 20 * mm))
    footer_data = [
        [Paragraph(f"CIS Payment Deduction Statement | {contractor_name}", footer_style),
         Paragraph("1 of 1", footer_right)],
    ]
    ft = Table(footer_data, colWidths=[130 * mm, 40 * mm])
    ft.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LINEABOVE", (0, 0), (-1, 0), 0.3, LIGHT_LINE),
    ]))
    story.append(ft)

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
