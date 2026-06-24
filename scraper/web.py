import logging, re, json, time, requests
from bs4 import BeautifulSoup
from dateutil import parser as dp
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}
CRAWL_DELAY = 1.5
MAX_PER_SITE = 15
BODY_LIMIT = 2000

def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s

def fetch(url, session):
    try:
        r = session.get(url, timeout=20, allow_redirects=True)
        r.raise_for_status()
        return r.text, r.url
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response else "?"
        logging.warning(f"HTTP {code}: {url}")
        return None, url
    except Exception as e:
        logging.warning(f"Fetch failed ({type(e).__name__}): {url}")
        return None, url

def find_articles(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    domain = "/".join(base_url.split("/")[:3])
    found, seen = [], set()
    for tag in soup.find_all(["h1","h2","h3","h4"]):
        a = tag.find("a", href=True)
        if not a or len(a.get_text(strip=True)) < 20:
            continue
        title = a.get_text(strip=True)
        href = a["href"]
        if href.startswith("//"): href = "https:" + href
        elif href.startswith("/"): href = domain + href
        elif not href.startswith("http"): href = domain + "/" + href
        if href in seen: continue
        seen.add(href)
        found.append({"title": title, "url": href,
                      "pub_date": _date_near(tag), "snippet": _snippet(tag.parent)})
        if len(found) >= MAX_PER_SITE: break
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("NewsArticle","Article","BlogPosting"):
                    url = item.get("url") or item.get("mainEntityOfPage",{}).get("@id","")
                    if url and url not in seen:
                        seen.add(url)
                        d = item.get("datePublished") or item.get("dateModified","")
                        found.append({"title": item.get("headline",""), "url": url,
                                      "pub_date": _parse_date(d), "snippet": item.get("description","")[:300]})
        except Exception:
            pass
    return found

def fetch_body(url, session):
    html, _ = fetch(url, session)
    if not html: return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script","style","nav","footer","header","aside","form","iframe"]):
        tag.decompose()
    body = None
    for sel in ["article","main","[class*='article-body']","[class*='entry-content']",
                "[class*='post-content']","[class*='article-content']"]:
        body = soup.select_one(sel)
        if body: break
    if not body: body = soup.find("body")
    if not body: return ""
    paras = [p.get_text(strip=True) for p in body.find_all("p") if len(p.get_text(strip=True)) > 40]
    return " ".join(paras)[:BODY_LIMIT]

def _date_near(tag):
    container = tag.parent
    t = container.find("time")
    if t: return _parse_date(t.get("datetime") or t.get_text(strip=True))
    for el in container.find_all(["span","div","p","small"]):
        cls = " ".join(el.get("class") or [])
        if any(x in cls.lower() for x in ["date","time","publish","posted","byline","meta"]):
            d = _parse_date(el.get_text(strip=True))
            if d: return d
    return _date_in_text(container.get_text(" ", strip=True))

def _date_in_text(text):
    m = re.search(r'\b(202[4-9]|2030)-\d{2}-\d{2}\b', text)
    if m: return _parse_date(m.group())
    m = re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+202[4-9]\b', text, re.I)
    if m: return _parse_date(m.group())
    return None

def _parse_date(text):
    if not text or len(str(text).strip()) < 4: return None
    try: return dp.parse(str(text).strip(), ignoretz=True)
    except Exception: return None

def _snippet(container):
    for p in container.find_all("p"):
        t = p.get_text(strip=True)
        if len(t) > 40: return t[:300]
    return ""
