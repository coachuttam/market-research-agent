# ============================================================
# AI MARKET RESEARCH AGENT
# ============================================================
#
# PIPELINE
#
# User Question
#       ↓
# AI Research Agent
#       ↓
# Web Search
#       ↓
# Source Evaluation
#       ↓
# Source Filtering
#       ↓
# Source Ranking
#       ↓
# Source Summarization
#       ↓
# Source Verification
#       ↓
# Structured Data Extraction
#       ↓
# Infographic Generation
#       ↓
# Chart / Graph Generation
#       ↓
# Final Market Research Report
#
# FUTURE:
#       ↓
# DOCX Report
#       ↓
# PDF Report
#
# ============================================================


# ============================================================
# 1. IMPORTS
# ============================================================

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import ToolMessage
from dotenv import load_dotenv

import json
import re
from datetime import date

from tools.web_search import web_search
from infographic import generate_company_snapshot
from charts import generate_all_charts
from report_generator import generate_docx_report


# ============================================================
# 2. LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# 3. CREATE LLM
# ============================================================

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
)


# ============================================================
# 4. SOURCE EVALUATION
# ============================================================

def evaluate_source(title, content, question):

    prompt = f"""
You are a professional market research analyst.

Evaluate the following web source for the research question.

RESEARCH QUESTION:
{question}

SOURCE TITLE:
{title}

SOURCE CONTENT:
{content}

Evaluate the source using:

1. RELEVANCE
How relevant is the source to the research question?

2. QUALITY
How reliable and useful is the information?

Consider:

- Authority of the publisher
- Specificity of information
- Factual detail
- Relevance to the question
- Usefulness for professional research

Return EXACTLY this format:

RELEVANCE: High / Medium / Low
QUALITY: High / Medium / Low
REASON: <short explanation>

Do not add anything else.
"""

    response = llm.invoke(prompt)

    return response.content.strip()


# ============================================================
# 5. SOURCE FILTERING
# ============================================================

def filter_source(evaluation):

    evaluation_lower = evaluation.lower()

    # Reject low relevance sources
    if "relevance: low" in evaluation_lower:
        return False

    # Reject low quality sources
    if "quality: low" in evaluation_lower:
        return False

    return True


# ============================================================
# 6. SOURCE RANKING
# ============================================================

def rank_source(title, content, evaluation, question):

    prompt = f"""
You are an expert source-ranking analyst.

Research question:
{question}

Source title:
{title}

Source content:
{content}

Source evaluation:
{evaluation}

Score this source from 0 to 100.

Use the following scoring system:

Relevance: 0-30
Quality: 0-25
Authority: 0-25
Information Value: 0-20

Consider:

- How directly the source answers the research question
- Reliability of the publisher
- Authority of the organization
- Specific facts and statistics
- Depth of information
- Usefulness for professional market research

Return EXACTLY this format:

SCORE: XX
RELEVANCE SCORE: XX/30
QUALITY SCORE: XX/25
AUTHORITY SCORE: XX/25
INFORMATION VALUE SCORE: XX/20
REASON: <short explanation>

Do not add anything else.
"""

    response = llm.invoke(prompt)

    return response.content.strip()


# ============================================================
# 7. EXTRACT SOURCE SCORE
# ============================================================

def extract_score(ranking):

    match = re.search(
        r"SCORE:\s*(\d+)",
        ranking,
        re.IGNORECASE
    )

    if match:
        return int(match.group(1))

    return 0


# ============================================================
# 8. SOURCE SUMMARIZATION
# ============================================================

def summarize_source(title, content):

    prompt = f"""
You are a professional market research analyst.

Summarize the following source for use in a professional
market research report.

SOURCE TITLE:
{title}

SOURCE CONTENT:
{content}

Requirements:

- Write 5-8 sentences.
- Focus on factual information.
- Include important numbers when available.
- Include dates when available.
- Mention companies, products, markets and customers when relevant.
- Highlight important business developments.
- Explain why the information is relevant.
- Do not invent information.
- Do not make unsupported assumptions.

Return only the summary.
"""

    response = llm.invoke(prompt)

    return response.content.strip()


# ============================================================
# 9. SOURCE VERIFICATION
# ============================================================

def verify_sources(question, accepted_sources):

    if not accepted_sources:

        return "No accepted sources were available for verification."

    sources_text = ""

    for index, source in enumerate(accepted_sources):

        sources_text += f"""
==================================================
SOURCE {index + 1}
==================================================

TITLE:
{source['title']}

URL:
{source['url']}

SUMMARY:
{source['summary']}

SOURCE SCORE:
{source['score']}/100

SOURCE CONTENT:
{source['content']}

--------------------------------------------------
"""

    prompt = f"""
You are a senior market research verification analyst.

Your task is to verify important claims across multiple
research sources.

RESEARCH QUESTION:
{question}

RESEARCH SOURCES:
{sources_text}

Identify important claims relevant to the research question.

For every important claim:

1. State the claim.
2. Identify supporting sources.
3. Determine the verification status.

Use ONLY these statuses:

VERIFIED
PARTIALLY VERIFIED
CONFLICTING
NOT VERIFIED

Definitions:

VERIFIED:
The claim is supported by multiple reliable sources or
strong authoritative evidence.

PARTIALLY VERIFIED:
There is some supporting evidence, but the information
is incomplete.

CONFLICTING:
Reliable sources provide different information.

NOT VERIFIED:
There is insufficient evidence.

IMPORTANT RULES:

- Do not invent facts.
- Do not assume information is true without evidence.
- Clearly identify conflicting information.
- Prefer stronger and more authoritative sources.
- Focus on claims useful for the final market research report.

Return a professional verification report.
"""

    response = llm.invoke(prompt)

    return response.content.strip()


# ============================================================
# 10. SAFE JSON PARSER
# ============================================================

