"""
Autonomous Research Agent (real-time CLI)
=========================================

A ReAct-style autonomous research agent built with LangChain + OpenAI
(gpt-4o-mini). It runs in the terminal and streams its reasoning live:

    Thought  ->  Action (tool call)  ->  Observation  ->  ... -> Final report

Flow:
    user enters a topic -> the agent autonomously searches the web
    (DuckDuckGo), gathers ~5 sources, optionally summarises them, then writes
    a markdown report with the sections: Overview, Key Findings, Sources.

The agent decides its own steps (the tool loop is capped at ~6 iterations).
Every step is printed in real time as it happens, so you watch the agent
actually reason and act — not a pre-baked script.

Usage:
    python research_agent.py
    python research_agent.py "your research topic here"

Requires OPENAI_API_KEY (read from the environment or a local .env file).
"""

from __future__ import annotations

import os
import sys
import re
import time
from typing import List, Dict

from dotenv import load_dotenv

import requests
from bs4 import BeautifulSoup

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI

# DuckDuckGo search. The package was renamed from `duckduckgo-search` to
# `ddgs`; the new one is maintained and actually returns results, so prefer it.
try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover - fall back to the legacy package
    from duckduckgo_search import DDGS

# Colour output that works on Windows terminals too.
try:
    from colorama import Fore, Style, init as colorama_init

    colorama_init()
except ImportError:  # pragma: no cover - colour is optional
    class _NoColour:
        def __getattr__(self, _):
            return ""

    Fore = Style = _NoColour()  # type: ignore


load_dotenv()

# Force UTF-8 console output so emoji / box-drawing characters work on
# Windows terminals (which default to a legacy code page like cp1252).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
MODEL_NAME = "gpt-4o-mini"
MAX_STEPS = 8          # cap on the ReAct tool loop (raised to allow page fetches)
NUM_SOURCES = 5        # how many sources we aim to collect
FETCH_TIMEOUT = 12     # seconds to wait for a page download
FETCH_MAX_CHARS = 5000  # cap extracted text per page to keep prompts lean
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


# --------------------------------------------------------------------------- #
# Small console helpers
# --------------------------------------------------------------------------- #
def c(text: str, colour: str) -> str:
    return f"{colour}{text}{Style.RESET_ALL}"


def rule(title: str = "") -> None:
    line = "─" * 70
    if title:
        print(c(f"\n{line}\n{title}\n{line}", Fore.CYAN))
    else:
        print(c(line, Fore.CYAN))


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
def make_web_search_tool(collected_sources: List[Dict[str, str]]) -> Tool:
    """Build a web_search tool that also records sources into a shared list.

    The shared `collected_sources` list lets us reliably render a Sources
    section even if the model paraphrases things in its final answer.
    """

    def web_search(query: str) -> str:
        query = (query or "").strip()
        # Models often wrap the query in quotes; strip them so DDG gets a
        # clean phrase rather than a literal quoted (exact-match) string.
        query = query.strip("\"'").strip()
        if not query:
            return "No query provided. Pass a search query string."

        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=NUM_SOURCES))
        except Exception as exc:  # network / rate-limit / parsing issues
            return f"Search failed: {exc}. Try a different or simpler query."

        if not results:
            return "No results found. Try rephrasing the query."

        lines = []
        for i, r in enumerate(results, start=1):
            title = r.get("title", "Untitled").strip()
            url = r.get("href") or r.get("link") or r.get("url", "")
            snippet = (r.get("body") or r.get("snippet") or "").strip()

            # Record unique sources for the final Sources section.
            if url and not any(s["url"] == url for s in collected_sources):
                collected_sources.append({"title": title, "url": url})

            lines.append(f"{i}. {title}\n   URL: {url}\n   {snippet}")

        return "\n".join(lines)

    return Tool(
        name="web_search",
        func=web_search,
        description=(
            "Search the web via DuckDuckGo. Input: a concise search query "
            "string. Returns the top results with titles, URLs, and snippets. "
            "Use this to gather sources about the topic."
        ),
    )


def make_summarise_tool(llm: ChatOpenAI) -> Tool:
    """Build a summarise tool backed by the same LLM."""

    def summarise(text: str) -> str:
        text = (text or "").strip()
        if not text:
            return "No text provided to summarise."
        prompt = (
            "Summarise the following research material into tight, factual "
            "bullet points. Keep concrete facts, numbers, and named entities. "
            "Be concise.\n\n"
            f"{text[:6000]}"
        )
        return llm.invoke(prompt).content

    return Tool(
        name="summarise",
        func=summarise,
        description=(
            "Condense long text (e.g. concatenated search snippets) into "
            "concise factual bullet points. Input: the raw text to summarise."
        ),
    )


