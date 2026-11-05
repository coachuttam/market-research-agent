import os
import re
import textwrap
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

W, H = 1800, 1200
MARGIN = 55
BLACK = (25, 25, 25)
DARK = (55, 55, 55)
MID = (110, 110, 110)
LIGHT = (220, 220, 220)
WHITE = (255, 255, 255)


def safe_filename(name):
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", str(name)).strip("_").lower()


def font(size, bold=False):
    paths = [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


F_TITLE = font(40, True)
F_SUB = font(19)
F_SECTION = font(18, True)
F_LABEL = font(15, True)
F_BODY = font(15)
F_SMALL = font(12)
F_KPI = font(28, True)
F_KPI_SMALL = font(22, True)


def clean(v, fallback="Not available"):
    if v is None:
        return fallback
    s = str(v).strip()
    return s if s else fallback


def verified_metrics(data, field):
    rows = data.get(field, [])
    if not isinstance(rows, list):
        return []
    return [
        x for x in rows
        if isinstance(x, dict)
        and x.get("verification") == "VERIFIED"
        and x.get("value") not in (None, "")
    ]


def metric_number(metric):
    if not metric:
        return None
    v = metric.get("value")
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).lower().replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    n = float(m.group())
    if "billion" in s:
        n *= 1000
    elif "thousand" in s:
        n /= 1000
    return n


def metric_year(metric):
    try:
        return int(metric.get("year"))
    except Exception:
        return 0


# ------------------------------------------------------------
# Keyword lists used to recognize employee and customer metrics.
#
# NOTE: kept in sync by hand with the equivalent lists in
# research_agent.py's employee/customer contamination filters. The
# original, narrower lists here (just "employee"/"workforce"/
# "headcount" and "customer"/"users") were the direct cause of the
# Company Snapshot showing "Not available" for companies that use
# different terminology -- Garmin's own materials call its people
# "associates", which matched nothing.
# ------------------------------------------------------------

EMPLOYEE_KEYWORDS = [
    "employee", "workforce", "headcount", "staff", "personnel",
    "associate", "people",
]

CUSTOMER_KEYWORDS = [
    "customer", "user", "subscriber", "client", "member",
    "installed base",
]


def find_metric(data, fields, patterns, annual_only=False, exclude_types=None):
    rows = []
    for field in fields:
        rows += verified_metrics(data, field)

    exclude_types = exclude_types or []

    matches = []
    for x in rows:
        name = str(x.get("metric", "")).lower()
        unit = str(x.get("unit", "")).lower()
        period = str(x.get("period", "")).lower()
        item_type = str(x.get("type", "")).lower()

        if annual_only:
            # Check name, unit AND period -- a quarterly figure is often
            # labelled "Quarterly Revenue" (the word "quarter" appears as
            # "quarterly", which \bquarter\b does NOT match due to the
            # word-boundary after "r") with the actual "Q2 2026" marker
            # sitting in the period field instead of the metric name.
            haystack = f"{name} {unit} {period}"
            if re.search(r"\bq[1-4]\b|quarter", haystack):
                continue

        if item_type in exclude_types:
            continue
        if any(p in name for p in patterns) or any(p in unit for p in patterns):
            matches.append(x)

    if not matches:
        return None
    return max(matches, key=metric_year)


def display_metric(metric):
    if not metric:
        return "Not available"
    value = clean(metric.get("value"))
    unit = clean(metric.get("unit"), "")
    year = metric.get("year")
    text = value
    if unit and unit.lower() not in value.lower():
        text += f" {unit}"
    if year:
        text += f"  •  {year}"
    return text


def wrap(text, width):
    return textwrap.wrap(
        clean(text),
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )


def items(value, limit):
    if not isinstance(value, list):
        return []
    result = []
    for x in value:
        if isinstance(x, dict):
            x = x.get("name") or x.get("title") or x.get("description") or x.get("event")
        if x:
            result.append(str(x).strip())
    return result[:limit]


def draw_card(draw, box):
    draw.rounded_rectangle(box, radius=14, outline=LIGHT, width=2, fill=WHITE)


def draw_section(draw, box, title):
    x1, y1, x2, y2 = box
    draw_card(draw, box)
    draw.text((x1 + 24, y1 + 20), title.upper(), font=F_SECTION, fill=BLACK)
    draw.line((x1 + 24, y1 + 50, x1 + 165, y1 + 50), fill=BLACK, width=2)


def draw_wrapped(draw, text, x, y, width, max_lines=4, f=F_BODY, gap=7, max_y=None):
    lines = wrap(text, width)
    lines = lines[:max_lines]
    for line in lines:
        # A fixed-height box layout must never let text run past the
        # next labeled sub-section drawn below it -- AI-generated
        # strategy/summary text varies a lot in length, and without this
        # clamp a long paragraph silently bleeds into (and garbles) the
        # heading that follows it at a fixed y-offset.
        if max_y is not None and y + f.size > max_y:
            break
        draw.text((x, y), line, font=f, fill=DARK)
        y += f.size + gap
    return y


