# ============================================================
# DOCX REPORT GENERATOR  (branded, section-aware layout)
# ============================================================
#
# Combines:
#
# 1. Cover page
# 2. Company Snapshot infographic (from infographic.py, unchanged)
# 3. Final Market Research Report (LLM narrative), converted into
#    headings / paragraphs / bullets, with:
#      - a Key Financials table injected at the top of the
#        Financial Performance section
#      - Strengths / Risks / Opportunities collapsed into one
#        3-column SWOT table
#      - charts placed next to the section they support instead of
#        dumped at the end
# 4. Research Sources table (accepted_sources only, with real
#    clickable hyperlinks) — the LLM's own "# Sources" narrative is
#    never treated as authoritative and is dropped.
#
# into a single professional Word document.
#
# ============================================================

import os
import re

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from charts import CHART_SECTION_MAP


# ============================================================
# 1. OUTPUT DIRECTORY
# ============================================================

OUTPUT_DIR = "output"

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


# ============================================================
# 2. BRAND PALETTE
# ============================================================

NAVY = RGBColor(0x12, 0x23, 0x3F)
BLUE = RGBColor(0x1F, 0x5F, 0xA8)
GOLD = RGBColor(0xC8, 0x96, 0x3E)
SLATE = RGBColor(0x5B, 0x6B, 0x7C)
TEXT = RGBColor(0x26, 0x31, 0x3F)

NAVY_HEX = "12233F"
GOLD_HEX = "C8963E"
LIGHT_HEX = "F4F6F8"
LIGHT_BORDER_HEX = "D8DEE4"
WHITE_HEX = "FFFFFF"

FONT_NAME = "Aptos"


# ============================================================
# 3. SAFE FILE NAME
# ============================================================

def safe_filename(name):

    name = str(name)

    name = re.sub(
        r'[\\/:*?"<>|]',
        "_",
        name
    )

    name = name.replace(
        " ",
        "_"
    )

    return name


# ============================================================
# 4. DOCUMENT-LEVEL SETUP
# ============================================================

def set_document_margins(document):

    section = document.sections[0]

    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)


def set_default_font(document):

    styles = document.styles

    normal_style = styles["Normal"]

    normal_style.font.name = FONT_NAME
    normal_style.font.size = Pt(10.5)
    normal_style.font.color.rgb = TEXT

    normal_style._element.rPr.rFonts.set(
        qn("w:eastAsia"),
        FONT_NAME
    )

    # Give headings a consistent branded look instead of Word's defaults.
    heading_specs = {
        "Heading 1": (16, NAVY, True),
        "Heading 2": (13, BLUE, True),
        "Heading 3": (11.5, SLATE, True),
    }

    for style_name, (size, color, bold) in heading_specs.items():
        try:
            style = styles[style_name]
        except KeyError:
            continue
        style.font.name = FONT_NAME
        style.font.size = Pt(size)
        style.font.color.rgb = color
        style.font.bold = bold


# ============================================================
# 5. LOW-LEVEL OXML HELPERS
# ============================================================

def set_cell_background(cell, hex_color):

    tc_pr = cell._tc.get_or_add_tcPr()

    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)

    tc_pr.append(shd)


def set_cell_border_color(cell, hex_color, size=4):

    tc_pr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")

    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:color"), hex_color)
        borders.append(el)

    tc_pr.append(borders)


def add_page_number(paragraph):

    # w:fldSimple is a paragraph-level element in its own right (it wraps
    # its own w:r children) -- it must NOT be nested inside a separate
    # w:r, which is invalid OOXML and is silently "fixed" by Word's error
    # recovery but breaks stricter readers/converters. Attach it directly
    # to the paragraph instead.

    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")

    # A cached fallback value so the field displays something sensible
    # even in viewers that render fields without recalculating them
    # (e.g. some headless PDF converters). Word recalculates this to the
    # real page number automatically when the document is opened.
    fallback_run = OxmlElement("w:r")
    fallback_text = OxmlElement("w:t")
    fallback_text.text = "1"
    fallback_run.append(fallback_text)
    field.append(fallback_run)

    paragraph._p.append(field)


def add_hyperlink(paragraph, url, text, color_hex="1F5FA8"):
    """python-docx has no native write support for hyperlinks, so the
    relationship + w:hyperlink element are built manually. This is the
    only reliable way to get a real, clickable Word hyperlink rather
    than plain text that merely looks like a URL."""

    part = paragraph.part
    r_id = part.relate_to(url, RT.HYPERLINK, is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")

    color = OxmlElement("w:color")
    color.set(qn("w:val"), color_hex)
    rpr.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rpr.append(underline)

    rfonts = OxmlElement("w:rFonts")
    rfonts.set(qn("w:ascii"), FONT_NAME)
    rpr.append(rfonts)

    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "17")
    rpr.append(sz)

    new_run.append(rpr)

    text_el = OxmlElement("w:t")
    text_el.text = text
    new_run.append(text_el)

    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)

    return hyperlink


# ============================================================
# 6. INLINE MARKDOWN (bold) PARSING
# ============================================================

def add_inline_runs(paragraph, text, base_size=10.5, base_color=TEXT):
    """Splits on **bold** markers and adds properly bolded runs instead
    of printing literal asterisks, which is what the previous plain
    line-by-line writer did."""

    parts = re.split(r"(\*\*[^*]+\*\*)", text)

    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
            run.font.color.rgb = NAVY
        else:
            run = paragraph.add_run(part)
            run.font.color.rgb = base_color
        run.font.size = Pt(base_size)
        run.font.name = FONT_NAME


# ============================================================
# 7. HEADER / FOOTER
# ============================================================

