# 🤖 MAMA AGENT (cloud-ready, Phase 1)

A tool-using AI agent: Streamlit UI + Google Gemini (function calling + Google Search grounding).
Runs locally **or** on Streamlit Community Cloud straight from a GitHub repo.

## Phase 1 status
Done and tested: config, Gemini provider (swappable), agent loop (multi-step, retries, rollback on failure),
tool registry with permissions + timeouts, calculator (safe AST), date/time, workspace-sandboxed file tools,
Google-grounded web search with source URLs, SQLite task history, password gate, logging, 18 tests + GitHub Actions CI.
Next: Phase 3 documents/PPTX/XLSX/PDF (Phase 2 web research is already included in basic form).

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                   # then put your GEMINI_API_KEY inside
pytest -q
streamlit run app.py
```

## Deploy from GitHub (free)
1. Create a GitHub repo and push this folder (`.env` and `secrets.toml` are git-ignored - never commit keys).
   ```bash
   git init && git add . && git commit -m "MAMA AGENT phase 1"
   git branch -M main
   git remote add origin https://github.com/<you>/mama-agent.git
   git push -u origin main
   ```
2. Go to https://share.streamlit.io → **New app** → pick the repo, branch `main`, main file `app.py`.
3. **Advanced settings → Secrets**: paste the contents of `.streamlit/secrets.toml.example` with your real values
   (`GEMINI_API_KEY`, `GEMINI_MODEL`, `APP_PASSWORD`).
4. Deploy. Every `git push` redeploys automatically; GitHub Actions runs the tests on each push.

## Cloud limitations (by design)
- Disk is **ephemeral**: files in `workspace/output` and `data/agent.db` vanish on reboot. The UI offers download buttons for new files.
- No visible browser / Playwright on Streamlit Cloud → Phase 4 needs a different host (Docker on a VPS, Render, Fly.io, Hugging Face Spaces, etc.).
- Always set `APP_PASSWORD` (or make the app private) so strangers cannot use your API quota.
- Model names change; if `gemini-3.5-flash` is unavailable for your key, set `GEMINI_MODEL` to one listed in Google AI Studio.

## Layout
```
app.py            Streamlit UI            config.py   settings (.env / st.secrets)
agent/            core loop, providers (BaseModelProvider → GeminiProvider), memory (SQLite), prompts, factory
tools/            registry (permissions, timeouts) + calculator, files, web_search, system_tools
tests/            pytest suite (fake model provider - no API key needed)
```
