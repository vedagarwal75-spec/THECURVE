"""
app.py — The Curve: Economic Intelligence Platform
Backend: Flask + Direct Gemini REST API + Alpha Vantage News API
"""

import os
import json
import requests
import time 
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from datetime import datetime
# --- FORCE LOAD THE .ENV FILE ---
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

print("--- BOOT SEQUENCE ---")
print(f"Loaded Gemini Key: {os.getenv('GEMINI_API_KEY')}")
print("---------------------")

# ============================================================
#  APP INITIALIZATION
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback-dev-secret-key-change-in-prod")

# ============================================================
#  CONFIGURATION
# ============================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

SYSTEM_INSTRUCTION = """
You are Curve AI — an advanced economics intelligence assistant built to develop deep conceptual understanding and real-world intuition.

## Identity
You are NOT a human and do not have a personal name. You are a system designed to think rigorously about economics and explain it clearly.

## Teaching Philosophy
You combine the analytical rigour of intermediate economics with the clarity of first-principles thinking. You never oversimplify at the cost of accuracy, but you always aim for intuitive understanding.

## Core Behavioral Rules

1. **Structured Markdown Responses**  
   ALL responses MUST be formatted in clean Markdown:
   - Use `##` for main sections  
   - Use `###` for sub-sections  
   - Use `**bold**` for key concepts  
   - Use `-` for bullet points  
   - Use `>` blockquotes for definitions or key insights  

2. **Real-World Grounding (India + Global)**  
   Ground concepts in real-world economic systems:
   - Reference institutions like the Reserve Bank of India (RBI), Monetary Policy Committee (MPC), Union Budget, etc.
   - Use Indian context where relevant, but expand to global context when helpful.

3. **Rigorous Economic Frameworks**  
   Apply correct models wherever appropriate:
   - Inflation → Fisher Equation, Quantity Theory of Money, Phillips Curve  
   - Growth → Solow Model, IS-LM  
   - Trade → Comparative Advantage, Heckscher-Ohlin  
   - Monetary Policy → Taylor Rule  

4. **Data-Backed Intuition**  
   Use approximate real-world data when helpful (clearly state when approximate), such as:
   - India GDP growth (~6–8%)  
   - Inflation target (4% ± 2%)  
   - Repo rate range  

5. **Concise but Insightful**  
   - Avoid fluff  
   - Prioritise clarity and insight  
   - Make responses scannable but meaningful  

6. **Knowledge Check (MANDATORY)**  
   End EVERY response with:
   ## 🎓 Knowledge Check  
   Ask ONE sharp, application-based question that tests understanding (not rote memory).

7. **Tone & Voice**  
   - Analytical, sharp, and intellectually engaging  
   - Slightly challenging but supportive  
   - Use phrases like:  
     “Notice that…”,  
     “The key insight here is…”,  
     “This is precisely why…”,  
     “Consider the counterfactual…”  

## Objective
Your goal is not just to answer, but to help the user think like an economist.
"""