def add_header_footer(document, company_name, research_date):

    section = document.sections[0]
    section.different_first_page_header_footer = True

    # Cover page gets a blank header/footer so the title page stays clean.
    section.first_page_header.paragraphs[0].text = ""
    section.first_page_footer.paragraphs[0].text = ""

    header_paragraph = section.header.paragraphs[0]
    header_paragraph.text = ""
    header_paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(6.4))

    run = header_paragraph.add_run(f"{company_name.upper()}  ")
    run.bold = True
    run.font.size = Pt(8)
    run.font.color.rgb = NAVY
    run.font.name = FONT_NAME

    run = header_paragraph.add_run("MARKET RESEARCH REPORT")
    run.font.size = Pt(8)
    run.font.color.rgb = SLATE
    run.font.name = FONT_NAME

    run = header_paragraph.add_run(f"\t{research_date.upper()}")
    run.font.size = Pt(8)
    run.font.color.rgb = SLATE
    run.font.name = FONT_NAME

    footer_paragraph = section.footer.paragraphs[0]
    footer_paragraph.text = ""
    footer_paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(6.4))

    run = footer_paragraph.add_run("AI-Assisted Market Research  |  Verified, Source-Matched Data")
    run.font.size = Pt(7.5)
    run.font.color.rgb = SLATE
    run.font.name = FONT_NAME

    run = footer_paragraph.add_run("\tPage ")
    run.font.size = Pt(7.5)
    run.font.color.rgb = SLATE
    run.font.name = FONT_NAME

    add_page_number(footer_paragraph)


# ============================================================
# 8. TITLE PAGE
# ============================================================

def add_title_page(document, company_name, research_date):

    for _ in range(4):
        document.add_paragraph()

    p = document.add_paragraph()
    run = p.add_run("MARKET RESEARCH REPORT")
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = GOLD
    run.font.name = FONT_NAME

    p = document.add_paragraph()
    run = p.add_run(company_name)
    run.bold = True
    run.font.size = Pt(34)
    run.font.color.rgb = NAVY
    run.font.name = FONT_NAME

    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    run = p.add_run("AI-Powered Market Research Analysis")
    run.italic = True
    run.font.size = Pt(13)
    run.font.color.rgb = SLATE
    run.font.name = FONT_NAME

    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    pPr = p._p.get_or_add_pPr()
    border = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), GOLD_HEX)
    border.append(bottom)
    pPr.append(border)

    for _ in range(6):
        document.add_paragraph()

    p = document.add_paragraph()
    run = p.add_run(f"Prepared: {research_date}")
    run.font.size = Pt(10)
    run.font.color.rgb = SLATE
    run.font.name = FONT_NAME

    p = document.add_paragraph()
    run = p.add_run("Classification: AI-Assisted Research, Verified Against Cited Primary Sources")
    run.font.size = Pt(10)
    run.font.color.rgb = SLATE
    run.font.name = FONT_NAME

    document.add_page_break()


# ============================================================
# 8B. EXECUTIVE BRIEF
#
# Everything here is built directly from structured_data using the same
# helpers the rest of the report uses (_pick_metric, format_metric_cell,
# defined further below) -- no separate numbers, no new narrative LLM
# call, except for the Strategic Evaluation scores, which are the one
# genuinely interpretive piece and are clearly labeled as such. Any
# subsection with no underlying data is skipped entirely.
# ============================================================

STRATEGIC_SCORE_ORDER = [
    "strategic_position",
    "growth_potential",
    "product_market_strength",
    "ability_to_disrupt",
    "market_traction",
    "financial_strength",
    "competitive_position",
]

STRATEGIC_SCORE_LABELS = {
    "strategic_position": "Strategic Position",
    "growth_potential": "Growth Potential",
    "product_market_strength": "Product/Market Fit",
    "ability_to_disrupt": "Ability to Disrupt",
    "market_traction": "Market Traction",
    "financial_strength": "Financial Strength",
    "competitive_position": "Competitive Position",
}


def _stat_cards_table(document, cards):
    """cards: list of (label, value) tuples. Renders up to 4 as a single
    row of KPI-style cards."""

    cards = cards[:4]
    if not cards:
        return

    table = document.add_table(rows=1, cols=len(cards))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for cell, (label, value) in zip(table.rows[0].cells, cards):
        set_cell_background(cell, LIGHT_HEX)
        set_cell_border_color(cell, LIGHT_BORDER_HEX)
        cell.paragraphs[0].text = ""

        label_p = cell.paragraphs[0]
        run = label_p.add_run(str(label).upper())
        run.font.size = Pt(8)
        run.font.bold = True
        run.font.color.rgb = SLATE
        run.font.name = FONT_NAME

        value_p = cell.add_paragraph()
        run = value_p.add_run(str(value))
        run.font.size = Pt(13)
        run.font.bold = True
        run.font.color.rgb = NAVY
        run.font.name = FONT_NAME

    document.add_paragraph()


def _brief_bullet(document, label, value):
    p = document.add_paragraph(style="List Bullet")
    run = p.add_run(f"{label}: ")
    run.bold = True
    run.font.size = Pt(10)
    run.font.color.rgb = NAVY
    run.font.name = FONT_NAME
    run2 = p.add_run(str(value))
    run2.font.size = Pt(10)
    run2.font.color.rgb = TEXT
    run2.font.name = FONT_NAME


