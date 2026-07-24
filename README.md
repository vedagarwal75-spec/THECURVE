# The Curve — Economic Intelligence Platform

A Flask web app that bundles four macroeconomics tools into one dark "terminal"
style dashboard:

| Module | What it does | Data source |
| --- | --- | --- |
| **AI Tutor** | Chat with an economics tutor that answers in structured Markdown and ends every reply with a Knowledge Check. | Google Gemini (free tier) |
| **Global Markets** | Plot and compare a macro indicator (GDP growth, inflation, unemployment, …) for any two of 20 countries. | World Bank Open Data (no key) |
| **Econ Lab** | Move policy sliders (repo rate, government spending, corporate tax) and watch a stylised IS-LM / Phillips-curve model project GDP, inflation and unemployment. | Client-side model |
| **News Terminal** | Live macro headlines auto-tagged Bullish / Bearish / Neutral. | GNews (free tier), with a built-in sample fallback |

All external calls degrade gracefully — if a key is missing or an API is down,
the page shows sample data or a friendly message instead of crashing.

## Run it locally

```bash
# 1. create a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. install dependencies
pip install -r requirements.txt

# 3. add your API keys
cp .env.example .env             # then edit .env and paste your keys

# 4. start the server
python app.py
```

Open <http://127.0.0.1:5000> in your browser.

> The **Markets** and **News** modules work even without any API keys
> (World Bank needs none; News falls back to sample headlines).
> Only the **AI Tutor** needs a `GEMINI_API_KEY`.

## Configuration (.env)

| Variable | Required | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | for AI Tutor | Google Gemini key ([get one](https://aistudio.google.com/apikey)) |
| `GNEWS_API_KEY` | optional | GNews key ([get one](https://gnews.io/)) — falls back to samples if absent |
| `GEMINI_MODEL` | optional | Override the model (default `gemini-2.5-flash`) |
| `FLASK_SECRET_KEY` | optional | Flask session secret |
| `FLASK_DEBUG` | optional | `1` enables debug mode locally; keep `0` for demos |

## Notes

- One place defines every headline macro number (`MACRO` in `app.py`), so the
  dashboard, sidebar and Econ Lab baseline can never contradict each other.
- The Econ Lab is a **teaching model** with illustrative elasticities — it shows
  the direction and rough scale of policy effects, not precise forecasts.

*Built by Ved Agarwal · ECOA 279.*
