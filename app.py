"""
app.py — The Curve: Economic Intelligence Platform
--------------------------------------------------
A single-file Flask backend that powers four modules:

  • AI Tutor   → direct REST call to the Google Gemini API (no SDK dependency)
  • Markets    → World Bank Open Data (fetched client-side, no key needed)
  • Econ Lab   → pure client-side IS-LM / Phillips-curve toy model
  • News       → GNews macro headlines + a lightweight sentiment tagger,
                 with a cache shield and a mock-data fallback so the page
                 NEVER shows an empty/broken feed.

Design goals for this rebuild:
  1. Nothing crashes in front of a live audience — every external call is
     wrapped and degrades gracefully.
  2. One source of truth for the macro numbers (see MACRO below) so the
     dashboard can never contradict itself.
  3. No paid APIs. Gemini free tier + World Bank (free) + GNews free tier.
"""

import os
import time
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from werkzeug.exceptions import HTTPException
from dotenv import load_dotenv

# --- Load environment variables from .env (next to this file) ---------------
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


def _masked(value: str) -> str:
    """Show only that a secret is present — never print the secret (or any part)."""
    return "set" if value else "MISSING"


# ============================================================
#  APP INITIALIZATION
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-secret-change-me")
# Reject absurdly large request bodies outright (defensive; chat/news are tiny).
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024  # 256 KB

# Bounds for a single chat turn, so one request can't balloon the Gemini call.
MAX_MESSAGE_CHARS = 4000
MAX_HISTORY_TURNS = 20

# ============================================================
#  CONFIGURATION
# ============================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY")

# Stable, current, free-tier Gemini model. Overridable via .env if needed.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Only 2.5 / 3.x models understand thinkingConfig; disabling "thinking"
# guarantees the whole token budget goes to the visible answer (no truncation).
_SUPPORTS_THINKING = any(tag in GEMINI_MODEL for tag in ("2.5", "-3", "3.", "3-"))

print("=" * 60)
print("  THE CURVE — boot sequence")
print(f"  Gemini key : {_masked(GEMINI_API_KEY)}")
print(f"  GNews key  : {_masked(GNEWS_API_KEY)}")
print(f"  Model      : {GEMINI_MODEL}")
print("=" * 60)

# ============================================================
#  SINGLE SOURCE OF TRUTH — India macro snapshot
#  Every template reads these via the context processor below, so the
#  dashboard, the sidebar and the Econ Lab baseline can never disagree.
#  Figures are illustrative, rounded, and roughly aligned to 2025–26 India.
# ============================================================
# Student identity shown in the site header and footer.
STUDENT = {
    "name": "Ved Agarwal",
    "department": "Economics",
    "roll": "0279",
}

MACRO = {
    "repo_rate": 5.50,       # RBI policy repo rate (%)
    "cpi_inflation": 3.10,   # CPI inflation, YoY (%)
    "gdp_growth": 6.50,      # Real GDP growth (%)
    "unemployment": 7.80,    # Unemployment rate, CMIE (%)
    "repo_stance": "Neutral",
    "fy_label": "FY26",
    "world_gdp_tn": 115.5,   # World nominal GDP (USD trillion, IMF est.)
}

# Global policy rates for the dashboard sidebar (illustrative, ~2025–26).
CENTRAL_BANK_RATES = [
    {"name": "RBI (India)",     "short": "RBI", "rate": MACRO["repo_rate"], "accent": "sky"},
    {"name": "US Fed",          "short": "FED", "rate": 4.50,               "accent": "emerald"},
    {"name": "ECB (Euro)",      "short": "ECB", "rate": 2.50,               "accent": "slate"},
    {"name": "Bank of England", "short": "BOE", "rate": 4.25,               "accent": "amber"},
    {"name": "Bank of Japan",   "short": "BOJ", "rate": 0.50,               "accent": "slate"},
]