def add_executive_brief(document, structured_data, strategic_scores, company_name, research_date):

    data = structured_data or {}
    strategic_scores = strategic_scores or {}

    document.add_heading("Executive Brief", level=1)

    # --- Company / Market header ---
    industry = str(data.get("industry", "")).strip()
    sub_industry = str(data.get("sub_industry", "")).strip()
    geo_list = [str(g).strip() for g in (data.get("geographic_presence") or []) if str(g).strip()]
    geo_text = ", ".join(geo_list[:5])

    if industry:
        label = f"{industry} — {sub_industry}" if sub_industry else industry
        _brief_bullet(document, "Industry", label)
    if geo_text:
        _brief_bullet(document, "Geography", geo_text)
    _brief_bullet(document, "Research Period", research_date)

    business_model = str(data.get("business_model", "")).strip()
    if business_model:
        one_liner = business_model.split(". ")[0].strip().rstrip(".") + "."
        p = document.add_paragraph()
        run = p.add_run(one_liner)
        run.italic = True
        run.font.size = Pt(10.5)
        run.font.color.rgb = SLATE
        run.font.name = FONT_NAME

    document.add_paragraph()

    financial_metrics = data.get("financial_metrics", []) or []
    market_metrics = data.get("market_metrics", []) or []
    annual_history = data.get("annual_revenue_history", []) or []

    # --- Market Momentum ---
    momentum_cards = []
    seen = set()
    for item in market_metrics:
        if not isinstance(item, dict):
            continue
        name = str(item.get("metric", "")).strip()
        if not name or name in seen:
            continue
        # Company guidance/forecast figures belong in the Financial
        # Snapshot (and the main Key Financials table), not here --
        # Market Momentum is meant for market-level indicators (size,
        # growth, CAGR, share), not the company's own forward guidance.
        if str(item.get("type", "")).lower() in ("guidance", "forecast"):
            continue
        if "guidance" in name.lower():
            continue
        cell_text = format_metric_cell(item)
        if cell_text:
            momentum_cards.append((name, cell_text))
            seen.add(name)
        if len(momentum_cards) >= 4:
            break

    if len(momentum_cards) < 4:
        growth_item = _pick_metric(financial_metrics, ["revenue growth"], [], type_filter=["actual"])
        cell_text = format_metric_cell(growth_item)
        if cell_text:
            momentum_cards.append(("Revenue Growth", cell_text))

    if momentum_cards:
        document.add_heading("Market Momentum", level=2)
        _stat_cards_table(document, momentum_cards)

    # --- Financial Snapshot ---
    fin_cards = []

    revenue_item = None
    if annual_history:
        valid = [x for x in annual_history if x.get("value") not in (None, "")]
        if valid:
            revenue_item = max(valid, key=lambda x: int(x.get("year", 0) or 0))
    if revenue_item is None:
        revenue_item = _pick_metric(financial_metrics, ["revenue", "net sales"], ["guidance", "forecast"], type_filter=["actual"])
    if revenue_item:
        fin_cards.append(("Revenue", format_metric_cell(revenue_item)))

    growth_item = _pick_metric(financial_metrics, ["revenue growth"], [], type_filter=["actual"])
    if growth_item:
        fin_cards.append(("Revenue Growth", format_metric_cell(growth_item)))

    margin_item = (
        _pick_metric(financial_metrics, ["operating margin"], [], type_filter=["actual"])
        or _pick_metric(financial_metrics, ["net margin", "net income margin"], [], type_filter=["actual"])
    )
    if margin_item:
        fin_cards.append(("Profitability", format_metric_cell(margin_item)))

    fcf_item = _pick_metric(financial_metrics, ["free cash flow"], [], type_filter=["actual"])
    if fcf_item:
        fin_cards.append(("Free Cash Flow", format_metric_cell(fcf_item)))

    if len(fin_cards) < 4:
        cash_debt_item = (
            _pick_metric(financial_metrics, ["net debt"], [], type_filter=["actual"])
            or _pick_metric(financial_metrics, ["cash and cash equivalents", "total cash"], [], type_filter=["actual"])
        )
        if cash_debt_item:
            label = "Net Debt" if "net debt" in str(cash_debt_item.get("metric", "")).lower() else "Cash"
            fin_cards.append((label, format_metric_cell(cash_debt_item)))

    if fin_cards:
        document.add_heading("Financial Snapshot", level=2)
        _stat_cards_table(document, fin_cards)

    # --- Customer & Market Snapshot ---
    customer_lines = []

    target_customers = [str(x).strip() for x in (data.get("target_customers") or []) if str(x).strip()]
    if target_customers:
        customer_lines.append(("Target Customers", ", ".join(target_customers[:5])))

    customer_segments = [str(x).strip() for x in (data.get("customer_segments") or []) if str(x).strip()]
    if customer_segments:
        customer_lines.append(("Customer Segments", ", ".join(customer_segments[:5])))

    market_size_item = next(
        (x for x in market_metrics if isinstance(x, dict) and "market size" in str(x.get("metric", "")).lower()),
        None
    )
    if market_size_item:
        customer_lines.append(("Market Size", format_metric_cell(market_size_item)))

    customer_metrics = data.get("customer_metrics") or []
    if customer_metrics:
        latest_customer = max(customer_metrics, key=lambda x: int(x.get("year", 0) or 0))
        cell_text = format_metric_cell(latest_customer)
        if cell_text:
            customer_lines.append(("Customers / Users", cell_text))

    if geo_text:
        customer_lines.append(("Geographic Exposure", geo_text))

    if customer_lines:
        document.add_heading("Customer & Market Snapshot", level=2)
        for label, value in customer_lines:
            _brief_bullet(document, label, value)

    # --- Strategic Evaluation (the one interpretive section) ---
    if strategic_scores:
        document.add_heading("Strategic Evaluation", level=2)

        note = document.add_paragraph()
        run = note.add_run("AI ANALYSIS — NOT AN EXTERNALLY VERIFIED FACT.  ")
        run.bold = True
        run.font.size = Pt(8.5)
        run.font.color.rgb = RGBColor(0xB3, 0x3A, 0x3A)
        run.font.name = FONT_NAME
        run2 = note.add_run(
            "Each score is the model's own 1-10 judgment based only on the "
            "verified data in this report, with a stated reason for each score."
        )
        run2.italic = True
        run2.font.size = Pt(8.5)
        run2.font.color.rgb = SLATE
        run2.font.name = FONT_NAME

        table = document.add_table(rows=1, cols=3)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = ["Category", "Score", "Basis"]
        widths = [Inches(1.8), Inches(0.7), Inches(3.8)]

        for cell, label, width in zip(table.rows[0].cells, headers, widths):
            cell.text = label
            cell.width = width
            set_cell_background(cell, NAVY_HEX)
            set_cell_border_color(cell, LIGHT_BORDER_HEX)
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.bold = True
                    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                    run.font.size = Pt(9.5)
                    run.font.name = FONT_NAME

        row_index = 0
        for category in STRATEGIC_SCORE_ORDER:
            entry = strategic_scores.get(category)
            if not entry:
                continue
            row = table.add_row()
            cells = row.cells
            fill = LIGHT_HEX if row_index % 2 == 0 else WHITE_HEX
            row_index += 1

            cells[0].text = STRATEGIC_SCORE_LABELS.get(category, category)
            cells[1].text = f"{entry['score']}/10"
            cells[2].text = entry["justification"]

            for cell, width in zip(cells, widths):
                cell.width = width
                set_cell_background(cell, fill)
                set_cell_border_color(cell, LIGHT_BORDER_HEX)
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.font.size = Pt(9)
                        run.font.name = FONT_NAME
                        run.font.color.rgb = TEXT

        document.add_paragraph()

    # --- Key Value Proposition ---
    advantages = [str(a).strip().rstrip(".") for a in (data.get("competitive_advantages") or []) if str(a).strip()]
    if advantages:
        document.add_heading("Key Value Proposition", level=2)
        p = document.add_paragraph()
        text = f"{company_name} differentiates through " + "; ".join(advantages[:4]) + "."
        run = p.add_run(text)
        run.font.size = Pt(10.5)
        run.font.color.rgb = TEXT
        run.font.name = FONT_NAME

    # --- Responsible AI & Risk ---
    ai_strategy = str(data.get("ai_strategy", "")).strip()
    risks = [str(r).strip() for r in (data.get("risks") or []) if str(r).strip()]
    if ai_strategy or risks:
        document.add_heading("Responsible AI & Risk Considerations", level=2)
        if ai_strategy:
            p = document.add_paragraph()
            run = p.add_run(ai_strategy)
            run.font.size = Pt(10.5)
            run.font.color.rgb = TEXT
            run.font.name = FONT_NAME
        for r in risks[:4]:
            p = document.add_paragraph(style="List Bullet")
            add_inline_runs(p, r)

    # --- Revenue Model ---
    revenue_model = str(data.get("revenue_model", "")).strip()
    if revenue_model:
        document.add_heading("Revenue Model", level=2)
        p = document.add_paragraph()
        run = p.add_run(revenue_model)
        run.font.size = Pt(10.5)
        run.font.color.rgb = TEXT
        run.font.name = FONT_NAME

    document.add_page_break()