def parse_json_response(response):
    # AI models often wrap JSON answers in markdown code fences, like
    # ```json ... ```. We need to strip those off before we can read
    # the text as real JSON.
    text = response.content.strip()

    # Remove ```json
    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    # Remove ```
    text = re.sub(
        r"^```\s*",
        "",
        text
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    try:

        return json.loads(text)

    except json.JSONDecodeError:

        print(
            "\nWARNING: Structured data JSON could not be parsed."
        )

        return {}


# ============================================================
# 11. STRUCTURED DATA EXTRACTION
# ============================================================

# Words used to recognize employee and customer counts. Keep this list
# the same as in infographic.py, or a value found here might not show
# up on the Company Snapshot.

EMPLOYEE_KEYWORDS = [
    "employee", "workforce", "headcount", "staff", "personnel",
    "associate", "people",
]

CUSTOMER_KEYWORDS = [
    "customer", "user", "subscriber", "client", "member",
    "installed base",
]

# Different kinds of businesses are judged on different numbers. Rather
# than hard-code one fixed set of metrics for every company, we detect a
# rough industry archetype from the company's own stated industry (from
# the profile pass) and ask the financial pass to also look for whatever
# extra metrics actually matter for that kind of business. Metrics
# already covered elsewhere (Capex and Market Share, for example) are
# deliberately left out here to avoid asking for the same thing twice.
INDUSTRY_ARCHETYPE_KEYWORDS = {
    "saas": ["software", "saas", "cloud", "platform", "subscription service"],
    "manufacturing": ["manufactur", "industrial", "machinery", "automotive parts"],
    "consumer": ["consumer electronics", "consumer goods", "retail", "hardware"],
}

INDUSTRY_KPI_HINTS = {
    "saas": [
        "ARR (Annual Recurring Revenue)", "MRR (Monthly Recurring Revenue)",
        "Net Revenue Retention", "Customer Acquisition Cost (CAC)",
        "Customer Lifetime Value (LTV)", "Churn Rate",
    ],
    "manufacturing": [
        "Production Capacity", "Capacity Utilization Rate",
        "Units Sold", "Order Backlog",
    ],
    "consumer": [
        "Units Sold", "Average Selling Price",
    ],
}


def _detect_industry_archetype(industry, sub_industry):
    text = f"{industry} {sub_industry}".lower()
    for archetype, keywords in INDUSTRY_ARCHETYPE_KEYWORDS.items():
        if any(k in text for k in keywords):
            return archetype
    return None


def extract_structured_data(
    question,
    accepted_sources,
    verification_report
):

    if not accepted_sources:
        return {}

    schema = {
        "company_name": "",
        "legal_name": "",
        "parent_company": "",
        "brands": [],
        "industry": "",
        "sub_industry": "",
        "founded": "",
        "headquarters": "",
        "geographic_presence": [],
        "business_model": "",
        "revenue_model": "",
        "target_customers": [],
        "customer_segments": [],
        "industries_served": [],
        "products_services": [],
        "key_partnerships": [],
        "acquisitions": [],
        "leadership": [],
        "funding": "",
        "valuation": "",
        "revenue": "",
        "employees": "",
        "customers": "",
        "ai_strategy": "",
        "ai_products": [],
        "ai_capabilities": [],
        "ai_partnerships": [],
        "competitive_advantages": [],
        "competitors": [],
        "strengths": [],
        "weaknesses": [],
        "risks": [],
        "opportunities": [],
        "financial_metrics": [],
        "industry_kpis": [],
        "market_metrics": [],
        "customer_metrics": [],
        "employee_metrics": [],
        "operational_metrics": [],
        "segment_metrics": [],
        "geographic_metrics": [],
        "competitor_metrics": [],
        "competitive_comparison": [],
        "timeline": [],
        "source_verification": [],
        "annual_revenue_history": [],
        "extraction_audit": []
    }

    # --------------------------------------------------------
    # Instead of one giant prompt asking for everything at once (which
    # tended to skip whole categories like employees or segments), we
    # run 5 smaller, focused prompts. Each one gets only the sources
    # relevant to its topic, so the model doesn't have to search through
    # everything for the one thing it's looking for.
    # --------------------------------------------------------

    def _select_relevant_sources(keywords, min_count=5):
        # Only keep sources whose title/summary/content mentions one of
        # our keywords -- so, e.g., the "employees" pass mostly sees
        # sources actually about employees, not all 30+ sources.
        if not keywords:
            return accepted_sources

        matched = []
        for source in accepted_sources:
            text = " ".join([
                str(source.get("title", "")),
                str(source.get("summary", "")),
                str(source.get("content", "")),
            ]).lower()
            if any(k in text for k in keywords):
                matched.append(source)

        # If keyword filtering matched too few sources, fall back to the
        # full set rather than risk starving the pass of a source that
        # matched on a term the keyword list didn't anticipate.
        if len(matched) < min_count:
            return accepted_sources

        return matched

    def _build_sources_text(sources):
        # Turns our list of source dicts into one big block of text we
        # can paste into a prompt.
        text = ""
        for index, source in enumerate(sources):
            text += f"""
==================================================
SOURCE {index + 1}
==================================================
TITLE:
{source['title']}
URL:
{source['url']}
SOURCE SCORE:
{source['score']}/100
SUMMARY:
{source['summary']}
SOURCE CONTENT:
{source['content']}
--------------------------------------------------
"""
        return text

    def _run_extraction_pass(pass_name, schema_subset, focus_instructions, sources):
        # Runs one focused extraction pass: builds a prompt asking the AI
        # for just a few specific fields, sends it, and returns the
        # answer as a dict.
        pass_sources_text = _build_sources_text(sources)
        schema_subset_text = json.dumps(schema_subset, indent=4, ensure_ascii=False)

        prompt = f"""
You are a senior financial-data extraction specialist performing a
FOCUSED extraction pass: {pass_name}.

RESEARCH QUESTION:
{question}

VERIFICATION REPORT:
{verification_report}

SOURCE MATERIAL:
{pass_sources_text}

{focus_instructions}

==================================================
RULES THAT APPLY TO EVERY PASS
==================================================

1. NEVER use general knowledge -- extract ONLY from the supplied source
   material.
2. NEVER invent or estimate a value.
3. Every numerical metric must have a source_title and source_url.
4. If a claim is unsupported by the sources, leave the field or list
   empty rather than guessing.
5. Company guidance is NEVER historical actual revenue. Quarterly/YTD
   data must NEVER be placed in annual history.

==================================================
OUTPUT
==================================================

Return ONLY valid JSON matching this exact schema (these keys only):
{schema_subset_text}
"""

        response = llm.invoke(prompt)
        result = parse_json_response(response)

        if not isinstance(result, dict):
            result = {}

        # Restrict the return value to exactly this pass's own schema
        # keys. Without this, a stray extra key the model adds despite
        # being told "these keys only" (e.g. the financial pass
        # hallucinating a "company_name" or "strengths" key) would
        # silently overwrite a different pass's correctly-extracted
        # field when all five results get merged together below --
        # since passes run in a fixed order, a later pass's mistake
        # would win with no validation catching it for non-metric
        # fields.
        filtered_result = {}
        for key, default_value in schema_subset.items():
            if key in result:
                filtered_result[key] = result[key]
            else:
                filtered_result[key] = default_value.copy() if isinstance(default_value, list) else default_value

        return filtered_result

    FINANCIAL_SOURCE_KEYWORDS = [
        "revenue", "income", "margin", "earnings", "eps", "cash flow",
        "ebitda", "profit", "sales", "fiscal", "quarter", "10-k", "10-q",
        "annual report", "financial", "guidance",
    ]
    SEGMENT_GEO_SOURCE_KEYWORDS = [
        "segment", "geographic", "region", "americas", "europe", "asia",
        "china", "japan", "division", "business unit", "10-k",
        "annual report",
    ]
    EMPLOYEE_CUSTOMER_SOURCE_KEYWORDS = EMPLOYEE_KEYWORDS + CUSTOMER_KEYWORDS
    MARKET_COMPETITOR_SOURCE_KEYWORDS = [
        "market share", "market size", "cagr", "competitor", "competition",
        "compete", "rival", "versus", " vs ", " vs. ",
    ]

    profile_schema = {
        k: schema[k] for k in [
            "company_name", "legal_name", "parent_company", "brands",
            "industry", "sub_industry", "founded", "headquarters",
            "geographic_presence", "business_model", "revenue_model",
            "target_customers", "customer_segments", "industries_served",
            "products_services", "key_partnerships", "acquisitions",
            "leadership", "funding", "valuation", "ai_strategy",
            "ai_products", "ai_capabilities", "ai_partnerships",
            "competitive_advantages", "competitors", "strengths",
            "weaknesses", "risks", "opportunities", "timeline",
        ]
    }
    financial_schema = {"financial_metrics": schema["financial_metrics"], "industry_kpis": schema["industry_kpis"]}
    segment_geo_schema = {
        "segment_metrics": schema["segment_metrics"],
        "geographic_metrics": schema["geographic_metrics"],
    }
    employee_customer_schema = {
        "employee_metrics": schema["employee_metrics"],
        "customer_metrics": schema["customer_metrics"],
    }
    market_competitor_schema = {
        "market_metrics": schema["market_metrics"],
        "competitor_metrics": schema["competitor_metrics"],
        "competitive_comparison": schema["competitive_comparison"],
    }

    profile_result = _run_extraction_pass(
        "company profile, positioning, and qualitative analysis",
        profile_schema,
        """
==================================================
FOCUS: COMPANY PROFILE, POSITIONING, AND QUALITATIVE ANALYSIS
==================================================

Extract company identity, business description, products, customers,
partnerships, acquisitions, leadership, AI strategy, competitive
positioning, SWOT-style qualitative fields, and a verified event
timeline.

For the timeline: dates must be explicitly supported by a source. For a
timeline event describing a financial-result milestone (e.g. "record
revenue for FY2025"), use the fiscal year/period the achievement
pertains to as the date -- NOT the press-release announcement date. A
FY2025 annual result announced in February 2026 is a 2025 event, not a
2026 event.

For strengths/risks/opportunities/weaknesses: base these on what the
sources actually say about this specific company's position, not
generic industry boilerplate.
""",
        accepted_sources,
    )

    # Detect a rough industry archetype from what the profile pass
    # already found, so the financial pass knows which extra KPIs (if
    # any) are worth looking for -- ARR/MRR for a SaaS company,
    # production capacity for a manufacturer, etc. This costs no extra
    # LLM call since it only reads data the profile pass already
    # produced.
    industry_archetype = _detect_industry_archetype(
        profile_result.get("industry", ""),
        profile_result.get("sub_industry", ""),
    )

    if industry_archetype and INDUSTRY_KPI_HINTS.get(industry_archetype):
        hint_list = ", ".join(INDUSTRY_KPI_HINTS[industry_archetype])
        industry_kpi_instructions = f"""
==================================================
INDUSTRY-SPECIFIC METRICS (industry_kpis)
==================================================

Based on its stated industry, this company appears to be a
{industry_archetype} business. In addition to financial_metrics above,
also look for these {industry_archetype}-specific metrics, and extract
any that are explicitly reported into industry_kpis (same field shape
as financial_metrics: metric, value, unit, year, period, type,
source_title, source_url, verification):

{hint_list}

Only include a metric here if a source explicitly reports it -- if none
of these apply or are reported, leave industry_kpis as an empty list
rather than guessing or approximating one from unrelated numbers.
"""
    else:
        industry_kpi_instructions = ""

    financial_result = _run_extraction_pass(
        "financial metrics",
        financial_schema,
        """
==================================================
FOCUS: FINANCIAL METRICS -- BE EXHAUSTIVE
==================================================

This is the ONLY pass extracting financial_metrics for this report, so
be thorough: extract every distinct financial figure explicitly
supported by the sources, not just the first one or two you find.

1. A rounded headline value is acceptable only when it is a faithful
   rounding of an exact value present in the same source; prefer the
   exact table value whenever available.
2. Preserve the source's actual period: FY, Q1-Q4, YTD, guidance, or
   forecast.
3. For financial tables marked "In thousands", convert only the
   DISPLAYED value to the requested unit. Example: 7,245,519 thousand
   USD = 7,245.519 USD million. Do not change the underlying fact.
4. If a source reports a rounded figure in prose (e.g. "$2.02 billion")
   and a table provides the exact figure, prefer the exact table figure.

PRIMARY-SOURCE PRIORITY: prefer, in order: regulatory filing/10-K/10-Q,
official annual report, official investor-relations earnings release,
official company newsroom, reputable secondary financial source.

FIVE-YEAR REVENUE: extract ALL directly supported annual revenue rows
you can find -- downstream code selects the latest five completed
fiscal years.

LATEST FINANCIALS: extract, when explicitly available: Annual Revenue,
Quarterly Revenue, Gross Profit, Gross Margin, Operating Income,
Operating Margin, Net Income, EPS, Free Cash Flow, Operating Cash Flow,
Capital Expenditure, Cash and Cash Equivalents, Total Debt, Net Debt,
Revenue Growth, Company Guidance.

Required fields per row: metric, value, unit, year, period, type,
source_title, source_url, verification. Example:
{
  "metric": "Annual Revenue",
  "value": "7245.519",
  "unit": "USD million",
  "year": 2025,
  "period": "FY2025",
  "type": "actual",
  "source_title": "2025 Annual Report",
  "source_url": "https://example.com",
  "verification": "VERIFIED"
}
""" + industry_kpi_instructions,
        _select_relevant_sources(FINANCIAL_SOURCE_KEYWORDS),
    )

    segment_geo_result = _run_extraction_pass(
        "segment and geographic revenue",
        segment_geo_schema,
        """
==================================================
FOCUS: SEGMENT AND GEOGRAPHIC REVENUE -- BE EXHAUSTIVE
==================================================

This is the ONLY pass extracting segment_metrics and geographic_metrics.
Actively look for a segment or geographic revenue breakdown in EVERY
source provided -- annual reports and 10-Ks almost always contain one
even when it is not the article's main subject. Do not stop checking
after the first or most obvious source.

Extract directly reported segment revenue, growth, gross profit,
operating income/loss and margins, preserving the exact period and
segment name. Extract directly reported geographic revenue and growth
(e.g. Americas, Europe, Greater China, Japan, Rest of Asia Pacific),
preserving the exact period and region name. NEVER calculate segment or
regional revenue from a percentage when the source does not provide the
absolute number.

Required fields per row: segment (or region), metric, value, unit, year,
period, type, source_title, source_url, verification.
""",
        _select_relevant_sources(SEGMENT_GEO_SOURCE_KEYWORDS),
    )

    employee_customer_result = _run_extraction_pass(
        "employee and customer metrics",
        employee_customer_schema,
        """
==================================================
FOCUS: EMPLOYEE AND CUSTOMER METRICS -- BE EXHAUSTIVE
==================================================

This is the ONLY pass extracting employee_metrics and customer_metrics.
Some of the supplied sources may be dedicated specifically to headcount
or customer/user counts (e.g. an article titled "Company Employee Count
2026") -- check EVERY source for a workforce or customer/user/
subscriber figure, even short, simple pages, not just primary financial
filings.

Companies describe their own workforce with different words --
employees, associates, staff, team members, personnel -- and their
customer base with different words -- customers, users, subscribers,
clients, members, installed base. Extract whichever term the source
itself uses, preserving that wording in the metric/unit field rather
than forcing it to say "employees" or "customers". A third-party
employee estimate can be used only if clearly labelled as a third-party
estimate, not presented as an official company headcount.

Required fields per row: metric, value, unit, year, period, type,
source_title, source_url, verification.
""",
        _select_relevant_sources(EMPLOYEE_CUSTOMER_SOURCE_KEYWORDS),
    )

    market_competitor_result = _run_extraction_pass(
        "market and competitor metrics",
        market_competitor_schema,
        """
==================================================
FOCUS: MARKET AND COMPETITOR METRICS -- BE EXHAUSTIVE
==================================================

This is the ONLY pass extracting market_metrics, competitor_metrics, and
competitive_comparison. Check EVERY source for a market size, CAGR,
market share, or category growth figure -- including sources whose
title itself names a specific percentage or statistic (e.g. "Company
hits record 20% global market share"). Also check for competitor market
share or revenue reported in the same source, since these are often
listed side by side in one table.

For competitor rows, extract numerical metrics only when reliably
reported and directly comparable (e.g. market share figures from the
same report, for the same period, across multiple named companies).
Never invent a market share or competitor score that is not explicitly
stated in a source.

competitor_metrics must be a competitor's MARKET SHARE (a percentage of
the overall market), REVENUE, or a growth/CAGR figure for their business
-- never their market capitalization or stock valuation. Market cap is
not a measure of market share and does not belong here; if a source
only gives a competitor's market cap or valuation, leave that competitor
out of competitor_metrics entirely rather than substituting valuation
for share. Prefer market-share percentages specifically over revenue
when a source states both, since that is what a market-composition
comparison across competitors actually needs.

Numeric competitor figures are only as reliable as their source. Weigh
this: a specific figure attributed to a named analyst report, the
competitor's own filing, or a reputable industry publication is far
more trustworthy than a rounded-looking estimate from a low-relevance
aggregator/directory site. When only a low-relevance source offers a
number and it looks like a rough estimate (a suspiciously round figure
with no stated methodology), it is safer to omit it than to report it
as if it were precise.

A "competitor" must be a real, named COMPANY -- never a market segment,
product category, distribution channel, or catch-all grouping such as
"Standalone Segment", "Connected Segment", "Online Channel", "Others",
or "Rest of Market". If a table's row labels are segment/category names
rather than company names, that table is not competitor data at all --
do not extract it into competitor_metrics or competitive_comparison,
even if the surrounding report also happens to mention a real
competitor's name elsewhere.

A source is only valid for a competitor row if it is actually discussing
{company} -- either directly comparing {company} to the named
competitor, or covering the same specific product/market that {company}
is known (from elsewhere in this research) to compete in. A generic
third-party market-sizing report for an unrelated niche {company} does
not participate in (e.g. a "kids' smartwatch market" report when
{company} makes fitness/aviation/marine devices, not kids' products) is
not evidence about {company}'s competitors, even if it names real
companies and even if it matched this pass's source-selection keywords.
When in doubt about whether a source is really about {company}'s own
competitive position, leave that source's numbers out rather than
including them.

Required fields per row: metric, value, unit, year, period, type,
source_title, source_url, verification, and for competitor rows a
"competitor" field naming which company the row is about.""".replace(
            "{company}",
            str(profile_result.get("company_name") or "").strip() or str(question).strip() or "the company",
        ) + """

==================================================
COMPETITIVE COMPARISON (qualitative, separate from competitor_metrics)
==================================================

Also build competitive_comparison: one entry per real, named competitor
you find described in the sources, covering what they do and how they
compare -- not just their numbers. For each competitor, extract only
what a source actually says:

- competitor: the company's name (must be a real company you found
  discussed in the sources, not one you are only aware of generally)
- main_segment: the market/segment they primarily compete in
- products_services: up to 3 of their relevant products/services
- strengths: up to 2 specific strengths a source attributes to them
- weaknesses: up to 2 specific weaknesses a source attributes to them
- competitive_advantage: one short phrase on what differentiates them
- market_positioning: one short phrase on how they are positioned
  (e.g. "premium", "budget", "market leader")
- relevance_to_target: one short phrase on why this competitor matters
  to the company being researched
- source_title, source_url: the exact source this profile came from

Every field above must be something the cited source actually states or
clearly implies -- do not fill in a plausible-sounding strength or
weakness that the source does not support. If a source only names a
competitor without describing them, still include the name with
whatever fields are actually supported and leave the rest empty rather
than inventing detail.
""",
        _select_relevant_sources(MARKET_COMPETITOR_SOURCE_KEYWORDS),
    )

    structured_data = {}
    for key, default_value in schema.items():
        structured_data[key] = default_value.copy() if isinstance(default_value, list) else default_value

    for pass_result in [
        profile_result, financial_result, segment_geo_result,
        employee_customer_result, market_competitor_result,
    ]:
        structured_data.update(pass_result)
    # Basic helpers.
    # --------------------------------------------------------

    metric_fields = [
        "financial_metrics",
        "industry_kpis",
        "market_metrics",
        "customer_metrics",
        "employee_metrics",
        "operational_metrics",
        "segment_metrics",
        "geographic_metrics",
        "competitor_metrics"
    ]

    allowed_types = {"actual", "reported", "guidance", "forecast", "derived"}
    allowed_verification = {"VERIFIED", "PARTIALLY VERIFIED", "DERIVED"}

    def clean_metric_list(items):
        if not isinstance(items, list):
            return []

        cleaned = []

        for item in items:
            if not isinstance(item, dict):
                continue

            if str(item.get("value", "")).strip() == "":
                continue

            try:
                year = int(item.get("year"))
            except (TypeError, ValueError):
                continue

            metric = str(item.get("metric", "")).strip()
            unit = str(item.get("unit", "")).strip()
            period = str(item.get("period", "")).strip()
            source_title = str(item.get("source_title", "")).strip()
            source_url = str(item.get("source_url", "")).strip()
            verification = str(item.get("verification", "")).upper().strip()
            item_type = str(item.get("type", "")).lower().strip()

            if not all([metric, unit, period, source_title, source_url]):
                continue
            if verification not in allowed_verification:
                continue
            if item_type not in allowed_types:
                continue

            item["year"] = year
            item["metric"] = metric
            item["unit"] = unit
            item["period"] = period
            item["verification"] = verification
            item["type"] = item_type
            cleaned.append(item)

        return cleaned

    for field in metric_fields:
        structured_data[field] = clean_metric_list(structured_data.get(field, []))

    # --------------------------------------------------------
    # Remove obviously-wrong employee/customer values (a date, a bare
    # year, a dollar amount, a percentage) that don't belong here.
    # --------------------------------------------------------

    # This pattern matches any month name (used to catch a date that
    # got mistakenly extracted as if it were a count).
    month_pattern = r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b"

    def contamination_filter(items, keywords):
        # Keep only the items that (a) actually match one of our
        # employee/customer keywords, and (b) don't look like some other
        # kind of value (a date, a year, money, a percentage) that
        # doesn't belong here.
        valid = []
        for item in items:
            metric_name = str(item.get("metric", "")).lower()
            unit = str(item.get("unit", "")).lower()
            value = str(item.get("value", "")).lower().strip()

            if not (
                any(k in metric_name for k in keywords)
                or any(k in unit for k in keywords)
            ):
                continue

            if re.search(month_pattern, value):
                continue
            if re.fullmatch(r"(19|20)\d{2}", value):
                # Matches a 4-digit year like "2025", but not a 4-digit
                # count like "5000" -- a company can have 5,000
                # employees, and that's a valid number, not a year.
                continue
            if any(term in value for term in ["usd", "million dollars", "billion dollars", "funding", "valuation", "%"]):
                continue
            if "%" in unit or "percent" in unit:
                # A genuine headcount or customer count is never a
                # percentage. This catches a value like 8 with unit
                # "percent" (e.g. an "activity up 8%" growth stat) that
                # the check above misses, since it only looks for a "%"
                # character actually written in the value itself.
                continue

            valid.append(item)
        return valid

    structured_data["employee_metrics"] = contamination_filter(
        structured_data["employee_metrics"], EMPLOYEE_KEYWORDS
    )
    structured_data["customer_metrics"] = contamination_filter(
        structured_data["customer_metrics"], CUSTOMER_KEYWORDS
    )

    # --------------------------------------------------------
    # Segment / geography shape validation.
    # --------------------------------------------------------

    structured_data["segment_metrics"] = [
        x for x in structured_data["segment_metrics"]
        if str(x.get("segment", "")).strip()
    ]

    structured_data["geographic_metrics"] = [
        x for x in structured_data["geographic_metrics"]
        if str(x.get("region", "")).strip()
    ]

    # --------------------------------------------------------
    # Check that each extracted number actually appears in its cited
    # source, allowing for unit differences (thousands/millions/billions)
    # and small rounding. This is how we verify a claim is real.
    # --------------------------------------------------------

    def normalize_url(url):
        # Makes two URLs that point to the same page compare as equal,
        # even if one has a trailing slash or a "#section" at the end.
        value = str(url or "").strip().lower()
        value = value.split("#", 1)[0]
        value = value.rstrip("/")
        return value

    source_records = []
    for source in accepted_sources:
        source_records.append({
            "url": normalize_url(source.get("url")),
            "title": str(source.get("title", "")),
            "text": " ".join([
                str(source.get("title", "")),
                str(source.get("summary", "")),
                str(source.get("content", ""))
            ])
        })

    def parse_number(value):
        # Pulls the first number out of a string, e.g. "$1,234.5" -> 1234.5.
        text = str(value or "").replace(",", "").replace("$", "").strip()
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None

    def source_unit_multiplier(text):
        # Figures out if a source's numbers are stated "in thousands",
        # "in millions", etc., and returns the multiplier to convert
        # them into millions.
        lower = text.lower()
        # Financial tables commonly state the scale once at the top.
        if re.search(r"in\s+thousands|\(in\s+thousands\)", lower):
            return 0.001, "thousand"
        if re.search(r"in\s+millions|\(in\s+millions\)", lower):
            return 1.0, "million"
        if re.search(r"in\s+billions|\(in\s+billions\)", lower):
            return 1000.0, "billion"
        return 1.0, "unit"

    def item_to_millions(item):
        # Converts an extracted value + unit (e.g. "7.25" + "billion")
        # into a single number in millions, so different items can be
        # compared on the same scale.
        number = parse_number(item.get("value"))
        if number is None:
            return None
        unit = str(item.get("unit", "")).lower()
        if "billion" in unit:
            result = number * 1000.0
        elif "thousand" in unit:
            result = number / 1000.0
        elif "million" in unit:
            result = number
        else:
            # No scale word in the unit (e.g. just "USD"). If the raw
            # number is way too big to plausibly already be "in
            # millions" (a real company's revenue in millions is rarely
            # over a million), it's almost certainly a plain dollar
            # amount instead -- e.g. 2,360,000,000 meaning $2.36
            # billion, not $2.36 billion million.
            result = number / 1_000_000.0 if number >= 1_000_000 else number

        # Extra safety net: sometimes the unit says "million" but the
        # value was ALSO already written out as a raw dollar amount
        # (e.g. value 2,360,000,000 with unit "USD million" -- which
        # would literally mean an impossible $2.36 quadrillion). No real
        # company metric is in the tens of trillions of dollars, so if
        # our result is still that huge, rescale down regardless of what
        # the unit claimed.
        if abs(result) >= 10_000_000:
            result = result / 1_000_000.0

        return result

    def source_number_candidates(text):
        # Finds every number-looking piece of text (like "$1,234.5" or
        # "42%") and returns it along with where it was found.
        pattern = re.compile(r"(?<![A-Za-z])\$?\(?-?\d[\d,]*(?:\.\d+)?\)?%?")
        for match in pattern.finditer(text):
            token = match.group(0)
            number = parse_number(token)
            if number is not None:
                yield number, match.start(), match.end(), token

    def metric_keywords(item):
        # Builds a list of words to search for in the source text, based
        # on what kind of metric this is (e.g. "Operating Income" ->
        # search for "operating income" nearby).
        metric = str(item.get("metric", "")).lower()
        keywords = []

        if "revenue" in metric or "net sales" in metric:
            keywords += ["net sales", "revenue"]
        if "gross profit" in metric:
            keywords += ["gross profit"]
        if "gross margin" in metric:
            keywords += ["gross margin"]
        if "operating income" in metric:
            keywords += ["operating income"]
        if "operating margin" in metric:
            keywords += ["operating income %", "operating margin"]
        if "net income" in metric:
            keywords += ["net income"]
        if "eps" in metric:
            keywords += ["eps", "diluted eps"]
        if "free cash flow" in metric:
            keywords += ["free cash flow"]
        if "operating cash flow" in metric:
            keywords += ["operating activities", "operating cash flow", "net cash provided by operating activities"]
        if "guidance" in metric:
            keywords += ["guidance", "anticipate revenue"]
        if any(k in metric for k in EMPLOYEE_KEYWORDS):
            keywords += EMPLOYEE_KEYWORDS
        if any(k in metric for k in CUSTOMER_KEYWORDS):
            keywords += CUSTOMER_KEYWORDS

        segment = str(item.get("segment", "")).strip().lower()
        region = str(item.get("region", "")).strip().lower()
        if segment:
            keywords += [segment]
        if region:
            keywords += [region]

        return list(dict.fromkeys(keywords))

    def value_matches_source(item, source_text):
        # Checks whether the number we extracted actually shows up
        # somewhere in the text of the source we said it came from.
        target = item_to_millions(item)
        if target is None:
            return False

        year = str(item.get("year", ""))
        keywords = metric_keywords(item)

        # Instead of searching the whole document, we look at small
        # windows of text right around each keyword (like "revenue").
        # This avoids accidentally matching an unrelated number, like a
        # date or page number, somewhere else in a long document.
        windows = []
        lower_text = source_text.lower()

        for keyword in keywords:
            start = 0
            while True:
                position = lower_text.find(keyword, start)
                if position == -1:
                    break
                windows.append(source_text[max(0, position - 1200): min(len(source_text), position + 1800)])
                start = position + len(keyword)

        if not windows:
            windows = [source_text]

        # Allow small rounding differences (1%, or at least 5) instead
        # of requiring an exact digit-for-digit match. This lets "$7.25
        # billion" in a sentence match an exact "7,245.519" in a table.
        tolerance = max(abs(target) * 0.01, 5.0)

        # Whether THIS item is itself claiming a percentage/ratio value
        # (growth, margin, EPS) rather than a dollar amount or count.
        # Needed below to stop a source's "18%" from ever validating a
        # claimed dollar figure just because both happen to parse to the
        # same number 18.
        is_percent_item = "%" in str(item.get("unit", "")) or "eps" in str(item.get("metric", "")).lower()

        for window in windows:
            # Figure out the unit scale from THIS window's own text, not
            # the whole document. A press release commonly has a formal
            # "(In thousands)" table AND a separate plain-English
            # highlights paragraph in plain millions -- using one
            # document-wide scale for every window would wrongly apply
            # the table's "divide by 1000" to numbers that were never in
            # thousands to begin with.
            unit_multiplier, _ = source_unit_multiplier(window)

            for raw_number, _, _, raw_token in source_number_candidates(window):
                # A source token written as "18%" describes a growth
                # rate or margin, never a dollar amount -- even though it
                # parses to the same float as "$18 million" would. Left
                # unchecked, a sentence like "Marine segment revenue grew
                # 18% in 2025" would wrongly verify a claimed Marine
                # REVENUE of $18 million, since the window contains
                # "Marine", "revenue", and the number 18 all at once.
                # Only let a percent-shaped source token validate a
                # dollar/count figure when the item being checked is
                # itself percent-shaped.
                if raw_token.strip().endswith("%") and not is_percent_item:
                    continue

                # Candidate is already in source table units when the source
                # has a global "in thousands" marker.
                candidate_millions = raw_number * unit_multiplier

                if abs(candidate_millions - target) <= tolerance:
                    if not year or year in source_text:
                        return True

                # Prose can report $7.25 billion while item uses USD million.
                # Try billion interpretation as a second pass.
                candidate_billion_millions = raw_number * 1000.0
                if abs(candidate_billion_millions - target) <= tolerance:
                    if not year or year in source_text:
                        return True

                # Percentage, EPS, and headcount/customer-count values
                # should not be scaled by the thousand/million/billion
                # multiplier above -- compare them directly, with a small
                # absolute allowance for rounding (e.g. "59%" vs. "59.2%").
                is_count_metric = any(
                    k in str(item.get("metric", "")).lower()
                    for k in (EMPLOYEE_KEYWORDS + CUSTOMER_KEYWORDS)
                )
                if "%" in str(item.get("unit", "")) or "eps" in str(item.get("metric", "")).lower():
                    if abs(raw_number - target) <= max(abs(target) * 0.02, 0.15):
                        if not year or year in source_text:
                            return True
                elif is_count_metric:
                    if abs(raw_number - target) <= max(abs(target) * 0.01, 5.0):
                        if not year or year in source_text:
                            return True

        return False

    def url_slug(url):
        # The last part of a URL's path, e.g. for ".../news/my-article",
        # the slug is "my-article".
        value = normalize_url(url)
        if not value:
            return ""
        return value.rsplit("/", 1)[-1]

    def url_id_suffix(url):
        # Many news sites end an article's URL with a long unique ID
        # number, e.g. "...-302691157.html". Matching on just that ID
        # lets us recognize the same article even if the rest of the
        # URL looks slightly different.
        slug = url_slug(url)
        match = re.search(r"(\d{6,})(?:\.\w+)?$", slug)
        return match.group(1) if match else ""

    def find_source_for_item(item):
        # Tries to find which of our accepted sources an extracted item
        # was cited from. Tries a few methods, from most to least exact:
        # exact URL, then unique article ID, then URL ending, then title.
        requested_url = normalize_url(item.get("source_url"))
        requested_title = str(item.get("source_title", "")).strip().lower()

        # URL match first.
        for source in source_records:
            if requested_url and source["url"] == requested_url:
                return source

        # Then a distinctive numeric article-ID match, which survives
        # small path differences an extraction step can introduce while
        # still citing the same real article.
        requested_id = url_id_suffix(item.get("source_url"))
        if requested_id:
            for source in source_records:
                if url_id_suffix(source["url"]) == requested_id:
                    return source

        # Then a bare slug match (last path segment), for URLs that
        # differ earlier in the path but share the same final segment.
        requested_slug = url_slug(item.get("source_url"))
        if requested_slug:
            for source in source_records:
                if url_slug(source["url"]) == requested_slug:
                    return source

        # Then title similarity. This handles redirected/parameterized URLs.
        for source in source_records:
            title = source["title"].lower()
            if requested_title and (
                requested_title == title
                or requested_title in title
                or title in requested_title
            ):
                return source

        return None

    def _normalize_currency_value(item):
        # Once an item is verified, rewrite its stored value/unit to a
        # consistent "USD million" form -- using the same scale-
        # detection already used to verify it. Without this, a value
        # originally written as raw dollars (e.g. 2,360,000,000) still
        # verifies correctly, but flows downstream unchanged into charts
        # and tables, producing an ugly "1e9"-scale axis instead of a
        # clean "2,360" millions-scale number.
        unit = str(item.get("unit", "")).lower()
        metric = str(item.get("metric", "")).lower()

        if "usd" not in unit and "dollar" not in unit:
            return  # not a currency figure at all (a percent, a count, etc.)
        if "per share" in unit or "eps" in metric:
            return  # a per-share amount, not an aggregate figure to rescale

        normalized = item_to_millions(item)
        if normalized is None:
            return

        item["value"] = f"{normalized:.3f}"
        item["unit"] = "USD million"

    removed_metrics = []

    for field in metric_fields:
        kept = []

        for item in structured_data[field]:
            source = find_source_for_item(item)

            if source is None:
                removed_metrics.append({
                    "field": field,
                    "metric": item.get("metric", ""),
                    "value": item.get("value", ""),
                    "year": item.get("year", ""),
                    "cited_source_title": item.get("source_title", ""),
                    "cited_source_url": item.get("source_url", ""),
                    "reason": "Cited source could not be matched to the accepted source set."
                })
                continue

            if value_matches_source(item, source["text"]):
                _normalize_currency_value(item)
                kept.append(item)
            else:
                removed_metrics.append({
                    "field": field,
                    "metric": item.get("metric", ""),
                    "value": item.get("value", ""),
                    "year": item.get("year", ""),
                    "cited_source_title": item.get("source_title", ""),
                    "cited_source_url": item.get("source_url", ""),
                    "reason": "Numerical value could not be matched to the cited source after unit/rounding normalization."
                })

        structured_data[field] = kept

    # --------------------------------------------------------
    # Competitive comparison is qualitative (strengths, weaknesses,
    # positioning) -- there's no number to tolerance-check the way we
    # check a dollar figure. Instead, every row must clear two bars:
    # (1) it cites a source that's actually in our accepted set, same as
    # any other claim, and (2) it names a competitor that was already
    # independently identified elsewhere in the research (the profile
    # pass's "competitors" list) -- not a name invented only for this
    # table. List/text fields are also capped in length so one row can't
    # balloon into a wall of unsupported-sounding detail.
    # --------------------------------------------------------

    known_competitors = [
        str(c).strip().lower() for c in structured_data.get("competitors", [])
        if str(c).strip()
    ]

    def _is_known_competitor(name):
        name_l = str(name).strip().lower()
        if not name_l:
            return False
        return any(name_l in known or known in name_l for known in known_competitors)

    def _capped_list(value, limit=3, max_len=140):
        if isinstance(value, str):
            value = [value]  # tolerate a single item returned as a bare string
        if not isinstance(value, list):
            return []
        return [str(x).strip()[:max_len] for x in value if str(x).strip()][:limit]

    valid_comparison = []
    comparison_removed = []

    for entry in structured_data.get("competitive_comparison", []) or []:
        if not isinstance(entry, dict):
            continue

        competitor = str(entry.get("competitor", "")).strip()
        if not competitor:
            continue

        if not _is_known_competitor(competitor):
            comparison_removed.append({
                "field": "competitive_comparison",
                "metric": "competitor profile",
                "value": competitor,
                "year": "",
                "cited_source_title": entry.get("source_title", ""),
                "cited_source_url": entry.get("source_url", ""),
                "reason": (
                    f"'{competitor}' was not identified anywhere else in "
                    "the research (not in the verified competitors list) "
                    "-- dropped to avoid an unconfirmed name."
                ),
            })
            continue

        source = find_source_for_item({
            "source_url": entry.get("source_url"),
            "source_title": entry.get("source_title"),
        })
        if source is None:
            comparison_removed.append({
                "field": "competitive_comparison",
                "metric": "competitor profile",
                "value": competitor,
                "year": "",
                "cited_source_title": entry.get("source_title", ""),
                "cited_source_url": entry.get("source_url", ""),
                "reason": "Cited source could not be matched to the accepted source set.",
            })
            continue

        valid_comparison.append({
            "competitor": competitor[:80],
            "main_segment": str(entry.get("main_segment", "")).strip()[:100],
            "products_services": _capped_list(entry.get("products_services")),
            "strengths": _capped_list(entry.get("strengths"), limit=2),
            "weaknesses": _capped_list(entry.get("weaknesses"), limit=2),
            "competitive_advantage": str(entry.get("competitive_advantage", "")).strip()[:200],
            "market_positioning": str(entry.get("market_positioning", "")).strip()[:200],
            "relevance": str(entry.get("relevance_to_target") or entry.get("relevance", "")).strip()[:200],
            "source_title": entry.get("source_title", ""),
            "source_url": entry.get("source_url", ""),
        })

    # Dedupe by competitor name (keep the first, since passes run in a
    # fixed order and the first hit is as good as any later duplicate).
    seen_names = set()
    deduped_comparison = []
    for entry in valid_comparison:
        key = entry["competitor"].lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        deduped_comparison.append(entry)

    structured_data["competitive_comparison"] = deduped_comparison[:6]

    if comparison_removed:
        removed_metrics.extend(comparison_removed)

    # --------------------------------------------------------
    # Sanity check: no single segment or region can have more revenue
    # than the whole company. This catches cases where a segment's name
    # got paired with the wrong number from a different table in the
    # source (each number looked valid on its own, so the normal check
    # above didn't catch it).
    # --------------------------------------------------------

    def _year_from_item(item):
        try:
            return int(item.get("year"))
        except (TypeError, ValueError):
            return None

    def _value_to_millions(item):
        try:
            number = float(str(item.get("value", "")).replace(",", ""))
        except (TypeError, ValueError):
            return None
        unit = str(item.get("unit", "")).lower()
        if "billion" in unit:
            result = number * 1000.0
        elif "thousand" in unit:
            result = number / 1000.0
        elif "million" not in unit and number >= 1_000_000:
            # Same fix as item_to_millions above: a bare number with no
            # scale word that's way too big to be "in millions" is
            # almost certainly a plain dollar amount, e.g. 2,360,000,000
            # for $2.36B.
            result = number / 1_000_000.0
        else:
            result = number

        # Same extra safety net as item_to_millions: catches a
        # self-contradictory "million" unit paired with an
        # already-raw-dollar value.
        if abs(result) >= 10_000_000:
            result = result / 1_000_000.0

        return result

    implausible_removed = []

    # Build a lookup of "this year -> the company's real total revenue",
    # so we can compare each segment/region against it below.
    #
    # This MUST be restricted to annual/full-year actuals, the same way
    # annual_revenue_history is filtered further down -- otherwise a
    # "Quarterly Revenue" row (which is still legitimately tagged
    # type: "actual", since "actual" only means "not guidance") can
    # become the year's baseline whenever no full annual figure has
    # been extracted yet for that year (very common for the most recent
    # year, before the annual report is out). A full year of segment or
    # regional revenue compared against one quarter's total looks
    # "implausible" even when every number is correct, and the
    # outlier-pruning loop below then deletes real regions to make the
    # sum fit -- a likely cause of a different region going missing on
    # different runs.
    total_revenue_by_year = {}
    for item in structured_data["financial_metrics"]:
        metric_name = str(item.get("metric", "")).lower()
        if "revenue" not in metric_name and "net sales" not in metric_name:
            continue
        if str(item.get("type", "")).lower() != "actual":
            continue
        period = str(item.get("period", "")).lower()
        if not ("fy" in period or "annual" in period or "full year" in period):
            continue
        year = _year_from_item(item)
        value = _value_to_millions(item)
        if year is None or value is None:
            continue
        if year not in total_revenue_by_year or value > total_revenue_by_year[year]:
            total_revenue_by_year[year] = value

    def _is_revenue_row(item):
        metric_name = str(item.get("metric", "")).lower()
        return "revenue" in metric_name or "net sales" in metric_name

    for field, label_key in (("segment_metrics", "segment"), ("geographic_metrics", "region")):

        by_year = {}
        for item in structured_data[field]:
            year = _year_from_item(item)
            by_year.setdefault(year, []).append(item)

        rebuilt = []

        for year, items in by_year.items():
            revenue_items = [x for x in items if _is_revenue_row(x)]
            other_items = [x for x in items if not _is_revenue_row(x)]
            total = total_revenue_by_year.get(year)

            if total is None or len(revenue_items) < 2:
                # Nothing to sanity-check a single figure against, or no
                # verified company total exists for this year -- keep as is.
                rebuilt.extend(items)
                continue

            # If the segments/regions add up to way more than the real
            # total, something is wrong. Remove the biggest value and
            # check again, repeating until the numbers make sense.
            remaining = list(revenue_items)
            tolerance = 1.05

            while len(remaining) > 1 and sum(_value_to_millions(x) or 0 for x in remaining) > total * tolerance:
                largest = max(remaining, key=lambda x: _value_to_millions(x) or 0)
                remaining.remove(largest)
                implausible_removed.append({
                    "field": field,
                    label_key: largest.get(label_key, ""),
                    "metric": largest.get("metric", ""),
                    "value": largest.get("value", ""),
                    "year": year,
                    "reason": (
                        f"Removed as part of an implausible {field} set for {year}: "
                        f"the reported segments/regions summed to well over the "
                        f"verified total company revenue ({total:.1f}M) for that "
                        f"year, most likely because a different table's totals "
                        f"got cross-wired with these labels in the source. This "
                        f"was the largest remaining outlier when the set was "
                        f"checked for consistency with the verified whole."
                    ),
                })

            rebuilt.extend(remaining)
            rebuilt.extend(other_items)

        structured_data[field] = rebuilt

    if implausible_removed:
        removed_metrics.extend(implausible_removed)

    # --------------------------------------------------------
    # Never trust LLM-filled convenience fields. Derive them ONLY from
    # validated metric arrays.
    # --------------------------------------------------------

    structured_data["revenue"] = ""
    structured_data["employees"] = ""
    structured_data["customers"] = ""

    # --------------------------------------------------------
    # Deduplicate financial metrics while preferring primary sources.
    # --------------------------------------------------------

    primary_terms = [
        "annual report", "10-k", "10-q", "investor relations",
        "earnings", "financial results", "garmin announces"
    ]

    def source_priority(item):
        title = str(item.get("source_title", "")).lower()
        url = str(item.get("source_url", "")).lower()
        score = 0
        if any(term in title or term in url for term in primary_terms):
            score += 10
        if "sec.gov" in url or ".gov" in url:
            score += 10
        return score

    deduped = {}
    verification_rank = {"VERIFIED": 3, "PARTIALLY VERIFIED": 2, "DERIVED": 1}

    for item in structured_data["financial_metrics"]:
        key = (
            str(item.get("metric", "")).lower(),
            str(item.get("period", "")).lower(),
            int(item.get("year", 0)),
            str(item.get("unit", "")).lower()
        )
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = item
        else:
            a = (verification_rank.get(item.get("verification"), 0), source_priority(item))
            b = (verification_rank.get(existing.get("verification"), 0), source_priority(existing))
            if a > b:
                deduped[key] = item

    structured_data["financial_metrics"] = list(deduped.values())

    # --------------------------------------------------------
    # Latest five completed annual revenue observations.
    # --------------------------------------------------------

    annual_revenue = []
    for item in structured_data["financial_metrics"]:
        metric = str(item.get("metric", "")).lower()
        period = str(item.get("period", "")).lower()
        item_type = str(item.get("type", "")).lower()

        if "revenue" not in metric and "net sales" not in metric:
            continue
        if item_type != "actual":
            continue
        if not ("fy" in period or "annual" in period or "full year" in period):
            continue

        annual_revenue.append(item)

    annual_revenue.sort(key=lambda x: int(x.get("year", 0)))
    annual_revenue = annual_revenue[-5:]
    structured_data["annual_revenue_history"] = annual_revenue

    if annual_revenue:
        latest = annual_revenue[-1]
        structured_data["revenue"] = f"{latest.get('value')} {latest.get('unit', '')}".strip()

    if structured_data["employee_metrics"]:
        latest_employee = max(
            structured_data["employee_metrics"],
            key=lambda x: (int(x.get("year", 0)), str(x.get("period", "")))
        )
        structured_data["employees"] = f"{latest_employee.get('value')} {latest_employee.get('unit', 'employees')}".strip()

    if structured_data["customer_metrics"]:
        latest_customer = max(
            structured_data["customer_metrics"],
            key=lambda x: (int(x.get("year", 0)), str(x.get("period", "")))
        )
        structured_data["customers"] = f"{latest_customer.get('value')} {latest_customer.get('unit', '')}".strip()

    if removed_metrics:
        structured_data["extraction_audit"].append({
            "status": "REMOVED_UNVERIFIED_NUMBERS",
            "count": len(removed_metrics),
            "examples": removed_metrics[:20]
        })

    structured_data["extraction_audit"].append({
        "status": "FINAL_COUNTS",
        "financial_metrics": len(structured_data["financial_metrics"]),
        "industry_kpis": len(structured_data["industry_kpis"]),
        "annual_revenue_history": len(structured_data["annual_revenue_history"]),
        "employee_metrics": len(structured_data["employee_metrics"]),
        "customer_metrics": len(structured_data["customer_metrics"]),
        "segment_metrics": len(structured_data["segment_metrics"]),
        "geographic_metrics": len(structured_data["geographic_metrics"]),
        "competitor_metrics": len(structured_data["competitor_metrics"])
    })

    return structured_data


# 11B. NUMERIC CLAIM AUDIT
# ============================================================
#
# The report-writing step sometimes states a number that isn't actually
# in structured_data (i.e., it makes it up). This is a safety net: after
# the report text is written, we check every dollar figure and
# percentage against structured_data, and remove any sentence that has
# a number we can't verify.
#
# Growth percentages (like "18% increase") are allowed through without
# a strict check, since they're often a fair calculation from two real
# numbers even if the percentage itself was never stored separately.

# Matches dollar amounts like "$1,234.5 million" or just "$50".
CURRENCY_CLAIM_PATTERN = re.compile(
    r"\$\s?([\d,]+(?:\.\d+)?)\s*(billion|million|thousand)?",
    re.IGNORECASE
)
# Matches percentages like "42%" or "3.5%".
PERCENT_CLAIM_PATTERN = re.compile(r"([\d,]+(?:\.\d+)?)\s*%")

GROWTH_CONTEXT_WORDS = [
    "increase", "growth", "decrease", "decline", "yoy",
    "year-over-year", "year over year", "grew", "fell", "rose", "drop"
]

# Sentences using these words are describing a calculation the prompt
# explicitly permits (see FINANCIAL ANALYSIS rules), not a raw sourced
# figure -- exempt the whole sentence rather than just one number in it.
DERIVED_CONTEXT_WORDS = ["derived", "cagr", "implied", "estimate", "estimated"]


def _audit_parse_number(value):
    text = str(value or "").replace(",", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _flatten_verified_numbers(structured_data):
    """Pulls every number out of structured_data into one list, tagged
    as "percent", "currency_millions", or "count" so we only ever
    compare a dollar figure against other dollar figures, etc."""

    numbers = []

    def add(value, unit):
        num = _audit_parse_number(value)
        if num is None:
            return
        unit_l = str(unit or "").lower()
        if "%" in unit_l:
            numbers.append((num, "percent"))
        elif "billion" in unit_l:
            numbers.append((num * 1000.0, "currency_millions"))
        elif "thousand" in unit_l:
            numbers.append((num / 1000.0, "currency_millions"))
        elif "million" in unit_l or "usd" in unit_l or "$" in unit_l:
            numbers.append((num, "currency_millions"))
        else:
            numbers.append((num, "count"))

    metric_fields = [
        "financial_metrics", "industry_kpis", "market_metrics", "customer_metrics",
        "employee_metrics", "operational_metrics", "segment_metrics",
        "geographic_metrics", "competitor_metrics",
    ]
    for field in metric_fields:
        for item in structured_data.get(field, []) or []:
            if isinstance(item, dict):
                add(item.get("value"), item.get("unit"))

    for item in structured_data.get("annual_revenue_history", []) or []:
        if isinstance(item, dict):
            add(item.get("value"), item.get("unit"))

    return numbers


def _extract_narrative_claims(sentence):
    """Returns (value, kind) pairs for every dollar figure and percentage
    in a sentence, skipping percentages in clear growth/delta framing
    (see GROWTH_CONTEXT_WORDS above)."""

    claims = []
    lower = sentence.lower()

    for match in CURRENCY_CLAIM_PATTERN.finditer(sentence):
        num = _audit_parse_number(match.group(1))
        if num is None:
            continue
        scale = (match.group(2) or "").lower()
        if scale == "billion":
            num *= 1000.0
        elif scale == "thousand":
            num /= 1000.0
        claims.append((num, "currency_millions"))

    if not any(word in lower for word in GROWTH_CONTEXT_WORDS):
        for match in PERCENT_CLAIM_PATTERN.finditer(sentence):
            num = _audit_parse_number(match.group(1))
            if num is not None:
                claims.append((num, "percent"))

    return claims


def audit_narrative_numbers(final_report, structured_data):
    """Drops any sentence in final_report whose dollar figures or
    percentages cannot be matched against structured_data. Returns
    (cleaned_report, removed_claims) -- removed_claims is printed to the
    console so a dropped claim is visible, not silently lost."""

    verified = _flatten_verified_numbers(structured_data)
    pool_by_kind = {"currency_millions": [], "percent": [], "count": []}
    for value, kind in verified:
        pool_by_kind[kind].append(value)

    def is_backed(value, kind):
        pool = pool_by_kind.get(kind, [])
        if not pool:
            return False
        tolerance = max(abs(value) * 0.02, 0.5) if kind == "percent" else max(abs(value) * 0.02, 5.0)
        return any(abs(value - candidate) <= tolerance for candidate in pool)

    removed_claims = []
    cleaned_lines = []

    for raw_line in final_report.splitlines():
        stripped = raw_line.strip()

        # Headings, table rows, and blank lines pass through untouched --
        # markdown tables are already handled separately by
        # report_generator.py, and headings never carry a fabricated
        # figure worth auditing.
        if not stripped or stripped.startswith("#") or re.match(r"^\|.*\|$", stripped):
            cleaned_lines.append(raw_line)
            continue

        if any(word in stripped.lower() for word in DERIVED_CONTEXT_WORDS):
            cleaned_lines.append(raw_line)
            continue

        prefix = ""
        content = stripped
        # If the line starts with "- " or "1. " (a bullet or numbered
        # list item), remember that prefix and check just the text after it.
        bullet_match = re.match(r"^(-\s+|\d+\.\s+)(.*)", stripped)
        if bullet_match:
            prefix = bullet_match.group(1)
            content = bullet_match.group(2)

        # Split the line into separate sentences (breaking after each
        # ".", "!", or "?"), so we can check and drop just the bad
        # sentence instead of the whole paragraph.
        sentences = re.split(r"(?<=[.!?])\s+", content)
        kept_sentences = []

        for sentence in sentences:
            if not sentence.strip():
                continue
            claims = _extract_narrative_claims(sentence)
            if not claims or all(is_backed(v, k) for v, k in claims):
                kept_sentences.append(sentence)
            else:
                removed_claims.append(sentence.strip())

        if kept_sentences:
            cleaned_lines.append(prefix + " ".join(kept_sentences))
        # If every sentence on this line got dropped, the whole line is
        # omitted rather than left as an empty bullet/paragraph.

    return "\n".join(cleaned_lines), removed_claims


# 11C. STRATEGIC EVALUATION SCORES (for the Executive Brief)
# ============================================================
#
# Unlike a dollar figure, a "Growth Potential: 8/10" score has no real
# number in a source to check it against -- it's the model's own
# judgment call. So this is handled differently from everything else in
# the pipeline:
#   - It only ever sees structured_data (already-verified facts), never
#     raw source text, so it can't invent a NEW fact while scoring.
#   - Every score MUST come with a one-sentence justification pointing
#     at a specific fact already in structured_data.
#   - Anything malformed (a score outside 1-10, a missing or empty
#     justification) is dropped rather than guessed at or defaulted.
#   - The docx rendering (in report_generator.py) labels this section
#     "AI Analysis" explicitly, never presenting it as a verified fact.

STRATEGIC_SCORE_CATEGORIES = [
    "strategic_position",
    "growth_potential",
    "product_market_strength",
    "ability_to_disrupt",
    "market_traction",
    "financial_strength",
    "competitive_position",
]


def generate_strategic_scores(company_name, structured_data):

    if not structured_data:
        # No verified data exists to score against at all -- don't even
        # ask the model, since we've seen it invent plausible-sounding
        # generic scores rather than reliably self-omitting every
        # category when told the data is "too thin."
        return {}

    # Give the model only the facts, not a wall of raw source text --
    # this is a judgment call about what's already verified, not a new
    # extraction task.
    facts_text = json.dumps(structured_data, indent=2, ensure_ascii=False)

    prompt = f"""
You are a strategy analyst producing a transparent, evidence-based
evaluation of {company_name} for an executive summary.

VERIFIED RESEARCH DATA (this is the ONLY information you may use):
{facts_text}

Score {company_name} from 1 (very weak) to 10 (very strong) on each of
these dimensions:

- strategic_position: overall competitive and market standing
- growth_potential: room to grow revenue/market share going forward
- product_market_strength: how well its products fit customer needs
- ability_to_disrupt: potential to change or lead its industry
- market_traction: current momentum -- adoption, revenue growth, demand
- financial_strength: balance sheet health, profitability, cash generation
- competitive_position: standing versus named competitors

RULES:
1. Base every score ONLY on the verified data above. If the data is too
   thin to responsibly score a category, OMIT that category entirely --
   do not guess a middle-of-the-road score to fill it in.
2. Every score you DO give must come with a one-sentence justification
   that names a specific fact from the data above (a number, a named
   competitor, a segment, a strength/risk already listed).
3. This is your professional judgment, not a verified fact. Do not
   invent statistics or facts beyond what is given above.

Return ONLY valid JSON in this exact shape, with only the categories you
can responsibly score:
{{
    "strategic_position": {{"score": 7, "justification": "..."}},
    "growth_potential": {{"score": 8, "justification": "..."}}
}}
"""

    response = llm.invoke(prompt)
    raw = parse_json_response(response)

    if not isinstance(raw, dict):
        return {}

    validated = {}
    for category in STRATEGIC_SCORE_CATEGORIES:
        entry = raw.get(category)
        if not isinstance(entry, dict):
            continue
        score = entry.get("score")
        justification = str(entry.get("justification", "")).strip()
        try:
            score = int(score)
        except (TypeError, ValueError):
            continue
        if not (1 <= score <= 10):
            continue
        if not justification:
            continue
        validated[category] = {"score": score, "justification": justification}

    return validated


# 12. FINAL MARKET RESEARCH REPORT
# ============================================================

def generate_final_report(
    question,
    accepted_sources,
    verification_report,
    structured_data
):

    if not accepted_sources:
        return """
# Executive Summary

No reliable research sources were available to generate the final market research report.
"""

    sources_text = ""
    for index, source in enumerate(accepted_sources):
        sources_text += f"""
==================================================
SOURCE {index + 1}
==================================================
TITLE:
{source['title']}
URL:
{source['url']}
SOURCE SCORE:
{source['score']}/100
SUMMARY:
{source['summary']}
SOURCE CONTENT:
{source['content']}
--------------------------------------------------
"""

    structured_data_text = json.dumps(structured_data, indent=4, ensure_ascii=False)

    prompt = f"""
You are an expert market research strategist, financial analyst,
competitive intelligence analyst and professional report writer.

Create a professional evidence-based report using ONLY the supplied
sources, verification report and structured data.

RESEARCH QUESTION:
{question}

VERIFICATION REPORT:
{verification_report}

STRUCTURED DATA:
{structured_data_text}

SOURCES:
{sources_text}

REPORT STRUCTURE:
# Executive Summary
# 1. Company Overview
## Background
## History
## Core Business
## Location
## Value Proposition
# 2. Financial Performance
# 3. Products and Services
# 4. Target Customers
# 5. Business Model
# 6. Competitive Landscape
# 7. AI Strategy
# 8. Recent Developments
# 9. Strengths
# 10. Risks
# 11. Opportunities
# 12. Conclusion
# Sources

==================================================
DATA DISCIPLINE
==================================================

1. Use the latest completed annual actual for the headline annual revenue.
2. Keep quarterly revenue separate from annual revenue.
3. Keep company guidance and forecasts separate from historical actuals.
4. If annual_revenue_history contains five observations, discuss the five-
   year revenue trajectory and use the five-year chart in the visual layer.
5. Do not substitute an old five-year series when a newer five-year series
   exists in structured data.
6. Use segment metrics when verified.
7. Use geographic metrics when verified.
8. Use employee/customer metrics only when verified.
9. Use competitor numbers only when directly supported.
10. Never invent market share or competitor scores.
11. If a claim is unsupported, say "Not available from the accepted sources."
12. If sources conflict, describe the conflict instead of silently choosing.
13. Do not call a guidance number historical revenue.
14. Do not turn a market-share percentage into a customer count.
15. Do not turn a date into an employee count.
16. Under "# 2. Financial Performance", write 2-4 sentences of narrative
    analysis of revenue, margin and profitability trends only -- do not
    attempt to render a financial table yourself. A verified Key
    Financials table is inserted automatically immediately under that
    heading by the document generator, built directly from
    structured_data["financial_metrics"].

==================================================
DEPTH AND DETAIL
==================================================

Every major section (Executive Summary, Company Overview's subsections,
Financial Performance, Products and Services, Target Customers, Business
Model, Competitive Landscape, AI Strategy, Recent Developments,
Conclusion) must contain at least 4-6 substantive sentences drawn from
the specific facts, numbers, and context available in the sources and
structured data -- not one or two generic sentences. Use the actual
detail present in the source summaries and content (specific products,
dates, figures, named partners, named competitors, direct quotes from
executives when present) rather than restating the section heading in
different words.

For list-style sections (Products and Services, Target Customers,
Competitive Landscape), where the sources support it, add a short
clause after each bullet explaining what it is or why it matters,
rather than a bare product or company name on its own line.

Under "# 2. Financial Performance" specifically: discuss every metric
present in structured_data["financial_metrics"] with context -- not just
the number, but what it indicates (margin trend, profitability,
cash generation, capital allocation) and, where a prior-period verified
figure exists for the same metric, how it changed.

This depth requirement does not relax any rule above: every added
sentence must still be grounded in the supplied sources and structured
data, and every number must still be one that genuinely appears there.
Write more only where there is more real, sourced substance to draw
on -- do not pad with restated numbers, filler adjectives, or
unsupported claims to reach a length target, and do not state that a
metric is unavailable unless you have actually checked structured_data
and confirmed it is absent.

==================================================
MARKET RESEARCH DEPTH
==================================================

Under "# 6. Competitive Landscape", this report should read as genuine
market research, not only a company profile. Where the sources support
it, cover:
- Market size and historical growth (using structured_data["market_metrics"])
- Market growth forecast or CAGR, if a source states one
- Market drivers and trends (what is pushing the market up or down)
- Customer or buyer trends relevant to this market
- Regional or geographic opportunities, if reported

Each of these is optional -- only include what the sources actually
support. If a source-backed number exists in market_metrics, use it and
cite it in prose the same way other verified numbers are used. Do not
estimate a market size, growth rate, or CAGR that is not explicitly
stated in a source.

==================================================
FINANCIAL ANALYSIS
==================================================

When available, discuss revenue, gross profit/margin, operating income/margin,
net income, EPS, cash flow, segment performance and latest quarterly results.
If a five-year revenue series exists, identify the direction of the trend and
may calculate a CAGR only as a clearly labelled derived calculation from the
verified endpoints.

Return ONLY the report.
"""

    response = llm.invoke(prompt)
    return response.content.strip()



# ============================================================
# 13. CREATE AI RESEARCH AGENT
# ============================================================

# Computed once here -- rather than hardcoded -- so the agent's own sense
# of "today" never goes stale. Reused again in section 16 so the system
# prompt and the per-run research requests always agree on the same date.
CURRENT_DATE = date.today().isoformat()
CURRENT_DATE_HUMAN = date.today().strftime("%B %Y")

SYSTEM_PROMPT = f"""
You are a professional market research strategist, financial researcher,
competitive intelligence analyst and evidence-collection agent.

The current date is {CURRENT_DATE_HUMAN} ({CURRENT_DATE}). Research must
prioritize the newest reliable information available, while preserving
historical data when it is specifically needed.

==================================================
CORE RULE
==================================================

Do not perform a shallow company overview. Collect source material that can
support a professional report AND numerical charts.

You MUST use the web search tool repeatedly and deliberately. Perform
multiple focused searches rather than one broad search.

At minimum, perform separate searches for:
1. latest annual report / annual results
2. five-year annual revenue and financial history
3. latest quarterly results
4. segment performance
5. geographic performance
6. employees / customers
7. market size / market share where relevant
8. AI / technology strategy
9. recent developments
10. competitors and competitor metrics where available

==================================================
PRIMARY SOURCE PRIORITY
==================================================

For company financial data prefer:
1. official investor relations
2. annual reports
3. regulatory filings
4. official quarterly earnings releases
5. official newsroom
6. government/regulator sources
7. reputable financial publications
8. reputable industry sources

A current primary source should outrank an older secondary source when both
cover the same metric.

==================================================
FIVE-YEAR REVENUE — MANDATORY
==================================================

Find the newest reliable annual report or annual financial release that
contains historical revenue.

Extract the latest five COMPLETED fiscal years available.

If the latest annual report contains FY2021-FY2025, collect all five.
Do not stop at FY2023.
Do not substitute a 2019-2023 series when 2021-2025 is available.

Search queries should explicitly include phrases such as:
"[company] 2025 annual report revenue 2021 2022 2023 2024 2025"
"[company] five year financial highlights revenue"
"[company] 2025 annual results revenue operating income"

==================================================
LATEST FINANCIALS
==================================================

Search for:
- latest annual revenue
- latest quarter revenue
- prior-year comparable quarter
- gross profit/margin
- operating income/margin
- net income
- EPS
- operating cash flow
- free cash flow
- capital expenditure (capex)
- cash and cash equivalents, total debt, net debt
- company guidance

Keep actuals, guidance and forecasts separate.

==================================================
SEGMENTS
==================================================

Find directly reported segment revenue, YoY growth, operating income/loss
and margins. Preserve the exact period.

==================================================
GEOGRAPHY
==================================================

Find directly reported geographic revenue and growth. Never calculate
regional revenue from percentages when the source does not provide the
number.

==================================================
EMPLOYEES / CUSTOMERS
==================================================

Find explicit workforce and customer/subscriber/user metrics. Preserve the
date or period attached to each metric. Companies describe their own
workforce with different words -- employees, associates, staff, team
members, personnel -- and their customer base with different words --
customers, users, subscribers, clients, members, installed base. Search for
and capture whichever term the company itself uses rather than assuming a
company that avoids the word "employees" has no headcount data available.

==================================================
MARKET / COMPETITORS
==================================================

Find market size, CAGR, market share and category growth when relevant.
For competitors, find numerical metrics only when reliably reported.
Otherwise provide qualitative evidence.

==================================================
AI / TECHNOLOGY
==================================================

Research confirmed AI products, AI capabilities, partnerships, generative AI,
personalization and operational AI. Separate current deployments from plans.

==================================================
RECENT DEVELOPMENTS
==================================================

Find recent launches, acquisitions, partnerships, earnings milestones and
strategic announcements, prioritizing official announcements.

==================================================
ANTI-HALLUCINATION
==================================================

Do not invent numbers, dates, market shares, employee counts or competitor
scores. Return source URLs through the search tool. The downstream pipeline
will verify and audit the extracted data.
"""

agent = create_agent(
    model=llm,
    tools=[web_search],
    system_prompt=SYSTEM_PROMPT
)


# 14. GET USER RESEARCH QUESTION
# ============================================================

question = input(
    "\nWhat would you like to research? "
).strip()


# ============================================================
# 15. START RESEARCH
# ============================================================

print("\n")
print("=" * 70)
print("STARTING AI MARKET RESEARCH")
print("=" * 70)


# ============================================================
# 16. RUN AI RESEARCH AGENT
# ============================================================

current_date = CURRENT_DATE  # same value SYSTEM_PROMPT was built with above

broad_research_request = f"""
Research this subject comprehensively: {question}

Current date: {current_date}.

Perform the broad research pass now. Use multiple web searches and collect
source material for company overview, products, customers, business model,
competition, AI, recent developments and financial/market analysis.
Do not stop after the first search.
"""

financial_research_request = f"""
Perform a SECOND INDEPENDENT RESEARCH PASS for: {question}

Current date: {current_date}.

This pass is specifically for DATA VERIFICATION and must search for primary
sources. Do not rely on the previous search results.

Search separately for:
1. latest annual report / latest full-year results
2. latest annual-report FINANCIAL HIGHLIGHTS / five-year revenue table
3. five-year annual revenue history from the newest primary source
4. latest quarterly results
5. segment revenue and YoY growth
6. geographic revenue and YoY growth
7. employee and customer metrics
8. market share / market size where relevant
9. latest AI strategy and recent developments

For the annual report, search explicitly for the phrase "financial highlights"
and extract the five-year table when it exists. Do not rely only on the income
statement, which may show only three years.

For a company, prioritize the newest annual report and latest quarterly
release. If a 2025 annual report exists, search for it explicitly. If 2026
quarterly results exist, search for the latest available quarter.

The goal is to prevent stale 2023 data from being used when 2025/2026 data is
available.
"""

print("\nRESEARCH PASS 1: BROAD RESEARCH")
result_broad = agent.invoke(
    {
        "messages": [
            {"role": "user", "content": broad_research_request}
        ]
    }
)

print("\nRESEARCH PASS 2: CURRENT FINANCIAL + DATA VERIFICATION")
result_financial = agent.invoke(
    {
        "messages": [
            {"role": "user", "content": financial_research_request}
        ]
    }
)

research_results = [result_broad, result_financial]


# 17. STORAGE
# ============================================================

accepted_sources = []

rejected_sources = []


# ============================================================
# 18. EXTRACT WEB SEARCH RESULTS
# ============================================================

# The full page text can be huge, so we only use the first 6000
# characters of it -- enough detail without making prompts too big.
MAX_RAW_CONTENT_CHARS = 6000

for research_result in research_results:

    for message in research_result["messages"]:

        if not isinstance(
            message,
            ToolMessage
        ):
            continue


        # --------------------------------------------------------
        # Parse tool response
        # --------------------------------------------------------

        try:

            tool_data = json.loads(
                message.content
            )

        except (
            json.JSONDecodeError,
            TypeError
        ):

            continue


        # --------------------------------------------------------
        # Determine search result structure
        # --------------------------------------------------------

        if isinstance(
            tool_data,
            list
        ):

            search_results = tool_data

        elif isinstance(
            tool_data,
            dict
        ):

            search_results = tool_data.get(
                "results",
                tool_data.get(
                    "items",
                    []
                )
            )

        else:

            continue


        # --------------------------------------------------------
        # Process each source
        # --------------------------------------------------------

        for source in search_results:

            title = source.get(
                "title",
                "Untitled Source"
            )

            url = source.get(
                "url",
                ""
            )

            content = source.get(
                "content",
                source.get(
                    "snippet",
                    ""
                )
            )

            raw_content = source.get("raw_content") or ""
            if raw_content:
                # Full page text takes priority over the short snippet
                # when Tavily provides it, capped to keep prompts bounded.
                content = raw_content[:MAX_RAW_CONTENT_CHARS]


            # ----------------------------------------------------
            # Ignore empty sources
            # ----------------------------------------------------

            if not content:
                continue


            # ====================================================
            # DUPLICATE CHECK
            # ====================================================

            existing_urls = {
                item["url"]
                for item in accepted_sources
            }

            existing_rejected_urls = {
                item["url"]
                for item in rejected_sources
            }


            if url and (
                url in existing_urls
                or url in existing_rejected_urls
            ):

                continue


            # ====================================================
            # SOURCE FOUND
            # ====================================================

            print("\n")
            print("-" * 70)
            print("SOURCE FOUND")
            print("-" * 70)

            print(
                f"Title: {title}"
            )

            print(
                f"URL: {url}"
            )


            # ====================================================
            # SOURCE EVALUATION
            # ====================================================

            print("\nSOURCE EVALUATION:")

            evaluation = evaluate_source(
                title,
                content,
                question
            )

            print(evaluation)


            # ====================================================
            # SOURCE FILTERING
            # ====================================================

            if not filter_source(
                evaluation
            ):

                print(
                    "\nSTATUS: REJECTED"
                )

                rejected_sources.append(
                    {
                        "title": title,
                        "url": url,
                        "evaluation": evaluation
                    }
                )

                continue


            print(
                "\nSTATUS: ACCEPTED"
            )


            # ====================================================
            # SOURCE RANKING
            # ====================================================

            print(
                "\nSOURCE RANKING:"
            )

            ranking = rank_source(
                title,
                content,
                evaluation,
                question
            )

            print(ranking)


            # ====================================================
            # EXTRACT SCORE
            # ====================================================

            score = extract_score(
                ranking
            )

            print(
                f"\nFINAL SCORE: {score}/100"
            )


            # ====================================================
            # SOURCE SUMMARY
            # ====================================================

            print(
                "\nSOURCE SUMMARY:"
            )

            summary = summarize_source(
                title,
                content
            )

            print(summary)


            # ====================================================
            # STORE ACCEPTED SOURCE
            # ====================================================

            accepted_sources.append(
                {
                    "title": title,
                    "url": url,
                    "content": content,
                    "evaluation": evaluation,
                    "ranking": ranking,
                    "score": score,
                    "summary": summary
                }
            )


    # ============================================================
# 19. SORT ACCEPTED SOURCES
# ============================================================

accepted_sources.sort(
    key=lambda source: source["score"],
    reverse=True
)


# ============================================================
# 20. FINAL SOURCE RANKING
# ============================================================

print("\n\n")
print("=" * 70)
print("FINAL SOURCE RANKING")
print("=" * 70)


if not accepted_sources:

    print(
        "\nNo accepted sources found."
    )

else:

    for index, source in enumerate(
        accepted_sources,
        start=1
    ):

        print(
            f"\n{index}. {source['title']}"
        )

        print(
            f"   Score: {source['score']}/100"
        )

        print(
            f"   URL: {source['url']}"
        )


# ============================================================
# 21. REJECTED SOURCES
# ============================================================

print("\n\n")
print("=" * 70)
print("REJECTED SOURCES")
print("=" * 70)


if not rejected_sources:

    print(
        "\nNo sources were rejected."
    )

else:

    for index, source in enumerate(
        rejected_sources,
        start=1
    ):

        print(
            f"\n{index}. {source['title']}"
        )

        print(
            f"URL: {source['url']}"
        )

        print(
            f"Evaluation:\n{source['evaluation']}"
        )


# ============================================================
# 22. SOURCE VERIFICATION
# ============================================================

print("\n\n")
print("=" * 70)
print("SOURCE VERIFICATION")
print("=" * 70)


verification_report = verify_sources(
    question,
    accepted_sources
)


print("\n")
print(
    verification_report
)


# ============================================================
# 23. STRUCTURED DATA EXTRACTION
# ============================================================

print("\n\n")
print("=" * 70)
print("STRUCTURED DATA EXTRACTION")
print("=" * 70)


structured_data = extract_structured_data(
    question,
    accepted_sources,
    verification_report
)


print("\n")

print(
    json.dumps(
        structured_data,
        indent=4,
        ensure_ascii=False
    )
)

print("\nEXTRACTION AUDIT:")
for audit_item in structured_data.get("extraction_audit", []):
    print(json.dumps(audit_item, ensure_ascii=False))

print("\nSTRUCTURED DATA METRIC SUMMARY:")

for metric_field in [
    "financial_metrics",
    "industry_kpis",
    "market_metrics",
    "customer_metrics",
    "employee_metrics",
    "operational_metrics",
    "segment_metrics",
    "geographic_metrics",
    "competitor_metrics"
]:
    count = len(
        structured_data.get(metric_field, [])
    )

    print(
        f"  {metric_field}: {count}"
    )


# ============================================================
# 24. INFOGRAPHIC GENERATION
# ============================================================

print("\n\n")
print("=" * 70)
print("INFOGRAPHIC GENERATION")
print("=" * 70)


if structured_data:

    try:

        infographic_path = (
            generate_company_snapshot(
                structured_data
            )
        )

        print(
            "\nCompany snapshot infographic generated:"
        )

        print(
            f"✓ {infographic_path}"
        )

    except Exception as error:

        infographic_path = None

        print(
            "\nWARNING: Infographic generation failed."
        )

        print(
            f"Error: {error}"
        )

else:

    infographic_path = None

    print(
        "\nInfographic skipped because structured "
        "data is empty."
    )


# ============================================================
# 25. CHART / GRAPH GENERATION
# ============================================================

print("\n\n")
print("=" * 70)
print("CHART / GRAPH GENERATION")
print("=" * 70)


if structured_data:

    try:

        charts_map = generate_all_charts(
            structured_data
        )


        if charts_map:

            print(
                "\nCharts generated:"
            )

            for chart_key, chart_path in charts_map.items():

                print(
                    f"✓ {chart_key}: {chart_path}"
                )

        else:

            print(
                "\nNo charts generated."
            )

            print(
                "Reason: insufficient verified "
                "numerical data was available."
            )

    except Exception as error:

        charts_map = {}

        print(
            "\nWARNING: Chart generation failed."
        )

        print(
            f"Error: {error}"
        )

else:

    charts_map = {}

    print(
        "\nChart generation skipped because "
        "structured data is empty."
    )


# ============================================================
# 26. FINAL MARKET RESEARCH REPORT
# ============================================================

print("\n\n")
print("=" * 70)
print("FINAL MARKET RESEARCH REPORT")
print("=" * 70)


final_report = generate_final_report(
    question,
    accepted_sources,
    verification_report,
    structured_data
)


print("\n")

print(
    final_report
)

# ============================================================
# 26B. NUMERIC CLAIM AUDIT
# ============================================================

print("\n\n")
print("=" * 70)
print("NUMERIC CLAIM AUDIT")
print("=" * 70)

final_report, removed_claims = audit_narrative_numbers(
    final_report,
    structured_data
)

if removed_claims:

    print(
        f"\nRemoved {len(removed_claims)} sentence(s) containing a "
        "number that could not be matched to structured_data:"
    )

    for claim in removed_claims:
        print(f"  ✗ {claim}")

else:

    print(
        "\nNo unbacked numeric claims found in the narrative."
    )

# ============================================================
# 26C. STRATEGIC EVALUATION SCORES
# ============================================================

print("\n\n")
print("=" * 70)
print("STRATEGIC EVALUATION SCORES")
print("=" * 70)

company_name = structured_data.get(
    "company_name",
    "Market Research"
)

try:

    strategic_scores = generate_strategic_scores(
        company_name,
        structured_data
    )

    if strategic_scores:

        print("\nScores generated (AI analysis, not verified facts):")

        for category, entry in strategic_scores.items():
            print(f"  {category}: {entry['score']}/10 -- {entry['justification']}")

    else:

        print(
            "\nNo strategic scores generated -- verified data was too "
            "thin to responsibly score any category."
        )

except Exception as error:

    strategic_scores = {}

    print(
        "\nWARNING: Strategic scoring failed."
    )

    print(
        f"Error: {error}"
    )

# ============================================================
# 27. DOCX REPORT GENERATION
# ============================================================

print("\n\n")
print("=" * 70)
print("DOCX REPORT GENERATION")
print("=" * 70)


try:

    docx_path = generate_docx_report(
        company_name=company_name,
        final_report=final_report,
        structured_data=structured_data,
        infographic_path=infographic_path,
        charts=charts_map,
        accepted_sources=accepted_sources,
        include_sources=True,
        strategic_scores=strategic_scores
    )

    print(
        "\nDOCX report generated:"
    )

    print(
        f"✓ {docx_path}"
    )


except Exception as error:

    docx_path = None

    print(
        "\nWARNING: DOCX generation failed."
    )

    print(
        f"Error: {error}"
    )

# ============================================================
# 28. PIPELINE STATUS
# ============================================================

print("\n\n")
print("=" * 70)
print("RESEARCH PIPELINE COMPLETED")
print("=" * 70)

print("\nCompleted stages:")

print("✓ AI Research Agent")
print("✓ Web Search")
print("✓ Source Evaluation")
print("✓ Source Filtering")
print("✓ Source Ranking")
print("✓ Source Summarization")
print("✓ Source Verification")
print("✓ Structured Data Extraction")
print("✓ Infographic Generation")
print("✓ Chart / Graph Generation")
print("✓ Final Market Research Report")
print("✓ DOCX Report Generation")

print("\nUpcoming stages:")

print("→ PDF Report")

print("\n")