# GDP-growth mini tracker for the sidebar. Bar `width` is derived from `value`
# (scaled so ~7.5% fills the bar) so the bars always track the numbers.
GDP_TRACKER = [
    {"name": "India",    "value": MACRO["gdp_growth"], "accent": "up"},
    {"name": "China",    "value": 4.8,                 "accent": "gold"},
    {"name": "USA",      "value": 2.7,                 "accent": "sea"},
    {"name": "Eurozone", "value": 0.9,                 "accent": "paper-mute"},
]
for _row in GDP_TRACKER:
    _row["width"] = max(6, min(100, round(_row["value"] / 7.5 * 100)))

# Countries for the Markets comparison dropdowns (World Bank 2-letter codes).
COUNTRIES = [
    ("IN", "🇮🇳 India"),          ("US", "🇺🇸 United States"), ("CN", "🇨🇳 China"),
    ("GB", "🇬🇧 United Kingdom"), ("DE", "🇩🇪 Germany"),       ("JP", "🇯🇵 Japan"),
    ("BR", "🇧🇷 Brazil"),         ("ZA", "🇿🇦 South Africa"),  ("KR", "🇰🇷 South Korea"),
    ("ID", "🇮🇩 Indonesia"),      ("MX", "🇲🇽 Mexico"),        ("RU", "🇷🇺 Russia"),
    ("FR", "🇫🇷 France"),         ("CA", "🇨🇦 Canada"),        ("AU", "🇦🇺 Australia"),
    ("SG", "🇸🇬 Singapore"),      ("NG", "🇳🇬 Nigeria"),       ("BD", "🇧🇩 Bangladesh"),
    ("PK", "🇵🇰 Pakistan"),       ("VN", "🇻🇳 Vietnam"),
]
# Plain (no-flag) names for chart labels / tooltips.
COUNTRY_NAMES_PLAIN = {code: label.split(" ", 1)[1] for code, label in COUNTRIES}


@app.context_processor
def inject_globals():
    """Make the macro figures available to every template automatically."""
    return {
        "student": STUDENT,
        "macro": MACRO,
        "central_bank_rates": CENTRAL_BANK_RATES,
        "gdp_tracker": GDP_TRACKER,
        "current_year": datetime.now().year,
        "model_name": GEMINI_MODEL,
    }


# ============================================================
#  AI TUTOR — system instruction
# ============================================================
SYSTEM_INSTRUCTION = """
You are Curve AI — an economics intelligence assistant built to develop deep conceptual understanding and real-world intuition.

## Identity
You are NOT a human and do not have a personal name. You are a system designed to think rigorously about economics and explain it clearly.

## Teaching Philosophy
You combine the analytical rigour of intermediate economics with the clarity of first-principles thinking. You never oversimplify at the cost of accuracy, but you always aim for intuitive understanding.

## Core Behavioral Rules
1. **Structured Markdown Responses** — ALL responses MUST use clean Markdown: `##` for sections, `###` for sub-sections, `**bold**` for key concepts, `-` for bullets, `>` for definitions/insights.
2. **Real-World Grounding (India + Global)** — reference the RBI, Monetary Policy Committee (MPC), Union Budget, etc. Use Indian context where relevant, and expand globally when helpful.
3. **Rigorous Frameworks** — apply correct models: Inflation → Fisher Equation, Quantity Theory, Phillips Curve; Growth → Solow, IS-LM; Trade → Comparative Advantage, Heckscher-Ohlin; Monetary Policy → Taylor Rule.
4. **Data-Backed Intuition** — use approximate real-world figures when helpful (state clearly when approximate): India GDP growth (~6–7%), CPI target (4% ± 2%), repo rate (~5.5%).
5. **Concise but Insightful** — avoid fluff; prioritise clarity; keep responses scannable but meaningful. Keep answers under ~350 words unless asked to go deep.
6. **Knowledge Check (MANDATORY)** — end EVERY response with:
   ## Knowledge Check
   Ask ONE sharp, application-based question that tests understanding (not rote memory).
7. **Tone** — analytical, sharp, intellectually engaging; slightly challenging but supportive.

## Objective
Your goal is not just to answer, but to help the user think like an economist.
"""