# ============================================================
# 9. INFOGRAPHIC (unchanged mechanism — see infographic.py for the
#    keyword-matching fix that stops it showing "Not available" for
#    data that is actually present)
# ============================================================

def add_infographic(document, infographic_path):

    if not infographic_path:
        return
    if not os.path.exists(infographic_path):
        return

    heading = document.add_heading("Company Snapshot", level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.LEFT

    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    run.add_picture(infographic_path, width=Inches(6.7))

    document.add_page_break()


# ============================================================
# 10. CHART INSERTION
# ============================================================

def add_chart(document, chart_path, caption_text=None):

    if not chart_path:
        return
    if not os.path.exists(chart_path):
        return

    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    run.add_picture(chart_path, width=Inches(6.3))

    if caption_text:
        cap = document.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cap.add_run(caption_text)
        run.italic = True
        run.font.size = Pt(8.5)
        run.font.color.rgb = SLATE
        run.font.name = FONT_NAME

    document.add_paragraph()


def chart_caption(chart_key):
    labels = {
        "revenue_five_year": "Multi-year revenue trend, verified annual filings.",
        "revenue_outlook": "Latest actual revenue vs. company guidance.",
        "quarterly_revenue": "Recent quarterly revenue.",
        "margin_trend": "Multi-year margin trend, verified annual filings.",
        "fcf_trend": "Multi-year free cash flow trend, verified annual filings.",
        "employee_metric": "Verified workforce figures.",
        "segment_revenue": "Revenue by business segment, most recent common period.",
        "segment_growth": "Year-over-year segment revenue growth.",
        "geographic_revenue": "Revenue by geography, most recent common period.",
        "customer_metric": "Verified customer / user figures.",
        "market_size": "Verified market size figures.",
        "market_composition": "Market share by competitor, verified sources.",
        "market_share_trend": "Market share over time.",
        "competitor_comparison": "Verified competitor comparison.",
        "company_timeline": "Verified company timeline.",
    }
    return labels.get(chart_key, "")


def flush_section_charts(document, section_norm, charts, used_keys):
    """Adds every chart mapped to this section that has not already been
    inserted, in a stable order. Never invents a chart: a section with
    no populated keys in `charts` simply gets nothing appended."""

    if not section_norm or not charts:
        return

    for key, mapped_section in CHART_SECTION_MAP.items():
        if mapped_section != section_norm:
            continue
        if key in used_keys:
            continue
        path = charts.get(key)
        if not path:
            continue
        add_chart(document, path, chart_caption(key))
        used_keys.add(key)


# ============================================================
# 11. KEY FINANCIALS TABLE
# ============================================================

VERIFICATION_RANK = {"VERIFIED": 2, "PARTIALLY VERIFIED": 1, "DERIVED": 0}

FINANCIAL_ROW_DEFS = [
    ("Revenue", ["revenue", "net sales"], ["guidance", "forecast"]),
    ("Latest Quarterly Revenue", ["revenue", "net sales"], ["guidance", "forecast"]),
    ("Revenue Growth (YoY)", ["revenue growth"], []),
    ("Gross Profit", ["gross profit"], []),
    ("Gross Margin", ["gross margin"], []),
    ("Operating Income", ["operating income"], []),
    ("Operating Margin", ["operating margin"], []),
    ("Net Income", ["net income"], []),
    ("Net Margin", ["net margin", "net income margin"], []),
    ("EBITDA", ["ebitda"], []),
    ("EPS", ["eps", "earnings per share"], []),
    ("Free Cash Flow", ["free cash flow"], []),
    ("Operating Cash Flow", ["operating cash flow", "cash from operations", "operating activities"], []),
    ("Capital Expenditure", ["capital expenditure", "capex", "purchases of property"], []),
    ("Cash and Equivalents", ["cash and cash equivalents", "total cash"], []),
    ("Total Debt", ["total debt", "long-term debt"], ["net debt"]),
    ("Net Debt", ["net debt"], []),
    ("Revenue Guidance", ["revenue"], []),
]


def period_sort_key(item):
    """Sort key that prefers later fiscal periods within the same year --
    e.g. Q2 2026 over Q1 2026 -- rather than relying on year alone, which
    ties when multiple quarters of the same year are both candidates."""
    try:
        year = int(item.get("year", 0) or 0)
    except (TypeError, ValueError):
        year = 0
    period = str(item.get("period", "")).lower()
    quarter_match = re.search(r"q([1-4])", period)
    # Annual/full-year periods have no quarter marker -- treat them as the
    # latest slice of their year so a full FY figure outranks a same-year
    # quarter when both are otherwise equally valid candidates.
    quarter = int(quarter_match.group(1)) if quarter_match else 4
    return (year, quarter)


def _pick_metric(items, include_any, exclude_any, type_filter=None):

    candidates = []

    for x in items:
        if not isinstance(x, dict):
            continue
        name = str(x.get("metric", "")).lower()
        if not any(p in name for p in include_any):
            continue
        if any(p in name for p in exclude_any):
            continue
        if type_filter is not None:
            if str(x.get("type", "")).lower() not in type_filter:
                continue
        candidates.append(x)

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda item: (VERIFICATION_RANK.get(item.get("verification"), 0), period_sort_key(item))
    )


