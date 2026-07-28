import os, re, json, logging
import anthropic
from datetime import datetime, timedelta

DEFAULT_PROMPT_INSTRUCTIONS = """For each article write ONE original AP-style sentence summarizing the key point for industry readers.

Rules:
1. AP style throughout
2. Do NOT start with a verb
3. Do NOT copy any phrase verbatim from the article
4. One sentence only
5. Report the news or finding, do not describe the article
6. Do not include source name or URL in the summary"""


def summarize_articles(articles, newsletter_topic, topic_focus="", custom_prompt="", web_search_enabled=True, recency_days=60):
    """
    Summarize articles using Claude.

    topic_focus      : free-text editor guidance, e.g. "focus on HVAC and campus safety, avoid K-12"
    custom_prompt    : full prompt override from the advanced editor (optional)
    web_search_enabled: if True, Claude also searches the web for additional articles
    recency_days   : how many days back web-discovered articles may be from
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Build the article block
    block = ""
    for i, a in enumerate(articles, 1):
        src  = a["url"].split("/")[2].replace("www.", "")
        body = a.get("body") or a.get("snippet") or "(not available)"
        block += f"\nARTICLE {i}:\nTitle: {a['title']}\nSource: {src}\nURL: {a['url']}\nBody: {body}\n---"

    # Build summarization instructions
    instructions = custom_prompt.strip() if custom_prompt.strip() else DEFAULT_PROMPT_INSTRUCTIONS

    # Build topic guidance block
    focus_block = ""
    if topic_focus.strip():
        focus_block = f"\nEDITOR GUIDANCE — apply this to both summarization and web search:\n{topic_focus.strip()}\n"

    # Web search instruction
    search_instruction = ""
    if web_search_enabled:
        search_instruction = f"""
ADDITIONAL TASK — Web search for new sources:
After summarizing the articles above, use your web search tool to find up to 5 additional
recent articles about {newsletter_topic} that are NOT already in the list above.
{('Focus your search on: ' + topic_focus.strip()) if topic_focus.strip() else ''}
For each discovered article, include it in the JSON output with a field "discovered": true.
Only include articles from credible industry sources published on or after {(datetime.utcnow() - timedelta(days=recency_days)).strftime('%B %d, %Y')} (within the last {recency_days} days). For each discovered article, also include a "published_date" field in YYYY-MM-DD format so the date can be verified.
"""

    prompt = f"""You are an editorial assistant for the Naylor {newsletter_topic} newsletter.
Today's date is {datetime.utcnow().strftime('%B %d, %Y')}.
{focus_block}
{instructions}

Return a JSON array only. Each object must have exactly:
  article_num  : integer (use 0 for web-discovered articles)
  title        : original article title
  summary      : your one-sentence AP-style summary
  source_name  : domain only, e.g. facilityexecutive.com
  url          : full URL
  discovered   : true if you found this via web search, omit or false otherwise
  published_date : YYYY-MM-DD publish date, required for discovered articles (omit for fixed-source articles)

Return ONLY the JSON array, no markdown.
{search_instruction}
ARTICLES FROM FIXED SOURCES:
{block}"""

    # Tools list — include web search if enabled
    tools = []
    if web_search_enabled:
        tools.append({"type": "web_search_20250305", "name": "web_search"})

    try:
        model = "claude-sonnet-5" if web_search_enabled else "claude-haiku-4-5-20251001"
        kwargs = dict(
            model=model,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}]
        )
        if tools:
            kwargs["tools"] = tools

        resp = client.messages.create(**kwargs)

        # Claude can pause mid-turn on longer agentic work (e.g. running
        # several web searches). Keep feeding the conversation back so it
        # can finish, capped so a stuck loop can't run forever.
        turns = 0
        while resp.stop_reason == "pause_turn" and turns < 5:
            kwargs["messages"] = kwargs["messages"] + [{"role": "assistant", "content": resp.content}]
            resp = client.messages.create(**kwargs)
            turns += 1

        # Collect all text blocks (Claude may interleave tool use and text)
        raw = ""
        for block_item in resp.content:
            if hasattr(block_item, "text"):
                raw += block_item.text

        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("```").strip()

        if not raw:
            logging.error(f"Summarize error: empty response from Claude (stop_reason={resp.stop_reason})")
            return []

        start, end = raw.find("["), raw.rfind("]")
        json_str = raw[start:end + 1] if start != -1 and end != -1 and end > start else raw
        parsed = json.loads(json_str)

        # Hard-enforce recency for web-discovered articles instead of trusting
        # the model's compliance with the prompt instruction alone.
        cutoff_dt = datetime.utcnow() - timedelta(days=recency_days)
        filtered = []
        for item in parsed:
            if item.get("discovered"):
                pub = item.get("published_date", "")
                pub_dt = None
                if pub:
                    try:
                        pub_dt = datetime.strptime(pub[:10], "%Y-%m-%d")
                    except Exception:
                        pub_dt = None
                if not pub_dt or pub_dt < cutoff_dt:
                    logging.warning(f"Dropping discovered article outside recency window: {item.get('title', '')!r} ({pub or 'no date'})")
                    continue
            filtered.append(item)
        return filtered
    except Exception as e:
        raw_snippet = locals().get("raw", "")[:300]
        logging.error(f"Summarize error: {e} | raw response: {raw_snippet!r}")
        return []