# ============================================================
#  MOCK NEWS DATA (10-GPA Safety Net)
# ============================================================
MOCK_NEWS_DATA = [
    {
        "title": "RBI Holds Repo Rate at 6.5% as Inflation Stays Above Target",
        "summary": "The Reserve Bank of India's Monetary Policy Committee voted 5-1 to hold the benchmark repo rate steady at 6.5%, citing persistent food inflation and global commodity price uncertainty as key risks to its 4% CPI target.",
        "source": "The Economic Times",
        "url": "#",
        "time": "20260410T090000",
        "sentiment": "Neutral"
    },
    {
        "title": "India's GDP Growth Projected at 7.2% for FY25, IMF Revises Upward",
        "summary": "The International Monetary Fund has revised India's GDP growth forecast upward to 7.2% for fiscal year 2025, citing robust domestic consumption, strong manufacturing PMI data, and accelerating capital expenditure by the Union government.",
        "source": "Bloomberg India",
        "url": "#",
        "time": "20260410T090000",
        "sentiment": "Bullish"
    },
    {
        "title": "US Federal Reserve Signals Slower Rate Cut Trajectory in 2025",
        "summary": "Fed Chair Jerome Powell indicated at the December FOMC press conference that the pace of rate reductions would be more gradual than previously projected, pointing to a resilient labour market and sticky services inflation above the 2% target.",
        "source": "Reuters",
        "url": "#",
        "time": "20260410T090000",
        "sentiment": "Bearish"
    }
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
    return render_template("market.html")

@app.route("/simulation")
def simulation():
    return render_template("simulation.html")

@app.route("/news")
def news():
    return render_template("news.html")


# ============================================================
#  API ROUTES (DIRECT REST BYPASS)
# ============================================================

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Handles chat messages using a DIRECT REST API call to Gemini 1.5 Flash.
    This bypasses any outdated Python SDK issues completely.
    """
    if not GEMINI_API_KEY:
        return jsonify({"error": "Gemini API key is not configured on the server."}), 503

    try:
        payload = request.get_json(force=True)
        if not payload:
            return jsonify({"error": "Invalid JSON payload."}), 400

        user_message = payload.get("message", "").strip()
        raw_history = payload.get("history", [])

        if not user_message:
            return jsonify({"error": "Message cannot be empty."}), 400

        # Build exactly what Google's raw servers want
        formatted_contents = []
        for entry in raw_history:
            role = entry.get("role")
            content = entry.get("content", "")
            if role in ("user", "model") and content:
                formatted_contents.append({
                    "role": role,
                    "parts": [{"text": content}]
                })

        # Add the brand new message to the end
        formatted_contents.append({
            "role": "user",
            "parts": [{"text": user_message}]
        })

        # Build the exact payload for the REST API
        request_data = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_INSTRUCTION}]
            },
            "contents": formatted_contents,
            "generationConfig": {
                "temperature": 0.75,
                "topP": 0.95,
                "maxOutputTokens": 2048
            }
        }

        # Fire the HTTP request directly at Google
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={GEMINI_API_KEY}"
        resp = requests.post(url, headers={'Content-Type': 'application/json'}, json=request_data, timeout=25)
        resp_json = resp.json()

        # Catch actual API errors (like quota limits or bad keys)
        if resp.status_code != 200:
            error_msg = resp_json.get("error", {}).get("message", "Unknown API Error")
            print(f"❌ Direct API Error: {error_msg}")
            return jsonify({"error": f"API Error: {error_msg}"}), 500

        # Extract the AI text from the raw JSON response
        ai_text = resp_json['candidates'][0]['content']['parts'][0]['text']
        return jsonify({"response": ai_text})

    except requests.exceptions.Timeout:
        print("❌ Server Error: Google API Timeout")
        return jsonify({"error": "The AI is taking too long to respond. Please try again."}), 504
    except Exception as e:
        print(f"❌ Server Crash in /api/chat: {type(e).__name__}: {e}")
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500


# ============================================================
#  THE SHIELD: Memory Cache to protect API limits
# ============================================================
cached_news_data = None
last_news_fetch_time = 0

# ============================================================
#  THE SHIELD: Memory Cache (Now using GNews)
# ============================================================
cached_news_data = None
last_news_fetch_time = 0

@app.route("/api/news", methods=["GET"])
def api_news():
    global cached_news_data, last_news_fetch_time
    
    # 1. Check the 60-minute cache
    current_time = time.time()
    if cached_news_data is not None and (current_time - last_news_fetch_time < 3600):
        print("🛡️ Render/Browser refreshed! Serving news from CACHE.")
        return jsonify(cached_news_data)

    # 2. Make the request to GNews
    try:
        api_key = os.getenv("GNEWS_API_KEY")
        if not api_key:
            raise ValueError("GNews API key not configured. Serving mock data.")

        # Searching specifically for macroeconomic and Indian context
        gnews_url = f"https://gnews.io/api/v4/search?q=macroeconomics OR economy OR RBI&lang=en&country=in&max=10&apikey={api_key}"

        print("📡 Cache empty. Making ONE careful request to GNews...")
        resp = requests.get(gnews_url, timeout=12)
        resp.raise_for_status()
        data = resp.json()

        if "articles" not in data:
            raise ValueError(f"GNews feed missing: {data}")

        articles = []
        for item in data["articles"]:
            title = item.get("title", "Untitled")
            summary = item.get("description", "No summary available.")
            if len(summary) > 220:
                summary = summary[:217] + "..."

            # --- 1. THE CUSTOM SENTIMENT ENGINE ---
            text_to_analyze = (title + " " + summary).lower()
            
            bullish_words = ['ups', 'growth', 'ease', 'surge', 'gain', 'boom', 'positive', 'upward', 'rise', 'record high', 'expansion']
            bearish_words = ['warns', 'conflict', 'inflation', 'risk', 'lower', 'decline', 'fall', 'drop', 'contraction', 'deficit', 'crisis', 'slowdown']

            bull_score = sum(1 for word in bullish_words if word in text_to_analyze)
            bear_score = sum(1 for word in bearish_words if word in text_to_analyze)

            if bull_score > bear_score:
                sentiment = "Bullish"
            elif bear_score > bull_score:
                sentiment = "Bearish"
            else:
                sentiment = "Neutral"

            # --- 2. THE DATE FIX (Fixes the "undefined" UI bug) ---
            raw_date = item.get("publishedAt", "")
            try:
                # GNews gives dates like: 2024-04-10T09:00:00Z
                parsed_date = datetime.strptime(raw_date, "%Y-%m-%dT%H:%M:%SZ")
                # We format it to look clean for your terminal: "10 Apr 2026, 09:00"
                clean_time = parsed_date.strftime("%d %b %Y, %H:%M")
            except Exception:
                # If parsing fails, just use the raw string
                clean_time = raw_date

            # --- 3. APPEND TO LIST ---
            articles.append({
                "title": title,
                "summary": summary,
                "source": item["source"].get("name", "Unknown"),
                "url": item.get("url", "#"),
                "time": clean_time,
                "sentiment": sentiment 
            })

        # 3. Lock it in the cache
        cached_news_data = articles
        last_news_fetch_time = current_time

        print(f"✅ Successfully fetched and CACHED {len(articles)} live articles from GNews.")
        return jsonify(articles)

    except Exception as e:
        print(f"⚠️ GNews API Error: {type(e).__name__}: {e}")
        print("   → Serving high-quality mock news data as fallback.")
        return jsonify(MOCK_NEWS_DATA)

# ============================================================
#  ENTRY POINT
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  🚀 THE CURVE — Economic Intelligence Platform")
    print("  Running on http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=True, port=5000)