def make_fetch_page_tool() -> Tool:
    """Build a fetch_page tool that downloads a URL and extracts main text.

    This is what makes reports deep: instead of relying on short search
    snippets, the agent can open a promising URL and read the actual article.
    """

    def fetch_page(url: str) -> str:
        url = (url or "").strip().strip("\"'")
        if not url.startswith(("http://", "https://")):
            return "Invalid URL. Provide a full http(s) URL from a search result."

        try:
            resp = requests.get(
                url, headers=HTTP_HEADERS, timeout=FETCH_TIMEOUT, stream=True
            )
            resp.raise_for_status()
        except Exception as exc:
            return f"Failed to fetch {url}: {exc}. Try a different source."

        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype and "text" not in ctype:
            return f"Skipped {url}: unsupported content type ({ctype or 'unknown'})."

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # Strip non-content elements before extracting text.
        for tag in soup(
            ["script", "style", "noscript", "header", "footer", "nav", "aside", "form"]
        ):
            tag.decompose()

        # Prefer the <article>/<main> region if present, else the whole body.
        main = soup.find("article") or soup.find("main") or soup.body or soup
        text = main.get_text(separator="\n")

        # Collapse blank lines / whitespace.
        lines = [ln.strip() for ln in text.splitlines()]
        text = "\n".join(ln for ln in lines if ln)

        if not text:
            return f"No readable text extracted from {url}."

        title = (soup.title.string.strip() if soup.title and soup.title.string else url)
        body = text[:FETCH_MAX_CHARS]
        truncated = " …(truncated)" if len(text) > FETCH_MAX_CHARS else ""
        return f"TITLE: {title}\nURL: {url}\n\n{body}{truncated}"

    return Tool(
        name="fetch_page",
        func=fetch_page,
        description=(
            "Download a single web page and return its main readable text. "
            "Input: one full http(s) URL (typically taken from a web_search "
            "result). Use this to read sources in depth instead of relying on "
            "short snippets. Fetch the 2-3 most relevant URLs."
        ),
    )


# --------------------------------------------------------------------------- #
# Agent
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = f"""You are an autonomous research assistant. You research a \
topic using your tools, then write a structured markdown report.

Work through these steps:
1. Use web_search to find about {NUM_SOURCES} good sources for the topic.
2. Use fetch_page to OPEN the 2-3 most relevant URLs and read their full text.
   Base your findings on the fetched page content, not just the short search
   snippets — this is what makes the report accurate and specific.
3. Optionally use summarise to condense long fetched text into bullet points.
4. Once you have enough material, STOP calling tools and write the report
   directly as your final message.

Your final message MUST be a markdown report with exactly these sections:

## Overview
A short paragraph introducing the topic.

## Key Findings
- Bullet points of the most important, concrete findings (grounded in the
  pages you actually read).

## Sources
- A numbered list of the sources you used, as [title](url)."""


CHAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ]
)


def build_agent(llm: ChatOpenAI, tools: List[Tool]) -> AgentExecutor:
    # Native tool/function calling — far more robust than text-parsed ReAct
    # for OpenAI models (no "Invalid Format" parsing loops).
    agent = create_tool_calling_agent(llm, tools, CHAT_PROMPT)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        max_iterations=MAX_STEPS,
        return_intermediate_steps=False,
        verbose=False,
    )


def build_sources_markdown(sources: List[Dict[str, str]]) -> str:
    if not sources:
        return ""
    lines = ["", "## Sources", ""]
    for i, s in enumerate(sources, start=1):
        lines.append(f"{i}. [{s['title']}]({s['url']})")
    return "\n".join(lines)


def extract_thought(action) -> str:
    """Get any reasoning text the model emitted alongside a tool call.

    Tool-calling agents put free-text reasoning in the message content; if it's
    empty (common for gpt-4o-mini), there's simply no thought to show.
    """
    for msg in getattr(action, "message_log", None) or []:
        content = getattr(msg, "content", "")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def format_tool_input(tool_input) -> str:
    """Render a tool input (usually a dict) compactly for the live stream."""
    if isinstance(tool_input, dict):
        return ", ".join(f"{k}={v!r}" for k, v in tool_input.items())
    return str(tool_input)


