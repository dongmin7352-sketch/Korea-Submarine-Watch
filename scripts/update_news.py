import os
import re
import json
import hashlib
import html
import random
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "data" / "news.json"
KST = ZoneInfo("Asia/Seoul")

# ── 소스 목록 ────────────────────────────────────────────────────────────
# lang="ko"  -> Google 뉴스 한국어판(hl=ko&gl=KR)으로 검색
# lang="en"  -> Google 뉴스 영문판(hl=en-US&gl=US)으로 검색, site: 로 특정 매체 제한
SOURCES = [
    ("한화오션 (국내)", ["한화오션 잠수함"], "ko"),
    ("HD현대중공업 (국내)", ["HD현대중공업 잠수함 OR 현대중공업 잠수함"], "ko"),
    ("국내 잠수함 수출 종합", ["한국 잠수함 수출 OR 잠수함 수주 OR 잠수함 계약"], "ko"),
    ("연합뉴스", ["site:yna.co.kr 잠수함 (한화오션 OR HD현대 OR 현대중공업)"], "ko"),
    ("조선비즈", ["site:biz.chosun.com 잠수함 (한화오션 OR HD현대 OR 현대중공업)"], "ko"),
    ("Naval News", ["site:navalnews.com (Hanwha Ocean submarine OR HD Hyundai submarine OR South Korea submarine export)"], "en"),
    ("Defense News", ["site:defensenews.com (Hanwha Ocean submarine OR HD Hyundai submarine OR South Korea submarine)"], "en"),
    ("Naval Technology", ["site:naval-technology.com (Hanwha Ocean submarine OR HD Hyundai submarine OR South Korea submarine)"], "en"),
    ("Breaking Defense", ["site:breakingdefense.com (Hanwha Ocean submarine OR South Korea submarine)"], "en"),
    ("Janes", ["site:janes.com (Hanwha Ocean submarine OR HD Hyundai submarine OR South Korea submarine)"], "en"),
    ("Google News 종합(영문)", ["Hanwha Ocean submarine OR HD Hyundai Heavy Industries submarine OR South Korea submarine export"], "en"),
]

# ── 키워드 정의 ──────────────────────────────────────────────────────────
COMPANIES = {
    "한화오션": ["한화오션", "hanwha ocean"],
    "HD현대중공업": ["hd현대중공업", "현대중공업", "hd hyundai heavy industries", "hd hyundai"],
}
COMPETITORS = {
    "🇩🇪 TKMS": ["tkms", "thyssenkrupp marine"],
    "🇫🇷 Naval Group": ["naval group", "scorpene"],
    "🇮🇹 Fincantieri": ["fincantieri"],
    "🇪🇸 Navantia": ["navantia", "s-80"],
    "🇯🇵 미쓰비시": ["mitsubishi heavy industries submarine", "mhi submarine"],
}
SUBMARINE_KW = ["잠수함", "submarine", "submarines", "kss-iii", "kss-3", "장보고", "도산안창호"]
EXPORT_CONTEXT_KO = ["수출", "도입", "계약", "수주", "입찰", "제안서", "협상", "양해각서", "mou", "인도", "진수", "취역", "시험", "발주"]
EXPORT_CONTEXT_EN = ["export", "procurement", "acquisition", "contract", "tender", "bid", "bidding",
                      "negotiation", "proposal", "offer", "deal", "signed", "award", "delivery", "launch",
                      "commissioned", "sea trial"]