def draw_bullets(draw, values, x, y, width, max_items=4, max_y=None):
    values = values[:max_items]
    if not values:
        draw.text((x, y), "No verified information available.", font=F_BODY, fill=MID)
        return y + 25

    for value in values:
        lines = wrap(value, width)
        lines = lines[:3]
        if not lines:
            continue
        # Same overflow guard as draw_wrapped: stop before drawing
        # anything that would run past this section's allotted space,
        # rather than letting a long bullet (e.g. "Diverse product
        # portfolio across multiple segments") bleed into and garble
        # whatever fixed-position heading sits below this block.
        if max_y is not None and y + 18 > max_y:
            break
        draw.text((x, y), "• " + lines[0], font=F_BODY, fill=DARK)
        y += 24
        overflowed = False
        for line in lines[1:]:
            if max_y is not None and y + 18 > max_y:
                overflowed = True
                break
            draw.text((x + 17, y), line, font=F_BODY, fill=DARK)
            y += 22
        if overflowed:
            break
        y += 7
    return y


def draw_kpi(draw, box, label, value):
    draw_card(draw, box)
    x1, y1, x2, y2 = box
    draw.text((x1 + 24, y1 + 18), label.upper(), font=F_LABEL, fill=DARK)

    value_lines = wrap(value, 21)[:2]
    f = F_KPI if max([len(x) for x in value_lines] or [0]) <= 16 else F_KPI_SMALL

    yy = y1 + 55
    for line in value_lines:
        draw.text((x1 + 24, yy), line, font=f, fill=BLACK)
        yy += f.size + 3

    draw.text((x1 + 24, y2 - 28), "Latest verified figure", font=F_SMALL, fill=MID)


