# import requests
# from app import BasicAgent, DEFAULT_API_URL

# q = requests.get(f"{DEFAULT_API_URL}/random-question", timeout=15).json()
# print("TASK:", q)

# agent = BasicAgent()
# answer = agent(q["question"])
# print("\nANSWER:", answer)

import argparse
import random
import requests

import helpers
from app import BasicAgent, DEFAULT_API_URL
from helpers import answer_item, load_cache

helpers.SLEEP_BETWEEN = 0   # no need to pause after a single question

parser = argparse.ArgumentParser(description="Test the agent on one GAIA question.")
parser.add_argument("task_id", nargs="?",
                    help="Full task_id, or its first few characters. Omit it for a random question.")
parser.add_argument("--uncached", action="store_true",
                    help="In random mode, only pick questions that have no cached answer yet.")
parser.add_argument("--force", action="store_true",
                    help="Ignore the cached answer for this question and run the agent again.")
parser.add_argument("--list", action="store_true",
                    help="List all questions with their task_id and exit.")
args = parser.parse_args()

questions = requests.get(f"{DEFAULT_API_URL}/questions", timeout=15).json()
cache = load_cache()

# --- List mode ---
if args.list:
    for i, q in enumerate(questions):
        cached = "cached" if q["task_id"] in cache else "      "
        has_file = "file" if q.get("file_name") else "    "
        print(f"{i:2d} {q['task_id']} L{q.get('Level', '?')} {has_file} {cached} {q['question'][:70]!r}")
    raise SystemExit

# --- Pick the question ---
if args.task_id:
    matches = [q for q in questions if q["task_id"].startswith(args.task_id)]
    if len(matches) != 1:
        raise SystemExit(f"{len(matches)} questions match '{args.task_id}'. Run with --list to see the task_ids.")
    item = matches[0]
    mode = "specific"
else:
    pool = [q for q in questions if q["task_id"] not in cache] if args.uncached else questions
    if not pool:
        raise SystemExit("Every question already has a cached answer. Use --force with a task_id, or delete answers_cache.json.")
    item = random.choice(pool)
    mode = "random"

print(f"\n===== {mode} question =====")
print("task_id :", item["task_id"])
print("level   :", item.get("Level"))
print("file    :", item.get("file_name") or "none")
print("question:\n" + item["question"])
print("=" * 40)

# --- Run it ---
if args.force:
    cache.pop(item["task_id"], None)

agent = BasicAgent()
answer = answer_item(agent, item, DEFAULT_API_URL, cache)
print("\nANSWER:", answer)