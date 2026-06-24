import os, re, json, logging
import anthropic

def summarize_articles(articles, newsletter_topic):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    block = ""
    for i, a in enumerate(articles, 1):
        src = a["url"].split("/")[2].replace("www.","")
        body = a.get("body") or a.get("snippet") or "(not available)"
        block += f"\nARTICLE {i}:\nTitle: {a['title']}\nSource: {src}\nURL: {a['url']}\nBody: {body}\n---"
    prompt = f"""You are an editorial assistant for the Naylor {newsletter_topic} newsletter.

For each article write ONE original AP-style sentence summarizing the key point for industry readers.

Rules:
1. AP style throughout
2. Do NOT start with a verb
3. Do NOT copy any phrase verbatim from the article
4. One sentence only
5. Report the news or finding, do not describe the article
6. Do not include source name or URL in the summary

Return a JSON array only. Each object: article_num (int), title (original), summary (string), source_name (domain), url (full URL).
Return ONLY the JSON array, no markdown.

ARTICLES:{block}"""
    try:
        resp = client.messages.create(model="claude-opus-4-5", max_tokens=4000,
                                       messages=[{"role":"user","content":prompt}])
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?","",raw).rstrip("```").strip()
        return json.loads(raw)
    except Exception as e:
        logging.error(f"Summarize error: {e}")
        return []