def format_metric_cell(item):

    if not item:
        return None

    raw_value = item.get("value")
    unit = str(item.get("unit", "")).strip()
    period = str(item.get("period", "")).strip()
    unit_lower = unit.lower()

    try:
        num = float(str(raw_value).replace(",", ""))
    except (TypeError, ValueError):
        num = None

    # Handle a negative sign separately so it comes before the $ sign
    # ("-$1,200.0M" not "$-1,200.0M") -- net debt is commonly negative
    # when a company holds more cash than debt.
    sign = "-" if num is not None and num < 0 else ""
    abs_num = abs(num) if num is not None else None

    if abs_num is not None and "usd" in unit_lower and "billion" in unit_lower:
        text = f"{sign}${abs_num:,.2f}B"
    elif abs_num is not None and "usd" in unit_lower and "million" in unit_lower:
        text = f"{sign}${abs_num:,.1f}M"
    elif abs_num is not None and "%" in unit:
        text = f"{sign}{abs_num:.1f}%"
    elif abs_num is not None and unit_lower in ("usd", "usd per share", "$"):
        text = f"{sign}${abs_num:,.2f}"
    elif abs_num is not None and unit:
        text = f"{sign}{abs_num:,.1f} {unit}"
    elif abs_num is not None:
        text = f"{sign}{abs_num:,.1f}"
    else:
        text = f"{raw_value} {unit}".strip()

    if period:
        text += f"  ({period})"

    return text


def add_key_financials_table(document, structured_data):

    financial_metrics = structured_data.get("financial_metrics", []) or []
    annual_history = structured_data.get("annual_revenue_history", []) or []

    rows_to_render = []

    for label, include_any, exclude_any in FINANCIAL_ROW_DEFS:

        if label == "Revenue":
            item = None
            is_annual = False
            if annual_history:
                valid = [x for x in annual_history if x.get("value") not in (None, "")]
                if valid:
                    item = max(valid, key=lambda x: int(x.get("year", 0) or 0))
                    is_annual = True
            if item is None:
                item = _pick_metric(financial_metrics, include_any, exclude_any, type_filter=["actual"])
            row_label = label
            if item is not None and not is_annual:
                # No verified annual figure survived -- falling back to a
                # quarterly actual is still useful, but it must not be
                # presented under the same "Revenue" label an annual
                # figure would use, or a reader has no way to tell a
                # single quarter apart from a full fiscal year.
                period_text = str(item.get("period", "")).lower()
                if re.search(r"\bq[1-4]\b|quarter", period_text):
                    row_label = "Revenue (Latest Quarter)"

        elif label == "Latest Quarterly Revenue":
            # A genuinely supplementary row, not a fallback substitute --
            # only shown when annual revenue is ALSO present above, so
            # the table can show both the full-year figure and the most
            # recent quarter side by side. When no annual figure exists,
            # the "Revenue" row above already surfaces the latest quarter
            # itself (relabeled), so repeating it here would be redundant.
            item = None
            if annual_history:
                quarterly_candidates = [
                    x for x in financial_metrics
                    if any(p in str(x.get("metric", "")).lower() for p in include_any)
                    and str(x.get("type", "")).lower() == "actual"
                    and re.search(
                        r"\bq[1-4]\b|quarter",
                        f"{x.get('metric', '')} {x.get('period', '')}".lower()
                    )
                ]
                if quarterly_candidates:
                    item = max(quarterly_candidates, key=period_sort_key)
            row_label = label

        elif label == "Revenue Guidance":
            item = _pick_metric(financial_metrics, include_any, [], type_filter=["guidance", "forecast"])
            row_label = label

        else:
            item = _pick_metric(financial_metrics, include_any, exclude_any, type_filter=["actual"])
            row_label = label

        cell_text = format_metric_cell(item)
        if cell_text:
            rows_to_render.append((row_label, cell_text))

    if not rows_to_render:
        return

    table = document.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    header_cells = table.rows[0].cells
    header_cells[0].text = "Metric"
    header_cells[1].text = "Verified Value"

    for cell in header_cells:
        set_cell_background(cell, NAVY_HEX)
        set_cell_border_color(cell, LIGHT_BORDER_HEX)
        for p in cell.paragraphs:
            for run in p.runs:
                run.font.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                run.font.size = Pt(10)
                run.font.name = FONT_NAME

    for index, (label, value) in enumerate(rows_to_render):
        row = table.add_row()
        cells = row.cells
        cells[0].text = label
        cells[1].text = value

        fill = LIGHT_HEX if index % 2 == 0 else WHITE_HEX
        for cell in cells:
            set_cell_background(cell, fill)
            set_cell_border_color(cell, LIGHT_BORDER_HEX)
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(10)
                    run.font.name = FONT_NAME
                    run.font.color.rgb = TEXT

    document.add_paragraph()


