from langchain_tavily import TavilySearch
from langchain_core.tools import tool
from dotenv import load_dotenv

load_dotenv()

# The underlying Tavily tool. include_raw_content=True asks for the
# cleaned/parsed page text instead of a short AI-condensed snippet --
# necessary because several research runs showed real, well-established
# figures (FY2025 annual revenue, quarterly operating income) failing
# verification simply because the snippet-only content never contained
# the number near its label, especially on PDF sources like annual
# reports.
_tavily_search = TavilySearch(
    max_results=4,
    topic="general",
    include_answer=False,
    include_raw_content=True
)

# Most search results get a tight cap to keep the agent's own context
# bounded (see the note above the rate-limit incident this fixed). But a
# genuine pattern showed up across several runs: percentage figures
# stated in an early "highlights" paragraph (e.g. gross margin) reliably
# verified, while dollar figures sitting in the actual income-statement
# table deeper in the same annual-report PDF (e.g. operating income)
# never did -- because the table simply falls outside a 1,500-character
# window from the start of the page. Primary filings are also the
# minority of results per search (typically 0-2 out of 4), so giving
# just those extra room doesn't reintroduce the original rate-limit risk
# the way raising the cap for every result would.
MAX_RAW_CONTENT_CHARS_PER_RESULT = 1500
MAX_RAW_CONTENT_CHARS_PRIMARY = 6000

PRIMARY_SOURCE_MARKERS = [
    "annual report", "10-k", "10-q", "8-k", "form 10", "sec.gov",
    "investor relations", "investor overview", "investor presentation",
    "financial highlights",
]

# URL path fragments that show up on a company's own investor-relations
# site regardless of which company it is (e.g. "investors.garmin.com",
# "ir.something.com", ".../invRelations/..."). A single hardcoded domain
# like "investors.garmin.com" only ever matches one company and silently
# fails to recognize the equivalent official IR page for anyone else this
# pipeline researches.
PRIMARY_SOURCE_URL_MARKERS = [
    "invrelations", "investor-relations", "investorrelations", "ir.",
]

# Anchors that mark where the actual numbers live in a long financial
# filing. A full annual report or 10-K is often 50-100+ pages -- a
# shareholder letter, MD&A, and risk factors all come before the actual
# income statement -- so even a generous prefix-based cap can land
# entirely in front matter and never reach the table it was meant to
# capture. Searching for one of these in the FULL raw text and centering
# the truncation window there reaches the relevant section on a normal
# budget, instead of needing an ever-larger blind prefix (which is what
# caused the earlier rate-limit crash).
FINANCIAL_STATEMENT_ANCHORS = [
    "consolidated statements of income",
    "consolidated statements of operations",
    "consolidated income statement",
    "condensed consolidated statements of income",
    "operating income",
    "results of operations",
    "financial highlights",
]


def _is_primary_source(item):
    title = str(item.get("title", "")).lower()
    url = str(item.get("url", "")).lower()
    if any(marker in title or marker in url for marker in PRIMARY_SOURCE_MARKERS):
        return True
    return any(marker in url for marker in PRIMARY_SOURCE_URL_MARKERS)


def _smart_truncate(raw_content, cap):
    """Prefer a window centered on a financial-statement anchor over a
    blind prefix cut, when the content is long enough that a prefix
    wouldn't reach it anyway."""

    if len(raw_content) <= cap:
        return raw_content

    lower = raw_content.lower()
    best_position = None
    for anchor in FINANCIAL_STATEMENT_ANCHORS:
        position = lower.find(anchor)
        if position != -1 and (best_position is None or position < best_position):
            best_position = position

    if best_position is None:
        return raw_content[:cap]

    # Keep a little context before the anchor (labels/period headers
    # commonly sit just above the numbers) and spend the rest of the
    # budget after it.
    lead_in = int(cap * 0.15)
    start = max(0, best_position - lead_in)
    return raw_content[start:start + cap]


@tool
def web_search(query: str) -> dict:
    """Search the web for a query. Returns a small set of results, each
    with a title, url, a short content snippet, and (length-capped) raw
    page content when Tavily was able to extract it. Primary filings
    (annual reports, 10-K/10-Q/8-K, official investor relations pages)
    get a larger content allowance than other results, since the figures
    they contain often sit deeper in the page than a short cap can reach."""

    try:
        results = _tavily_search.invoke({"query": query})
    except Exception as error:
        # A Tavily failure (invalid/expired TAVILY_API_KEY, quota
        # exhausted, a transient network error) must never propagate as
        # a raw exception out of this tool. Depending on how the agent
        # framework converts a failed tool call into a ToolMessage, an
        # uncaught exception here can produce message content that isn't
        # valid JSON -- and research_agent.py's
        # `json.loads(message.content)` silently swallows any parse
        # failure with a bare `except: continue`, so the whole run comes
        # back reporting "no sources found" with no visible error
        # anywhere. Printing the real error here (where it's actually
        # available) surfaces the true cause immediately, and returning
        # a well-formed empty-results dict keeps the downstream JSON
        # parsing working instead of failing silently.
        print(f"\n[web_search] Tavily search failed for query '{query}': {error}")
        return {"query": query, "results": [], "error": str(error)}

    # TavilySearch doesn't always raise on a failed request -- an
    # account-level error (e.g. "Error 432: usage limit exceeded") comes
    # back as a normal return value shaped like {"error": ValueError(...)}
    # rather than as a raised exception, so the try/except above never
    # sees it. Left alone, that dict's "error" value is itself an
    # exception OBJECT, which isn't JSON-serializable -- when the agent
    # framework tries to turn this return value into ToolMessage text, it
    # falls back to a Python repr string (single-quoted, not valid JSON),
    # which then fails research_agent.py's json.loads for every single
    # search this happens to, with the real reason buried in a parse
    # error rather than shown plainly. Detect this shape explicitly and
    # handle it the same way as a raised exception.
    if isinstance(results, dict) and "error" in results and "results" not in results:
        error_text = str(results["error"])
        print(f"\n[web_search] Tavily returned an error for query '{query}': {error_text}")
        return {"query": query, "results": [], "error": error_text}

    if isinstance(results, dict):
        for item in results.get("results", []) or []:
            raw = item.get("raw_content")
            if raw:
                cap = MAX_RAW_CONTENT_CHARS_PRIMARY if _is_primary_source(item) else MAX_RAW_CONTENT_CHARS_PER_RESULT
                item["raw_content"] = _smart_truncate(raw, cap)

    return results