# --------------------------------------------------------------------------- #
# Core engine: a real-time event generator shared by the CLI and the web UI
# --------------------------------------------------------------------------- #
def iter_research_events(topic: str):
    """Run the agent and yield structured events as they happen.

    Each event is a dict with a "type" field. Event types:
        start       {topic, model, max_steps}
        thought     {step, text}
        action      {step, tool, input}
        observation {step, text}
        report      {markdown}
        done        {elapsed, steps}
        error       {message}

    This is the single source of truth for both front-ends: the terminal CLI
    and the web server both consume this generator.
    """
    yield {"type": "start", "topic": topic, "model": MODEL_NAME,
           "max_steps": MAX_STEPS}

    collected_sources: List[Dict[str, str]] = []
    llm = ChatOpenAI(model=MODEL_NAME, temperature=0)
    tools = [
        make_web_search_tool(collected_sources),
        make_fetch_page_tool(),
        make_summarise_tool(llm),
    ]
    agent_executor = build_agent(llm, tools)

    final_output = ""
    step_no = 0
    start = time.time()

    try:
        # AgentExecutor.stream() yields work as it happens:
        #   {"actions": [...]}  when it decides to call a tool
        #   {"steps":   [...]}  when a tool returns an observation
        #   {"output":  "..."}  the final answer
        # The agent can issue several tool calls before any observation comes
        # back (parallel calls). Key each action by its tool_call_id (unique per
        # call in OpenAI tool calling) so a returning observation attaches to the
        # right step regardless of how the stream batches actions and steps.
        def action_key(action) -> str:
            return getattr(action, "tool_call_id", None) or \
                f"{action.tool}|{action.tool_input}"

        action_to_step: Dict[str, int] = {}
        for chunk in agent_executor.stream({"input": topic}):
            if "actions" in chunk:
                for action in chunk["actions"]:
                    step_no += 1
                    action_to_step[action_key(action)] = step_no
                    thought = extract_thought(action)
                    if thought:
                        yield {"type": "thought", "step": step_no, "text": thought}
                    yield {
                        "type": "action",
                        "step": step_no,
                        "tool": action.tool,
                        "input": format_tool_input(action.tool_input),
                    }
            elif "steps" in chunk:
                for step in chunk["steps"]:
                    sn = action_to_step.get(action_key(step.action), step_no)
                    yield {
                        "type": "observation",
                        "step": sn,
                        "text": str(step.observation).strip(),
                    }
            elif "output" in chunk:
                final_output = chunk["output"].strip()
    except Exception as exc:
        yield {"type": "error", "message": str(exc)}
        return

    if not final_output:
        final_output = "_The agent did not produce a report._"
    if "## Sources" not in final_output:
        final_output += "\n" + build_sources_markdown(collected_sources)

    yield {"type": "report", "markdown": final_output}
    yield {"type": "done", "elapsed": round(time.time() - start, 1),
           "steps": step_no}


def run_research(topic: str) -> str:
    """Terminal front-end: consume the event stream and print it live."""
    final_output = ""
    for ev in iter_research_events(topic):
        kind = ev["type"]
        if kind == "start":
            rule(f"🔎  Researching: {ev['topic']}")
            print(c(f"   model={ev['model']}  max_steps={ev['max_steps']}\n",
                    Fore.LIGHTBLACK_EX))
        elif kind == "thought":
            print(c(f"🧠 Thought {ev['step']}: ", Fore.YELLOW) + ev["text"])
        elif kind == "action":
            print(
                c(f"⚙️  Action {ev['step']}: ", Fore.GREEN)
                + c(ev["tool"], Fore.GREEN + Style.BRIGHT)
                + c(f"  ({ev['input']})", Fore.LIGHTBLACK_EX)
            )
        elif kind == "observation":
            obs = ev["text"].replace("\n", "\n      ")
            if len(obs) > 600:
                obs = obs[:600] + " …(truncated)"
            print(c("👀 Observation:\n      ", Fore.MAGENTA) + obs + "\n")
        elif kind == "error":
            print(c(f"\n❌ Error: {ev['message']}", Fore.RED))
        elif kind == "report":
            final_output = ev["markdown"]
        elif kind == "done":
            print(c(f"\n✅ Done in {ev['elapsed']}s — {ev['steps']} tool step(s).",
                    Fore.CYAN))
    return final_output


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        print(
            c(
                "ERROR: OPENAI_API_KEY is not set. Add it to your environment "
                "or a .env file.",
                Fore.RED,
            )
        )
        sys.exit(1)

    # Topic from CLI arg, else prompt interactively.
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:]).strip()
    else:
        topic = input(c("Enter a research topic: ", Fore.CYAN)).strip()

    if not topic:
        print(c("No topic provided. Exiting.", Fore.RED))
        sys.exit(1)

    report = run_research(topic)

    rule("📄  FINAL REPORT")
    print(report)

    safe_topic = re.sub(r"[^A-Za-z0-9]+", "_", topic)[:40].strip("_") or "report"
    out_path = os.path.join(os.getcwd(), f"research_{safe_topic}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Research Report: {topic}\n\n{report}\n")

    rule()
    print(c(f"💾 Report saved to: {out_path}", Fore.GREEN))


if __name__ == "__main__":
    main()
