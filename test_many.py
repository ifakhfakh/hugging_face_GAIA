import random
import requests
from app import BasicAgent, DEFAULT_API_URL
from helpers import answer_item, load_cache

N = 2

questions = requests.get(f"{DEFAULT_API_URL}/questions", timeout=15).json()
sample = random.sample(questions, min(N, len(questions)))   # 10 different questions

agent = BasicAgent()
cache = load_cache()

for i, item in enumerate(sample, 1):
    print(f"\n===== {i}/{len(sample)} | task_id: {item['task_id']} | file: {item.get('file_name') or 'none'} =====")
    print("Q:", item["question"][:300])
    try:
        print("ANSWER:", answer_item(agent, item, DEFAULT_API_URL, cache))
    except Exception as e:
        print("FAILED:", e)