# ============================================================
#  MOCK NEWS — safety net so the News page is never empty
# ============================================================
MOCK_NEWS_DATA = [
    {
        "title": "RBI Holds Repo Rate at 5.50% as Inflation Stays Within Target",
        "summary": "The Reserve Bank of India's Monetary Policy Committee voted to hold the benchmark repo rate steady at 5.50%, citing a benign inflation outlook balanced against global commodity-price uncertainty.",
        "source": "The Economic Times",
        "url": "#",
        "time": "20260410T090000",
        "sentiment": "Neutral",
    },
    {
        "title": "India's GDP Growth Projected at 6.5% for FY26, IMF Holds Forecast",
        "summary": "The International Monetary Fund kept India's GDP growth forecast at 6.5% for the fiscal year, citing robust domestic consumption, strong manufacturing PMI data, and accelerating public capital expenditure.",
        "source": "Bloomberg India",
        "url": "#",
        "time": "20260410T090000",
        "sentiment": "Bullish",
    },
    {
        "title": "US Federal Reserve Signals Slower Rate-Cut Trajectory",
        "summary": "The Fed indicated the pace of rate reductions would be more gradual than previously projected, pointing to a resilient labour market and sticky services inflation above its 2% target.",
        "source": "Reuters",
        "url": "#",
        "time": "20260410T090000",
        "sentiment": "Bearish",
    },
    {
        "title": "Rupee Steadies Against Dollar as Foreign Inflows Return",
        "summary": "The Indian rupee firmed as foreign portfolio investors turned net buyers of domestic equities and bonds, easing pressure on the currency after a volatile quarter.",
        "source": "Mint",
        "url": "#",
        "time": "20260410T090000",
        "sentiment": "Bullish",
    },
    {
        "title": "Core Inflation Ticks Up on Firm Services Demand",
        "summary": "Analysts warned that sticky core inflation could delay further monetary easing, even as headline CPI remains comfortably within the RBI's tolerance band.",
        "source": "Business Standard",
        "url": "#",
        "time": "20260410T090000",
        "sentiment": "Bearish",
    },
    {
        "title": "Union Budget Prioritises Capex and Infrastructure Push",
        "summary": "The government reaffirmed a growth-oriented fiscal stance, raising capital expenditure allocations for railways, roads and green energy while holding the deficit path steady.",
        "source": "The Hindu BusinessLine",
        "url": "#",
        "time": "20260410T090000",
        "sentiment": "Bullish",
    },
]


# ============================================================
#  PAGE ROUTES
# ============================================================
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/ai")
def ai():
    return render_template("ai.html")


@app.route("/market")
def market():
    return render_template("market.html",
                           countries=COUNTRIES,
                           name_plain=COUNTRY_NAMES_PLAIN)


@app.route("/simulation")
def simulation():
    return render_template("simulation.html")


@app.route("/news")
def news():
    return render_template("news.html")


@app.route("/health")
def health():
    """Tiny status endpoint — handy for uptime checks / deploys."""
    return jsonify({
        "status": "ok",
        "model": GEMINI_MODEL,
        "gemini_key": bool(GEMINI_API_KEY),
        "gnews_key": bool(GNEWS_API_KEY),
    })


