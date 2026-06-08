# Research Console — Autonomous Research Agent

An AI agent that researches any topic for you. You give it a question, and it
**searches the web, opens and reads the best sources, and writes a clean,
cited report** with three sections: Overview, Key Findings, and Sources.

The special part: it is **not a black box**. You watch it think and work in
real time, step by step (search, read, summarise), as it happens.

It comes in two flavours:

1. A **premium web page** (a calm, minimal console you open in your browser).
2. A **terminal version** (runs in your command line, streams the same steps as colored text).

Both use the exact same "brain" under the hood.

---

## Table of contents

- [What it can do](#what-it-can-do)
- [How it works (in plain words)](#how-it-works-in-plain-words)
- [What's inside the project](#whats-inside-the-project)
- [Before you start (prerequisites)](#before-you-start-prerequisites)
- [Step 1 — Get the code](#step-1--get-the-code)
- [Step 2 — Create a virtual environment](#step-2--create-a-virtual-environment)
- [Step 3 — Install the dependencies](#step-3--install-the-dependencies)
- [Step 4 — Add your OpenAI API key](#step-4--add-your-openai-api-key)
- [Step 5 — Run it](#step-5--run-it)
  - [Option A: The web app (recommended)](#option-a-the-web-app-recommended)
  - [Option B: The terminal app](#option-b-the-terminal-app)
- [Using the web app](#using-the-web-app)
- [Configuration (optional tweaks)](#configuration-optional-tweaks)
- [Troubleshooting](#troubleshooting)
- [How much does it cost?](#how-much-does-it-cost)
- [Good to know / limitations](#good-to-know--limitations)
- [Tech stack](#tech-stack)

---

## What it can do

- Takes **any topic or question** as input.
- **Searches the web** using DuckDuckGo (no search API key needed).
- **Opens the most relevant pages and reads their full text**, not just the
  short search snippets. This is why the reports are specific and accurate.
- **Summarises** long pages into tight facts.
- Writes a **markdown report** with Overview, Key Findings, and Sources.
- **Streams every step live** so you can see exactly what the agent is doing.
- Lets you **download the report** as a `.md` file.

It decides its own steps. The tool loop is capped (about 8 steps) so it never
runs forever.

---

## How it works (in plain words)

Think of the agent as a smart intern with three tools:

| Tool | What it does |
|------|--------------|
| `web_search` | Searches DuckDuckGo and returns the top results (title, link, snippet). |
| `fetch_page` | Opens one web page and pulls out the readable article text. |
| `summarise`  | Condenses long text into short, factual bullet points. |

The flow for every run:

```
Your topic
   │
   ▼
1. Search the web  ─────────►  finds ~5 good sources
   │
   ▼
2. Read 2-3 best pages  ─────►  reads the actual article text
   │
   ▼
3. Summarise (optional)  ────►  squeezes pages into key facts
   │
   ▼
4. Write the final report  ──►  Overview · Key Findings · Sources
```

The "brain" is an **OpenAI model (`gpt-4o-mini`)** driven by **LangChain**
using native tool calling. The model itself chooses which tool to use and when
to stop and write the report.

The web version sends each step from the Python backend to your browser using
**Server-Sent Events (SSE)**, which is what makes the live streaming feel
instant.

---

## What's inside the project

```
Research_Assistant_agent/
├── research_agent.py      # The agent "brain" + the terminal app
├── server.py              # The web server (serves the page, streams steps)
├── web/
│   └── index.html         # The premium web page (HTML + CSS + JS, no build step)
├── requirements.txt       # All Python packages needed
├── .env                   # Your secret OpenAI API key lives here (you create this)
├── .gitignore             # Keeps .env and junk out of version control
├── examples/              # A few sample reports from past runs
└── README.md              # This file
```

- [research_agent.py](research_agent.py) — contains the three tools, the agent
  setup, and a single function `iter_research_events()` that produces the live
  steps. The terminal app and the web app both use this same function.
- [server.py](server.py) — a small FastAPI app. It serves the page and exposes
  one streaming endpoint, `/api/research`.
- [web/index.html](web/index.html) — the whole front-end in one file. No
  Node.js, no build tools, nothing to compile.

---

## Before you start (prerequisites)

You need three things:

1. **Python 3.10 or newer.** Check with:
   ```powershell
   python --version
   ```
   If you do not have it, download it from <https://www.python.org/downloads/>.
   On Windows, tick **"Add Python to PATH"** during install.

2. **An OpenAI API key.** Get one from
   <https://platform.openai.com/api-keys>. It looks like `sk-...`. This is a
   paid key (see [cost](#how-much-does-it-cost) below).

3. **An internet connection** (the agent searches and reads live web pages).

---

## Step 1 — Get the code

Put the project folder somewhere on your computer. If you already have the
folder (for example at `C:\Users\you\Documents\Research_Assistant_agent`), just
open a terminal **inside that folder**.

**Windows (PowerShell):**
```powershell
cd "C:\Users\srika\Documents\Research_Assistant_agent"
```

**macOS / Linux:**
```bash
cd ~/Documents/Research_Assistant_agent
```

---

## Step 2 — Create a virtual environment

A virtual environment keeps this project's packages separate from the rest of
your system. This step is optional but strongly recommended.

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
> If PowerShell blocks the activate script with a security error, run this once
> and try again:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

When it is active, you will see `(.venv)` at the start of your terminal line.

---

## Step 3 — Install the dependencies

This installs everything listed in `requirements.txt`:

```powershell
pip install -r requirements.txt
```

That includes LangChain, the OpenAI connector, the DuckDuckGo search package
(`ddgs`), the page reader (`requests` + `beautifulsoup4`), and the web server
(`fastapi` + `uvicorn`).

---

## Step 4 — Add your OpenAI API key

The app reads your key from a file named `.env` in the project folder.

1. Create a new file called **`.env`** (the name is just `.env`, nothing
   before the dot).
2. Put this single line inside it, with your real key:

   ```
   OPENAI_API_KEY=sk-your-real-key-here
   ```

3. Save the file.

**Quick way to create it from the terminal:**

**Windows (PowerShell):**
```powershell
"OPENAI_API_KEY=sk-your-real-key-here" | Out-File -Encoding utf8 .env
```

**macOS / Linux:**
```bash
echo "OPENAI_API_KEY=sk-your-real-key-here" > .env
```

> The `.env` file is private. It is already listed in `.gitignore`, so it will
> not be uploaded if you push this project to GitHub. Never share your key.

---

## Step 5 — Run it

You can run the agent two ways. Pick whichever you like.

### Option A: The web app (recommended)

Start the web server:

```powershell
python -m uvicorn server:app --reload
```

You will see a line like `Uvicorn running on http://127.0.0.1:8000`.

Now open your browser and go to:

```
http://127.0.0.1:8000
```

That is it. Type a topic and click **Research**.

To stop the server, go back to the terminal and press **Ctrl + C**.

> `--reload` makes the server restart automatically when you edit the code.
> You can leave it off if you just want to run it.

### Option B: The terminal app

If you prefer the command line, you can run the agent directly. The live steps
print as colored text and the final report is saved to a `.md` file.

**Give the topic right in the command:**
```powershell
python research_agent.py "how does the Raft consensus algorithm handle leader election"
```

**Or run it and let it ask you for a topic:**
```powershell
python research_agent.py
```

When it finishes, it saves a file like
`research_how_does_the_Raft_consensus_algorithm.md` in the project folder.

---

## Using the web app

1. **Type a topic** in the box, or click one of the example chips.
2. Click **Research** (or press Enter).
3. Watch the **Trace** appear live:
   - `Search` shows the query the agent typed.
   - `Read` shows each page it opened.
   - `Summarise` shows when it condensed text.
   - Click **"Result (… chars)"** under any step to expand and see the raw
     text the agent actually got back.
4. When it is done, the **report** appears below in a clean reading layout.
5. Click **Download report** to save it as a markdown (`.md`) file.

Two good topics to try first, so you can see the difference reading full pages
makes:

- `How does the Raft consensus algorithm handle leader election`
  (a "how does X work" topic — the report gets specific, with real numbers).
- `Compare LangGraph vs CrewAI for multi-agent systems`
  (a comparison topic — the agent reads articles and pulls out trade-offs).

---

## Configuration (optional tweaks)

All the simple settings live near the top of
[research_agent.py](research_agent.py):

| Setting | Default | Meaning |
|---------|---------|---------|
| `MODEL_NAME` | `"gpt-4o-mini"` | Which OpenAI model the agent uses. |
| `MAX_STEPS` | `8` | Max number of tool calls before it must write the report. |
| `NUM_SOURCES` | `5` | How many search results to gather per search. |
| `FETCH_TIMEOUT` | `12` | Seconds to wait when downloading a page. |
| `FETCH_MAX_CHARS` | `5000` | Max characters of text read from each page. |

Change a value, save the file, and run again. (If the web server is running
with `--reload`, it picks up the change automatically.)

---

## Troubleshooting

**"OPENAI_API_KEY is not set"**
Your `.env` file is missing, in the wrong folder, or the line is misspelled.
Make sure the file is named exactly `.env`, sits in the project folder, and
contains `OPENAI_API_KEY=sk-...`. Restart the app after creating it.

**`pip` is not recognized / wrong Python**
Try `python -m pip install -r requirements.txt` instead of plain `pip`.

**Port 8000 is already in use**
Another program (or an old run) is using the port. Either stop it, or run on a
different port:
```powershell
python -m uvicorn server:app --reload --port 8001
```
Then open `http://127.0.0.1:8001`.

**Search returns nothing / "Search failed"**
DuckDuckGo can rate-limit you if you run many searches quickly. Wait a minute
and try again, or rephrase the topic. The agent is built to retry with a
simpler query on its own.

**The PowerShell activate script is blocked**
Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate
the virtual environment again.

**Strange characters or a crash in the terminal version on Windows**
The app forces UTF-8 output to handle emojis. If your terminal is very old,
use Windows Terminal or PowerShell 7 for best results.

---

## How much does it cost?

The agent makes calls to the OpenAI API, which is paid, but it uses
`gpt-4o-mini`, which is one of the cheapest models. A single research run is
typically a fraction of a cent. The web search and page reading are **free**
(DuckDuckGo, no key). You can watch your usage at
<https://platform.openai.com/usage>.

---

## Good to know / limitations

- **Runs on your computer only.** The web app listens on `127.0.0.1`
  (localhost), so only you can reach it. It is not exposed to the internet.
- **Some pages cannot be read.** A few sites block automated readers or load
  their content with JavaScript. When that happens the agent simply uses other
  sources, so it keeps working.
- **The report is AI-generated.** It is grounded in real pages the agent read,
  and every source is linked, but you should still sanity-check important
  facts.
- **No HTML sanitization on the report.** This is fine for a personal,
  local-only tool. If you ever put this on a public server, add HTML
  sanitization first.

---

## Tech stack

- **Language:** Python 3.10+
- **AI orchestration:** LangChain (native tool-calling agent)
- **Model:** OpenAI `gpt-4o-mini`
- **Web search:** DuckDuckGo via the `ddgs` package (no API key)
- **Page reading:** `requests` + `BeautifulSoup`
- **Web server:** FastAPI + Uvicorn, streaming with Server-Sent Events
- **Front-end:** a single hand-written HTML/CSS/JS page (no build step)

---

Happy researching.