# ============================================================
# 11A. INDUSTRY-SPECIFIC KPI TABLE
#
# Unlike the Key Financials table above, this doesn't have a fixed set
# of rows to look for -- which metrics are even relevant depends on the
# kind of business (ARR for a SaaS company, production capacity for a
# manufacturer, etc.). So this just renders whatever verified
# industry_kpis items actually came back, one row per metric, rather
# than checking a hard-coded list the way FINANCIAL_ROW_DEFS does.
# ============================================================

def add_industry_kpis_table(document, structured_data):

    items = [
        x for x in (structured_data.get("industry_kpis", []) or [])
        if isinstance(x, dict) and x.get("value") not in (None, "")
    ]

    if not items:
        return

    # If the same metric shows up more than once (e.g. two different
    # periods), keep only the most recent for a clean one-row-per-metric
    # table.
    by_metric = {}
    for item in items:
        name = str(item.get("metric", "")).strip()
        if not name:
            continue
        if name not in by_metric or period_sort_key(item) > period_sort_key(by_metric[name]):
            by_metric[name] = item

    rows_to_render = []
    for name, item in by_metric.items():
        cell_text = format_metric_cell(item)
        if cell_text:
            rows_to_render.append((name, cell_text))

    if not rows_to_render:
        return

    document.add_heading("Industry-Specific Metrics", level=2)

    table = document.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    header_cells = table.rows[0].cells
    header_cells[0].text = "Metric"
    header_cells[1].text = "Verified Value"

    for cell in header_cells:
        set_cell_background(cell, NAVY_HEX)
        set_cell_border_color(cell, LIGHT_BORDER_HEX)
        for p in cell.paragraphs:
            for run in p.runs:
                run.font.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                run.font.size = Pt(10)
                run.font.name = FONT_NAME

    for index, (label, value) in enumerate(rows_to_render):
        row = table.add_row()
        cells = row.cells
        cells[0].text = label
        cells[1].text = value

        fill = LIGHT_HEX if index % 2 == 0 else WHITE_HEX
        for cell in cells:
            set_cell_background(cell, fill)
            set_cell_border_color(cell, LIGHT_BORDER_HEX)
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(10)
                    run.font.name = FONT_NAME
                    run.font.color.rgb = TEXT

    document.add_paragraph()


# ============================================================
# 11B. COMPETITOR COMPARISON TABLE
#
# Unlike every other table in this report, these rows are qualitative
# (strengths, weaknesses, positioning) rather than numbers -- there is
# no tolerance-matching that can verify "Apple's weakness is X." The
# guardrails live in research_agent.py's extraction step (every row
# must cite a real accepted source and name a competitor already
# identified elsewhere in the research); this function just renders
# whatever survived that check.
# ============================================================

def add_competitor_comparison_table(document, structured_data):

    comparison = [
        c for c in (structured_data.get("competitive_comparison", []) or [])
        if isinstance(c, dict) and c.get("competitor")
    ]

    if not comparison:
        return

    table = document.add_table(rows=1, cols=5)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    headers = ["Competitor", "Products / Services", "Strengths & Advantage", "Weaknesses", "Positioning & Relevance"]
    widths = [Inches(1.1), Inches(1.3), Inches(1.6), Inches(1.1), Inches(1.6)]

    for cell, label, width in zip(table.rows[0].cells, headers, widths):
        cell.text = label
        cell.width = width
        set_cell_background(cell, NAVY_HEX)
        set_cell_border_color(cell, LIGHT_BORDER_HEX)
        for p in cell.paragraphs:
            for run in p.runs:
                run.font.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                run.font.size = Pt(9)
                run.font.name = FONT_NAME

    for index, entry in enumerate(comparison):
        row = table.add_row()
        cells = row.cells
        fill = LIGHT_HEX if index % 2 == 0 else WHITE_HEX

        competitor_text = str(entry.get("competitor", ""))
        if entry.get("main_segment"):
            competitor_text += f"\n({entry['main_segment']})"
        cells[0].text = competitor_text

        cells[1].text = "; ".join(entry.get("products_services", []) or []) or "—"

        strengths_adv = list(entry.get("strengths", []) or [])
        if entry.get("competitive_advantage"):
            strengths_adv.append(entry["competitive_advantage"])
        cells[2].text = "; ".join(strengths_adv) or "—"

        cells[3].text = "; ".join(entry.get("weaknesses", []) or []) or "—"

        pos_rel = []
        if entry.get("market_positioning"):
            pos_rel.append(entry["market_positioning"])
        if entry.get("relevance"):
            pos_rel.append(entry["relevance"])
        cells[4].text = " — ".join(pos_rel) or "—"

        for cell, width in zip(cells, widths):
            cell.width = width
            set_cell_background(cell, fill)
            set_cell_border_color(cell, LIGHT_BORDER_HEX)
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(8.5)
                    run.font.name = FONT_NAME
                    run.font.color.rgb = TEXT

    caption = document.add_paragraph()
    run = caption.add_run(
        "Built only from sources cited for each competitor; only "
        "competitors independently identified elsewhere in this "
        "research are included."
    )
    run.italic = True
    run.font.size = Pt(8)
    run.font.color.rgb = SLATE
    run.font.name = FONT_NAME

    document.add_paragraph()