TECHNICAL_KW = ["aip", "공기불요추진", "리튬이온", "lithium-ion", "연료전지", "fuel cell", "sonar", "소나", "어뢰", "torpedo"]
TARGET_COUNTRIES = {
    "🇵🇱 폴란드": ["poland", "폴란드"],
    "🇨🇦 캐나다": ["canada", "캐나다"],
    "🇵🇭 필리핀": ["philippines", "필리핀"],
    "🇸🇦 사우디": ["saudi arabia", "사우디"],
    "🇵🇪 페루": ["peru", "페루"],
    "🇦🇺 호주": ["australia", "호주"],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

DEBUG = os.getenv("DEBUG_COLLECTOR", "").lower() in ("1", "true", "yes")


def log(*args):
    print(*args, flush=True)


def build_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    return session


SESSION = build_session()


def clean_text(s):
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_date(s):
    if not s:
        return datetime.now(timezone.utc)
    try:
        return parsedate_to_datetime(s).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def rss_url(query, lang):
    if lang == "ko":
        params = "&hl=ko&gl=KR&ceid=KR:ko"
    else:
        params = "&hl=en-US&gl=US&ceid=US:en"
    return "https://news.google.com/rss/search?q=" + quote_plus(query) + params


def fetch_query(query, lang):
    url = rss_url(query, lang)
    try:
        r = SESSION.get(url, timeout=25)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        out = []
        for item in root.findall(".//item"):
            title = clean_text(item.findtext("title"))
            link = item.findtext("link") or ""
            desc = clean_text(item.findtext("description"))
            pub = parse_date(item.findtext("pubDate"))
            if title and link:
                out.append({"title": title, "link": link, "description": desc, "published": pub.isoformat()})
        if DEBUG:
            log(f"  [debug] query='{query}' ({lang}) -> {len(out)} raw items (status {r.status_code})")
        return out, None
    except requests.exceptions.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        snippet = ""
        if getattr(e, "response", None) is not None:
            snippet = e.response.text[:200].replace("\n", " ")
        msg = f"HTTP error (status={status}): {e} | body: {snippet}"
        log(f"  [error] query='{query}' -> {msg}")
        return [], msg
    except ET.ParseError as e:
        log(f"  [error] query='{query}' -> RSS parse failed: {e}")
        return [], f"parse error: {e}"


def find_hits(text, mapping):
    t = text.lower()
    return [name for name, kws in mapping.items() if any(k in t for k in kws)]


def companies_found(text):
    return find_hits(text, COMPANIES)


def competitors_found(text):
    return find_hits(text, COMPETITORS)


def countries_found(text):
    return find_hits(text, TARGET_COUNTRIES)


def relevance(article):
    text = (article["title"] + " " + article["description"]).lower()
    company_hits = companies_found(text)
    sub_hit = any(k in text for k in SUBMARINE_KW)
    score = 0
    if company_hits: score += 40
    if sub_hit: score += 35
    if any(k in text for k in EXPORT_CONTEXT_KO) or any(k in text for k in EXPORT_CONTEXT_EN): score += 15
    if any(k in text for k in TECHNICAL_KW): score += 6
    if competitors_found(text): score += 6
    if countries_found(text): score += 8
    return max(0, min(100, score)), company_hits, sub_hit


def classify_stage(text):
    t = text.lower()
    if any(k in t for k in ["signed", "contract awarded", "계약 체결", "수주", "선정"]): return "계약/선정"
    if any(k in t for k in ["tender", "rfp", "rfi", "bid", "입찰", "제안서"]): return "입찰/제안"
    if any(k in t for k in ["negotiation", "협상", "talks", "mou", "양해각서"]): return "협상/MOU"
    if any(k in t for k in ["considering", "검토", "evaluation", "관심"]): return "도입 검토"
    if any(k in t for k in ["construction", "건조", "진수", "launch", "sea trial", "시험"]): return "건조/시험"
    if any(k in t for k in ["delivery", "인도", "commissioned", "취역"]): return "인도/취역"
    return "관련 동향"


def fallback_analysis(article, score, company_hits):
    text = (article["title"] + " " + article["description"]).lower()
    importance = 5 if score >= 80 else 4 if score >= 65 else 3 if score >= 50 else 2 if score >= 35 else 1
    tags = []
    if company_hits: tags.append("기업 언급: " + ", ".join(company_hits))
    if any(k in text for k in EXPORT_CONTEXT_KO) or any(k in text for k in EXPORT_CONTEXT_EN): tags.append("사업/수출")
    if competitors_found(text): tags.append("경쟁사 언급")
    countries = countries_found(text)
    if countries: tags.append("대상국: " + ", ".join(countries))
    tags.append(classify_stage(text))
    assessment = ("한화오션/HD현대중공업의 잠수함 수출·사업과 직접 관련된 중요 기사입니다." if score >= 65 else
                  "잠수함 관련 동향이지만 사업과의 직접적 연결은 제한적입니다." if score >= 35 else
                  "참고 수준으로 분류된 기사입니다.")
    return {"summary_ko": "AI API 키가 없어 규칙 기반 분석이 표시됩니다. 원문을 열어 핵심 내용을 확인하세요.",
            "importance": importance, "assessment": assessment,
            "tags": list(dict.fromkeys(tags)), "program_stage": classify_stage(text)}


def ai_analysis(article, score, company_hits):
    key = os.getenv("OPENAI_API_KEY")
    if not key or OpenAI is None:
        return fallback_analysis(article, score, company_hits)
    prompt = f'''당신은 방산·조선 뉴스 분석가다. 목표는 한화오션과 HD현대중공업의 잠수함 수출·건조·기술 관련 사업을 추적하는 것이다. 두 기업과 직접 관련 없는 일반 함정(구축함, 호위함 등) 기사는 낮게 평가하라. 확인되지 않은 사실은 단정하지 말라.
제목: {article['title']}
출처: {article['source']}
설명: {article['description'][:4000]}
반드시 JSON만 반환:
{{"summary_ko":"한국어 2~3문장 요약","importance":1,"assessment":"왜 중요한지 한국어 한 문장","tags":["사업/수출"],"program_stage":"도입 검토"}}
importance는 1~5. program_stage는 도입 검토 / 입찰/제안 / 협상/MOU / 계약/선정 / 건조/시험 / 인도/취역 / 관련 동향 중 하나.'''
    try:
        client = OpenAI(api_key=key)
        response = client.responses.create(model="gpt-5-mini", input=prompt)
        raw = re.sub(r"^```json\s*|\s*```$", "", response.output_text.strip(), flags=re.I)
        data = json.loads(raw)
        data["importance"] = max(1, min(5, int(data.get("importance", 3))))
        return data
    except Exception as e:
        log("AI analysis failed:", e)
        return fallback_analysis(article, score, company_hits)


def article_id(article):
    return hashlib.sha256(article["link"].encode("utf-8")).hexdigest()[:16]


def main():
    now = datetime.now(KST); today = now.date(); cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    all_articles = []; source_status = []
    for name, queries, lang in SOURCES:
        log(f"[collect] {name}")
        source_items = []; errors = []
        for query in queries:
            items, error = fetch_query(query, lang); source_items.extend(items)
            if error: errors.append(error)
            time.sleep(random.uniform(0.8, 1.6))
        unique_source = {}
        for a in source_items:
            key = re.sub(r"\W+", "", a["title"].lower())
            if key not in unique_source: unique_source[key] = a
        fresh = []
        for a in unique_source.values():
            if datetime.fromisoformat(a["published"]) >= cutoff:
                a["source"] = name; fresh.append(a)
        found_today = any(datetime.fromisoformat(a["published"]).astimezone(KST).date() == today for a in fresh)
        count_today = sum(datetime.fromisoformat(a["published"]).astimezone(KST).date() == today for a in fresh)
        log(f"  -> {len(source_items)} raw / {len(unique_source)} unique / {len(fresh)} within 14d / {count_today} today")
        source_status.append({"source": name, "query": " | ".join(queries), "found_today": found_today, "count_today": count_today, "error": "; ".join(errors) if errors else None})
        all_articles.extend(fresh)

    unique = {}
    for a in all_articles:
        key = re.sub(r"\W+", "", a["title"].lower())
        if key not in unique: unique[key] = a

    filtered = []
    borderline = []
    for a in unique.values():
        score, company_hits, sub_hit = relevance(a)
        if not company_hits or not sub_hit or score < 35:
            if DEBUG and (company_hits or sub_hit):
                borderline.append((score, a["title"]))
            continue
        a["id"] = article_id(a); a["relevance"] = score
        a["companies"] = company_hits
        a["competitors"] = competitors_found((a["title"] + " " + a["description"]).lower())
        a["countries"] = countries_found((a["title"] + " " + a["description"]).lower())
        a["program_stage"] = classify_stage((a["title"] + " " + a["description"]).lower())
        a["new_today"] = datetime.fromisoformat(a["published"]).astimezone(KST).date() == today
        a["published_ko"] = datetime.fromisoformat(a["published"]).astimezone(KST).strftime("%Y-%m-%d %H:%M")
        a["_score"] = score
        a["_company_hits"] = company_hits
        filtered.append(a)

    if DEBUG and borderline:
        log(f"[debug] {len(borderline)} articles excluded by score/keyword filter (score < 35 or missing keyword):")
        for score, title in sorted(borderline, reverse=True)[:10]:
            log(f"    score={score:>3}  {title}")

    filtered.sort(key=lambda x: (x.get("relevance", 0), x["published"]), reverse=True)
    for a in filtered[:15]:
        a.update(ai_analysis(a, a.pop("_score"), a.pop("_company_hits")))
    for a in filtered[15:]:
        a.update(fallback_analysis(a, a.pop("_score"), a.pop("_company_hits")))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": now.isoformat(), "updated_at_ko": now.strftime("%Y-%m-%d %H:%M"), "today": str(today), "sources": source_status, "articles": filtered[:200]}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Wrote {len(filtered)} relevant articles to {OUT}")


if __name__ == "__main__": main()
