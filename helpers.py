import os
import json
import time
import requests
import pandas as pd
from smolagents import tool

CACHE_FILE = "answers_cache.json"
SLEEP_BETWEEN = 180      # seconds to wait after each fresh answer (helps with free-tier limits)

ANSWER_RULES = (
    "\n\nIMPORTANT: When you know the answer, finish by calling the `final_answer` tool "
    "with ONLY the answer itself, in exactly the format the question asks for. "
    "No explanation, no full sentence. Only call tools that exist; never invent a tool name."
    "Research rules: After reading a page, check whether it already contains the answer; if it does, call "
    "final_answer immediately and do not search again just to double-check. If the page says it continues, "
    "read the next part with read_webpage(start=...) before searching elsewhere. "
    "Never repeat a search that gave no new information. "
    "Never print whole pages or large tables. Extract only the relevant part with code (for example a regex or a pandas filter) and print just that. Write down key findings in your Thought so you don't need to re-read old outputs. "
    "Every reply you give must be a call to one of the available tools (web_search, read_webpage, read_file, final_answer). Never reply with plain text. "
)

import re
from markdownify import markdownify

CHUNK = 3000   # characters per call (about 1,500 tokens)

from ddgs import DDGS

@tool
def web_search(query: str) -> str:
    """Searches the web and returns the top results (title, URL, snippet).
    Args:
        query: The search query. Short, specific queries work best.
    """
    words = query.split()
    candidates = [query]
    if len(words) > 4:
        candidates.append(" ".join(words[:4]))      # fallback: just the first few words

    for q in candidates:
        for attempt in range(2):
            try:
                results = DDGS().text(q, max_results=6)
                if results:
                    return "\n\n".join(f"{r['title']}\n{r['href']}\n{r['body']}" for r in results)
            except Exception:
                pass
            time.sleep(2)

    return ("No results found for this search. Do NOT repeat it. Try a different approach: "
            "use much shorter keywords, or open a likely page directly with read_webpage "
            "(for example the relevant Wikipedia article).")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; course-agent/1.0)"}

@tool
def read_webpage(url: str, start: int = 0) -> str:
    """Fetches a web page and returns about 6000 characters of its text, starting at character offset `start`.
    If the page is longer, the result says so: call again with a larger start to read the next part.
    Args:
        url: The URL of the page to read.
        start: Character offset to start reading from (0 for the beginning).
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code in (403, 429):
            # blocked: fetch the page through the r.jina.ai reader proxy instead
            r = requests.get("https://r.jina.ai/" + url, timeout=30)
            r.raise_for_status()
            text = re.sub(r"\(https?://[^)]*\)", "", r.text)   # drop link URLs to save tokens
        else:
            r.raise_for_status()
            text = markdownify(r.text, strip=["a", "img"])
    except Exception as e:
        return f"Error fetching page: {e}"
    text = re.sub(r"\n{3,}", "\n\n", text)
    part = text[start:start + CHUNK]
    more = ""
    if start + CHUNK < len(text):
        more = f"\n\n[Page continues: {len(text)} characters total. Call again with start={start + CHUNK}.]"
    return part + more

@tool
def read_file(path: str) -> str:
    """Reads a local file and returns its contents as text. Supports .txt, .md, .json, .py, .csv and .xlsx.
    Args:
        path: Path of the file to read.
    """
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".txt", ".md", ".json", ".py"):
            with open(path, "r", errors="replace") as f:
                text = f.read()
        elif ext == ".csv":
            text = pd.read_csv(path).to_string()
        elif ext in (".xlsx", ".xls"):
            sheets = pd.read_excel(path, sheet_name=None)
            text = "\n\n".join(f"Sheet: {name}\n{df.to_string()}" for name, df in sheets.items())
        else:
            return f"Unsupported file type: {ext}"
    except Exception as e:
        return f"Error reading file: {e}"
    return text[:12000]   # keep token usage under control


def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def download_file(api_url: str, task_id: str, file_name: str):
    """Downloads the file attached to a task (if any) and returns its local path."""
    if not file_name:
        return None
    os.makedirs("files", exist_ok=True)
    path = os.path.join("files", f"{task_id}_{file_name}")
    if not os.path.exists(path):
        r = requests.get(f"{api_url}/files/{task_id}", timeout=30)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
    return path


def build_prompt(item: dict, api_url: str):
    """Returns (prompt, file_missing)."""
    prompt = item["question"]
    if item.get("file_name"):
        path = download_file(api_url, item["task_id"], item["file_name"])
        if path is None:
            return None, True
        prompt += f"\n\nAn attached file is available at: {path}. Use the read_file tool to read it."
    return prompt + ANSWER_RULES, False

def ask_with_retry(agent, prompt: str, retries: int = 3, wait: int = 30) -> str:
    for attempt in range(retries):
        try:
            return str(agent(prompt)).strip()
        except Exception as e:
            print(f"Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt == retries - 1:
                raise
            time.sleep(wait * (attempt + 1))   # wait longer after each failure


def answer_item(agent, item: dict, api_url: str, cache: dict) -> str:
    """Returns a cached answer if there is one, otherwise asks the agent and caches the result."""
    task_id = item["task_id"]
    if task_id in cache:
        print("(using cached answer)")
        return cache[task_id]
    prompt, file_missing = build_prompt(item, api_url)
    if file_missing:
        print("SKIPPED: the attached file is not available on the server")
        return "unknown"
    answer = ask_with_retry(agent, prompt)
    cache[task_id] = answer
    save_cache(cache)
    time.sleep(SLEEP_BETWEEN)
    return answer

TPM_LIMIT = 8000   # your Groq tokens-per-minute limit

from smolagents import OpenAIServerModel

class RetryingModel(OpenAIServerModel):
    """Pauses after every model call, in proportion to the tokens it used."""
    def generate(self, *args, **kwargs):
        msg = super().generate(*args, **kwargs)
        usage = getattr(msg, "token_usage", None)
        if usage:
            used = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "output_tokens", 0) or 0)
            pause = min(used / TPM_LIMIT * 60, 45)
            print(f"[pacing] {used} tokens used, pausing {pause:.0f}s")
            time.sleep(pause)
        return msg

from smolagents import ActionStep

def prune_old_observations(memory_step, agent=None, **kwargs):
    """After each step, shorten the observations of steps older than the previous one."""
    if agent is None:
        return
    for step in agent.memory.steps:
        if isinstance(step, ActionStep) and step.step_number < memory_step.step_number - 1:
            if step.observations and len(step.observations) > 400:
                step.observations = step.observations[:400] + "\n...[older output truncated]"