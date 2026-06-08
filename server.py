"""
Web server for the Autonomous Research Agent.

Serves a single premium UI page and streams the agent's live steps to the
browser over Server-Sent Events (SSE). The agent engine itself lives in
research_agent.py; this file is just the transport + the report rendering.

Run:
    uvicorn server:app --reload
    # then open http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import markdown as md
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse

from research_agent import iter_research_events

load_dotenv()

APP_DIR = Path(__file__).parent
INDEX_HTML = APP_DIR / "web" / "index.html"

app = FastAPI(title="Research Console")


def render_report_html(markdown_text: str) -> str:
    """Convert the agent's markdown report into HTML for the page."""
    return md.markdown(
        markdown_text,
        extensions=["extra", "sane_lists", "nl2br"],
    )


def sse(event: dict) -> str:
    """Format one event dict as an SSE 'data:' frame."""
    return f"data: {json.dumps(event)}\n\n"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_HTML)


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True, "key_present": bool(os.getenv("OPENAI_API_KEY"))})


@app.get("/api/research")
def research(topic: str) -> StreamingResponse:
    topic = (topic or "").strip()

    def event_stream():
        if not topic:
            yield sse({"type": "error", "message": "Please enter a research topic."})
            return
        if not os.getenv("OPENAI_API_KEY"):
            yield sse({"type": "error",
                       "message": "OPENAI_API_KEY is not set on the server."})
            return

        # iter_research_events already wraps the agent run in its own
        # try/except and emits a structured 'error' event on failure.
        for ev in iter_research_events(topic):
            if ev["type"] == "report":
                ev = {**ev, "html": render_report_html(ev["markdown"])}
            yield sse(ev)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # disable proxy buffering so steps stream live
    }
    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=headers
    )