# ============================================================
#  API — AI TUTOR (direct Gemini REST call)
# ============================================================
@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Relay a chat turn to Gemini. Always returns JSON; never leaks a stack trace."""
    if not GEMINI_API_KEY:
        return jsonify({
            "error": "The AI Tutor isn't configured yet — no GEMINI_API_KEY was found on the server."
        }), 503

    try:
        payload = request.get_json(force=True, silent=True) or {}
        user_message = (payload.get("message") or "").strip()
        raw_history = payload.get("history", [])

        if not user_message:
            return jsonify({"error": "Message cannot be empty."}), 400

        # Keep a single turn bounded (protects the free-tier Gemini quota).
        user_message = user_message[:MAX_MESSAGE_CHARS]
        if isinstance(raw_history, list):
            raw_history = raw_history[-MAX_HISTORY_TURNS:]
        else:
            raw_history = []

        # Rebuild the conversation in Gemini's expected shape.
        contents = []
        for entry in raw_history:
            if not isinstance(entry, dict):
                continue
            role = entry.get("role")
            content = (entry.get("content") or "").strip()[:MAX_MESSAGE_CHARS]
            if role in ("user", "model") and content:
                contents.append({"role": role, "parts": [{"text": content}]})
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        generation_config = {
            "temperature": 0.75,
            "topP": 0.95,
            "maxOutputTokens": 2048,
        }
        if _SUPPORTS_THINKING:
            # Spend the whole budget on the visible answer, not hidden reasoning.
            generation_config["thinkingConfig"] = {"thinkingBudget": 0}

        request_data = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": contents,
            "generationConfig": generation_config,
        }

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        )
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=request_data,
            timeout=30,
        )

        try:
            data = resp.json()
        except ValueError:
            return jsonify({"error": "The AI returned an unreadable response. Please try again."}), 502

        # Real API error (bad key, quota, unknown model, …)
        if resp.status_code != 200:
            msg = data.get("error", {}).get("message", "Unknown API error")
            print(f"❌ Gemini API {resp.status_code}: {msg}")
            # Keep the user-facing message friendly and non-technical.
            return jsonify({"error": "The AI service is temporarily unavailable. Please try again in a moment."}), 502

        # A prompt can be blocked before any candidate is produced.
        candidates = data.get("candidates", [])
        if not candidates:
            block = data.get("promptFeedback", {}).get("blockReason")
            if block:
                return jsonify({"response": "I couldn't respond to that one — it was flagged by a safety filter. Try rephrasing your economics question."})
            return jsonify({"error": "The AI returned an empty response. Please try again."}), 502

        cand = candidates[0]
        parts = cand.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        finish = cand.get("finishReason")

        if not text:
            if finish == "MAX_TOKENS":
                return jsonify({"response": "That answer ran long and got cut off — try asking something a little more specific."})
            if finish in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"):
                return jsonify({"response": "I can't answer that one. Let's keep it to economics — ask me anything about markets, policy or theory."})
            return jsonify({"error": "The AI returned an empty response. Please try again."}), 502

        return jsonify({"response": text})

    except requests.exceptions.Timeout:
        return jsonify({"error": "The AI is taking too long to respond. Please try again."}), 504
    except requests.exceptions.RequestException:
        return jsonify({"error": "Couldn't reach the AI service. Check your connection and try again."}), 502
    except Exception as e:  # last-resort guard — never 500 with a stack trace
        print(f"❌ Unexpected error in /api/chat: {type(e).__name__}: {e}")
        return jsonify({"error": "Something went wrong on our side. Please try again."}), 500


# ============================================================
#  NEWS — GNews with a 60-minute cache shield + mock fallback
# ============================================================
_cached_news = None
_last_news_fetch = 0.0
_CACHE_TTL_SECONDS = 3600

BULLISH_WORDS = {
    "growth", "grows", "ease", "eases", "easing", "surge", "surges", "gain",
    "gains", "boom", "positive", "upbeat", "upward", "rise", "rises", "rebound",
    "recovery", "record", "expansion", "expands", "boost", "optimism", "rally",
    "strong", "strengthen", "inflows", "beat", "beats", "cut", "cuts",
}
BEARISH_WORDS = {
    "warns", "warning", "conflict", "risk", "risks", "lower", "decline",
    "declines", "fall", "falls", "drop", "drops", "contraction", "deficit",
    "crisis", "slowdown", "slump", "weak", "weakens", "fear", "fears",
    "recession", "layoffs", "default", "downgrade", "plunge", "selloff",
    "sticky", "hike", "hikes", "tariff", "tariffs",
}


def _classify_sentiment(text: str) -> str:
    """Very small whole-word lexicon tagger. Not real NLP — just a heuristic."""
    words = set(text.lower().replace(",", " ").replace(".", " ").split())
    bull = len(words & BULLISH_WORDS)
    bear = len(words & BEARISH_WORDS)
    if bull > bear:
        return "Bullish"
    if bear > bull:
        return "Bearish"
    return "Neutral"


@app.route("/api/news", methods=["GET"])
def api_news():
    global _cached_news, _last_news_fetch

    now = time.time()
    if _cached_news is not None and (now - _last_news_fetch < _CACHE_TTL_SECONDS):
        return jsonify({"articles": _cached_news, "source": "live"})

    try:
        if not GNEWS_API_KEY:
            raise ValueError("GNEWS_API_KEY not configured")

        gnews_url = (
            "https://gnews.io/api/v4/search"
            "?q=macroeconomics OR economy OR RBI OR inflation OR GDP"
            f"&lang=en&country=in&max=10&apikey={GNEWS_API_KEY}"
        )
        resp = requests.get(gnews_url, timeout=12)
        resp.raise_for_status()
        data = resp.json()

        if "articles" not in data or not data["articles"]:
            raise ValueError(f"GNews returned no articles: {data.get('errors', data)}")

        articles = []
        for item in data["articles"]:
            title = item.get("title") or "Untitled"
            summary = item.get("description") or "No summary available."
            if len(summary) > 220:
                summary = summary[:217] + "..."

            sentiment = _classify_sentiment(f"{title} {summary}")

            raw_date = item.get("publishedAt", "")
            try:
                parsed = datetime.strptime(raw_date, "%Y-%m-%dT%H:%M:%SZ")
                clean_time = parsed.strftime("%Y%m%dT%H%M%S")
            except (ValueError, TypeError):
                clean_time = raw_date

            source = (item.get("source") or {}).get("name", "Unknown")

            articles.append({
                "title": title,
                "summary": summary,
                "source": source,
                "url": item.get("url", "#"),
                "time": clean_time,
                "sentiment": sentiment,
            })

        _cached_news = articles
        _last_news_fetch = now
        print(f"✅ Cached {len(articles)} live GNews articles.")
        return jsonify({"articles": articles, "source": "live"})

    except Exception as e:
        # Never fail the page — serve the sample feed, clearly labelled as such
        # so nothing fabricated is ever presented as live reporting.
        print(f"⚠️  GNews unavailable ({type(e).__name__}: {e}). Serving sample feed.")
        return jsonify({"articles": MOCK_NEWS_DATA, "source": "sample"})


# ============================================================
#  ERROR HANDLERS — friendly pages, never the raw debugger
# ============================================================
@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found."}), 404
    return render_template("error.html", code=404,
                           message="This page doesn't exist."), 404


@app.errorhandler(500)
def server_error(_e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error."}), 500
    return render_template("error.html", code=500,
                           message="Something went wrong on our side."), 500


@app.errorhandler(HTTPException)
def http_exception(e):
    """Catch-all for other HTTP errors (405, 413, …) — friendly page or JSON."""
    code = e.code or 500
    if code in (404, 500):  # handled above with tailored messages
        return e
    if request.path.startswith("/api/"):
        return jsonify({"error": e.name}), code
    return render_template("error.html", code=code, message=e.description), code


# ============================================================
#  ENTRY POINT
# ============================================================
if __name__ == "__main__":
    # Debug is OFF unless FLASK_DEBUG=1 — so a live demo never shows the
    # interactive Werkzeug traceback page.
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    port = int(os.getenv("PORT", "5000"))
    print(f"  🚀 The Curve running on http://127.0.0.1:{port}  (debug={debug})")
    app.run(debug=debug, host="0.0.0.0", port=port)