def generate_company_snapshot(structured_data):
    data = structured_data if isinstance(structured_data, dict) else {}
    company = clean(data.get("company_name"), "Market Research")
    industry = clean(data.get("industry"), "Technology")

    revenue = find_metric(
        data, ["financial_metrics"],
        ["revenue", "net sales"],
        annual_only=True,
        exclude_types=["guidance", "forecast"],
    )
    customers = find_metric(
        data, ["customer_metrics"],
        CUSTOMER_KEYWORDS,
    )
    employees = find_metric(
        data, ["employee_metrics"],
        EMPLOYEE_KEYWORDS,
    )
    market_share = find_metric(
        data, ["market_metrics"],
        ["market share"],
    )

    # If customer/employee metrics were stored outside the dedicated fields,
    # recover them without mixing unrelated numbers.
    if not customers:
        customers = find_metric(data, ["operational_metrics"], CUSTOMER_KEYWORDS)
    if not employees:
        employees = find_metric(data, ["operational_metrics"], EMPLOYEE_KEYWORDS)

    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)

    # Header
    draw.text((MARGIN, 42), company, font=F_TITLE, fill=BLACK)
    draw.text(
        (MARGIN, 91),
        f"{industry}  |  Executive Market Research Dashboard",
        font=F_SUB,
        fill=DARK,
    )
    draw.text(
        (W - MARGIN, 48),
        "VERIFIED RESEARCH",
        font=F_LABEL,
        fill=DARK,
        anchor="ra",
    )
    draw.line((MARGIN, 130, W - MARGIN, 130), fill=LIGHT, width=2)

    # KPI row
    gap = 16
    card_w = (W - 2*MARGIN - 3*gap) // 4
    y1, y2 = 155, 285

    kpis = [
        ("Revenue", display_metric(revenue)),
        ("Customers", display_metric(customers)),
        ("Employees", display_metric(employees)),
        ("Market Share", display_metric(market_share)),
    ]

    for i, (label, value) in enumerate(kpis):
        x1 = MARGIN + i * (card_w + gap)
        draw_kpi(draw, (x1, y1, x1 + card_w, y2), label, value)

    # Main content
    gap = 18
    col_w = (W - 2*MARGIN - gap) // 2
    left = MARGIN
    right = MARGIN + col_w + gap

    # Products & Market and AI & Technology each stack a second labeled
    # sub-row (Target customers / AI products+Capabilities) beneath their
    # first row of bullets, inside one fixed-height box -- the original
    # 210px box height only budgeted enough room for the first sub-row,
    # so the second one had nowhere to go. There was ~125px of unused
    # space below the footer text at the bottom of the canvas; borrowing
    # 40px each for rows 1 and 2 here (and shifting row 3 and the footer
    # down to match) gives both two-sub-row boxes enough real room.
    top1, bottom1 = 315, 565
    top2, bottom2 = 585, 835
    top3, bottom3 = 855, 1095

    # Company profile
    draw_section(draw, (left, top1, left + col_w, bottom1), "Company Profile")
    profile = [
        ("Legal entity", clean(data.get("legal_name"), company)),
        ("Founded", clean(data.get("founded"))),
        ("Headquarters", clean(data.get("headquarters"))),
        ("Business model", clean(data.get("business_model"))),
        ("Revenue model", clean(data.get("revenue_model"))),
    ]
    yy = top1 + 72
    for label, value in profile:
        # Same fixed-box overflow guard as the bullet/wrapped-text
        # helpers below -- stop before running past this box's own
        # bottom edge rather than spilling text under the card border.
        if yy > bottom1 - 20:
            break
        draw.text((left + 24, yy), label + ":", font=F_LABEL, fill=BLACK)
        value_lines = wrap(value, 44)[:2]
        draw.text((left + 185, yy), value_lines[0], font=F_BODY, fill=DARK)
        yy += 31
        for extra in value_lines[1:]:
            if yy > bottom1 - 20:
                break
            draw.text((left + 185, yy), extra, font=F_BODY, fill=DARK)
            yy += 24
        yy += 4

    # Products & market
    draw_section(draw, (right, top1, right + col_w, bottom1), "Products & Market")
    products = items(data.get("products_services"), 3)
    industries = items(data.get("industries_served"), 3)
    targets = items(data.get("target_customers"), 3)

    # "Target customers" is a second sub-row beneath Products/Industries
    # inside the same fixed-height box, so its own bullets are clamped
    # to this box's bottom edge (bottom1), and the Products/Industries
    # bullets above it are clamped to stop just before its label --
    # this is exactly the pair of boundaries that used to be ignored,
    # letting long bullet text overlap the "Target customers" heading.
    sub_row_y = top1 + 178

    draw.text((right + 24, top1 + 72), "Products / services", font=F_LABEL, fill=BLACK)
    draw_bullets(draw, products, right + 30, top1 + 100, 37, 3, max_y=sub_row_y - 8)

    split = right + col_w//2
    draw.text((split, top1 + 72), "Industries", font=F_LABEL, fill=BLACK)
    draw_bullets(draw, industries, split + 5, top1 + 100, 27, 3, max_y=sub_row_y - 8)

    draw.text((right + 24, sub_row_y), "Target customers", font=F_LABEL, fill=BLACK)
    draw_bullets(draw, targets, right + 30, sub_row_y + 27, 60, 2, max_y=bottom1 - 12)

    # Competitive position
    draw_section(draw, (left, top2, left + col_w, bottom2), "Competitive Position")
    competitors = items(data.get("competitors"), 4)
    advantages = items(data.get("competitive_advantages"), 3)

    draw.text((left + 24, top2 + 72), "Key competitors", font=F_LABEL, fill=BLACK)
    draw_bullets(draw, competitors, left + 30, top2 + 100, 34, 4, max_y=bottom2 - 12)

    split = left + col_w//2
    draw.text((split, top2 + 72), "Differentiators", font=F_LABEL, fill=BLACK)
    draw_bullets(draw, advantages, split + 5, top2 + 100, 27, 3, max_y=bottom2 - 12)

    # AI
    draw_section(draw, (right, top2, right + col_w, bottom2), "AI & Technology")
    ai_strategy = clean(data.get("ai_strategy"))
    ai_products = items(data.get("ai_products"), 2)
    ai_caps = items(data.get("ai_capabilities"), 2)

    # Same pattern as the Products & Market box: the AI strategy
    # paragraph is clamped to stop before the "AI products"/
    # "Capabilities" sub-row heading, and that sub-row's own bullets are
    # clamped to this box's bottom edge.
    ai_sub_row_y = top2 + 171

    draw_wrapped(
        draw,
        ai_strategy,
        right + 24,
        top2 + 72,
        84,
        max_lines=3,
        f=F_BODY,
        max_y=ai_sub_row_y - 8,
    )

    draw.text((right + 24, ai_sub_row_y), "AI products", font=F_LABEL, fill=BLACK)
    draw_bullets(draw, ai_products, right + 30, ai_sub_row_y + 27, 34, 2, max_y=bottom2 - 12)

    split = right + col_w//2
    draw.text((split, ai_sub_row_y), "Capabilities", font=F_LABEL, fill=BLACK)
    draw_bullets(draw, ai_caps, split + 5, ai_sub_row_y + 27, 27, 2, max_y=bottom2 - 12)

    # Strategic insights
    box_gap = 18
    box_w = (W - 2*MARGIN - 2*box_gap) // 3

    strengths = items(data.get("strengths"), 3)
    risks = items(data.get("risks") or data.get("weaknesses"), 3)
    opportunities = items(data.get("opportunities"), 3)

    for i, (title, vals) in enumerate([
        ("Strengths", strengths),
        ("Risks", risks),
        ("Opportunities", opportunities),
    ]):
        x = MARGIN + i * (box_w + box_gap)
        draw_section(draw, (x, top3, x + box_w, bottom3), title)
        draw_bullets(draw, vals, x + 30, top3 + 72, 46, 3, max_y=bottom3 - 12)

    draw.line((MARGIN, 1120, W-MARGIN, 1120), fill=LIGHT, width=2)
    draw.text(
        (MARGIN, 1145),
        "Generated from verified research data. Missing values are intentionally not estimated.",
        font=F_SMALL,
        fill=MID,
    )
    draw.text(
        (W-MARGIN, 1145),
        "Market Research AI",
        font=F_SMALL,
        fill=MID,
        anchor="ra",
    )

    path = os.path.join(
        OUTPUT_DIR,
        f"{safe_filename(company)}_executive_dashboard.png",
    )
    img.save(path, "PNG", optimize=True)
    return path