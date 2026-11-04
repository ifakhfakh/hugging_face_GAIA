# import requests

# r = requests.get("https://agents-course-unit4-scoring.hf.space/files/f918266a-b3e0-4914-865d-4faa564f1aef")
# print(r.status_code)
# print(r.text[:300])


from ddgs import DDGS
import time

query = "Malko Competition winners list 2024 all winners"
words = query.split()
candidates = [query]
if len(words) > 4:
    candidates.append(" ".join(words[:4]))      # fallback: just the first few words

for q in candidates:
    for attempt in range(2):
        try:
            results = DDGS().text(q, max_results=6)
            if results:
                print("\n\n".join(f"{r['title']}\n{r['href']}\n{r['body']}" for r in results))
        except Exception:
            pass
        time.sleep(2)

print ("No results found for this search. Do NOT repeat it. Try a different approach: "
            "use much shorter keywords, or open a likely page directly with read_webpage "
            "(for example the relevant Wikipedia article).")