# ============================================================
# 12. SWOT TABLE
# ============================================================

def add_swot_table(document, swot_buffers):

    strengths = swot_buffers.get("strengths", [])
    risks = swot_buffers.get("risks", [])
    opportunities = swot_buffers.get("opportunities", [])

    if not any([strengths, risks, opportunities]):
        return

    document.add_heading("SWOT Analysis", level=1)

    table = document.add_table(rows=1, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    header_cells = table.rows[0].cells
    headers = ["Strengths", "Risks", "Opportunities"]
    accents = [GOLD_HEX, "B33A3A", "2E7D5B"]

    for cell, label in zip(header_cells, headers):
        cell.text = label
        set_cell_background(cell, NAVY_HEX)
        set_cell_border_color(cell, LIGHT_BORDER_HEX)
        for p in cell.paragraphs:
            for run in p.runs:
                run.font.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                run.font.size = Pt(10)
                run.font.name = FONT_NAME

    body_row = table.add_row()
    columns = [strengths, risks, opportunities]

    for cell, items in zip(body_row.cells, columns):
        set_cell_background(cell, LIGHT_HEX)
        set_cell_border_color(cell, LIGHT_BORDER_HEX)

        cell.paragraphs[0].text = ""

        if not items:
            run = cell.paragraphs[0].add_run("Not available from the accepted sources.")
            run.italic = True
            run.font.size = Pt(9.5)
            run.font.color.rgb = SLATE
            run.font.name = FONT_NAME
            continue

        for index, item in enumerate(items):
            p = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
            run = p.add_run("— ")
            run.bold = True
            run.font.color.rgb = NAVY
            run.font.size = Pt(9.5)
            run.font.name = FONT_NAME
            add_inline_runs(p, item, base_size=9.5)

    document.add_paragraph()


# ============================================================
# 13. RESEARCH SOURCES TABLE (accepted_sources is authoritative)
# ============================================================

def source_relevance_label(source):

    score = source.get("score", 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0

    if score >= 90:
        return "Primary / High Relevance"
    if score >= 75:
        return "High Relevance"
    if score >= 60:
        return "Moderate Relevance"
    return "Supporting"


def add_source_table(document, accepted_sources):

    if not accepted_sources:
        return

    document.add_page_break()
    document.add_heading("Research Sources", level=1)

    intro = document.add_paragraph()
    run = intro.add_run(
        "The following sources were evaluated, filtered and ranked by the research "
        "pipeline and used to support the verified claims in this report."
    )
    run.italic = True
    run.font.size = Pt(9)
    run.font.color.rgb = SLATE
    run.font.name = FONT_NAME

    table = document.add_table(rows=1, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    widths = [Inches(3.4), Inches(1.6), Inches(2.0)]
    header_cells = table.rows[0].cells
    headers = ["Source", "Type / Relevance", "URL"]

    for cell, label, width in zip(header_cells, headers, widths):
        cell.text = label
        cell.width = width
        set_cell_background(cell, NAVY_HEX)
        set_cell_border_color(cell, LIGHT_BORDER_HEX)
        for p in cell.paragraphs:
            for run in p.runs:
                run.font.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                run.font.size = Pt(9.5)
                run.font.name = FONT_NAME

    ordered_sources = sorted(
        accepted_sources,
        key=lambda s: s.get("score", 0),
        reverse=True
    )

    for index, source in enumerate(ordered_sources):

        row = table.add_row()
        cells = row.cells
        fill = LIGHT_HEX if index % 2 == 0 else WHITE_HEX

        title = source.get("title", "Unknown source")
        url = source.get("url", "")
        relevance = f"{source_relevance_label(source)} ({source.get('score', 'n/a')}/100)"

        cells[0].text = str(title)
        cells[1].text = relevance

        cells[2].paragraphs[0].text = ""
        if url:
            add_hyperlink(cells[2].paragraphs[0], url, url)
        else:
            run = cells[2].paragraphs[0].add_run("URL not available")
            run.italic = True

        for cell, width in zip(cells, widths):
            cell.width = width
            set_cell_background(cell, fill)
            set_cell_border_color(cell, LIGHT_BORDER_HEX)
            for p in cell.paragraphs:
                for run in p.runs:
                    if not run.font.size:
                        run.font.size = Pt(9)
                    run.font.name = FONT_NAME
                    if not run.font.color or run.font.color.type is None:
                        run.font.color.rgb = TEXT


# ============================================================
# 14. HEADING NORMALIZATION
# ============================================================

def normalize_heading(text):
    stripped = re.sub(r"^\d+\.\s*", "", text.strip())
    return stripped.strip().lower()


def heading_level(line):
    match = re.match(r"^(#{1,3})\s+(.*)", line)
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


SWOT_HEADINGS = {"strengths", "risks", "opportunities"}

# The canonical set of top-level section names, exactly as specified in
# generate_final_report's REPORT STRUCTURE prompt (after normalize_heading
# strips any leading "N. " numbering). Detection is keyed off this text
# match rather than raw heading depth ("#" count), because the model does
# not reliably nest headings at a consistent depth -- sometimes the whole
# document shifts down a level uniformly, and sometimes a single section
# (observed: "Sources") gets nested one level deeper than its siblings
# while everything else stays put. A positional/depth-based offset can
# only ever handle the first case; text matching handles both, since it
# doesn't care what depth a heading was written at.
TOP_LEVEL_SECTION_NAMES = {
    "executive summary",
    "company overview",
    "financial performance",
    "products and services",
    "target customers",
    "business model",
    "competitive landscape",
    "ai strategy",
    "recent developments",
    "strengths",
    "risks",
    "opportunities",
    "conclusion",
    "sources",
}


# ============================================================
# 15. MAIN REPORT-CONTENT WALKER
# ============================================================

def add_report_content(document, final_report, structured_data, charts):

    charts = charts or {}
    used_chart_keys = set()

    lines = final_report.splitlines()

    current_section = None
    skip_body = False
    swot_mode = None
    swot_buffers = {"strengths": [], "risks": [], "opportunities": []}
    # The report-writing LLM sometimes prepends its own document title
    # line (e.g. "## Garmin Ltd. Comprehensive Market Research Report")
    # before "# Executive Summary" even though the prompt's REPORT
    # STRUCTURE starts directly with Executive Summary. That line matches
    # no recognized section name, so without this guard it would render
    # as an orphan heading with no body. Anything before the first
    # recognized top-level section is treated as noise and dropped.
    seen_first_section = False

    def close_section(section_norm):
        if section_norm and section_norm != "sources":
            flush_section_charts(document, section_norm, charts, used_chart_keys)

    for raw_line in lines:

        line = raw_line.strip()

        if not line:
            continue

        # A leaked markdown table (the report-writing LLM occasionally
        # builds its own despite being told not to, e.g. under Financial
        # Performance) has no business appearing as literal pipe-text in
        # the document -- the real data already gets its own properly
        # formatted table. Recognize and silently drop table syntax
        # rather than let it render as "| Metric | Value |" text.
        if re.match(r"^\|.*\|$", line) or re.match(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$", line):
            continue

        heading = heading_level(line)

        if heading:
            _raw_level, text = heading
            norm = normalize_heading(text)
            is_top_level = norm in TOP_LEVEL_SECTION_NAMES

            if not seen_first_section and not is_top_level:
                # Stray pre-report-structure heading (e.g. a self-written
                # title) -- drop it and keep waiting for a real section.
                continue

            if is_top_level:
                seen_first_section = True

                close_section(current_section)

                if norm in SWOT_HEADINGS:
                    swot_mode = norm
                    current_section = norm
                    continue

                if swot_mode is not None:
                    add_swot_table(document, swot_buffers)
                    swot_mode = None

                current_section = norm

                if norm == "sources":
                    skip_body = True
                    continue

                skip_body = False
                document.add_heading(text, level=1)

                if norm == "financial performance":
                    add_key_financials_table(document, structured_data)
                    add_industry_kpis_table(document, structured_data)

                if norm == "competitive landscape":
                    add_competitor_comparison_table(document, structured_data)

                continue

            else:
                if swot_mode is not None or skip_body:
                    continue
                document.add_heading(text, level=2)
                continue

        # Non-heading content lines.

        if not seen_first_section:
            # Stray pre-report-structure prose (e.g. a title-adjacent
            # intro line) -- same treatment as a stray heading above.
            continue

        if skip_body:
            continue

        if swot_mode is not None:
            # Only capture genuine bulleted lines. The report-writing LLM
            # often prefixes the list with a plain lead-in sentence (e.g.
            # "Garmin's strengths include:") before its actual bullets --
            # without this check, that sentence itself became a bogus
            # first "bullet" in the SWOT table.
            if line.startswith("- "):
                swot_buffers[swot_mode].append(line[2:].strip())
            continue

        if line.startswith("- "):
            paragraph = document.add_paragraph(style="List Bullet")
            add_inline_runs(paragraph, line[2:].strip())
            continue

        numbered_match = re.match(r"^\d+\.\s+(.*)", line)
        if numbered_match:
            paragraph = document.add_paragraph(style="List Number")
            add_inline_runs(paragraph, numbered_match.group(1))
            continue

        paragraph = document.add_paragraph()
        add_inline_runs(paragraph, line)

    # Flush whatever section was open when the content ended.
    if swot_mode is not None:
        add_swot_table(document, swot_buffers)
        swot_mode = None
    close_section(current_section)


# ============================================================
# 16. MAIN DOCX GENERATOR
# ============================================================

def generate_docx_report(
    company_name,
    final_report,
    structured_data=None,
    infographic_path=None,
    charts=None,
    accepted_sources=None,
    research_date=None,
    include_sources=True,
    strategic_scores=None
):

    structured_data = structured_data or {}
    charts = charts or {}
    accepted_sources = accepted_sources or []
    strategic_scores = strategic_scores or {}

    if not research_date:
        from datetime import date
        research_date = date.today().strftime("%B %Y")

    document = Document()

    set_document_margins(document)
    set_default_font(document)
    add_header_footer(document, company_name, research_date)

    add_title_page(document, company_name, research_date)

    add_infographic(document, infographic_path)

    add_executive_brief(document, structured_data, strategic_scores, company_name, research_date)

    add_report_content(document, final_report, structured_data, charts)

    if include_sources:
        add_source_table(document, accepted_sources)

    filename = (
        f"{safe_filename(company_name)}"
        "_market_research_report.docx"
    )

    output_path = os.path.join(
        OUTPUT_DIR,
        filename
    )

    document.save(
        output_path
    )

    return output_path