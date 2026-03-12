#!/usr/bin/env python3
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from html import escape, unescape
from typing import Dict, List, Optional
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

KST = timezone(timedelta(hours=9))
WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"


def fetch_url(url: str, timeout: int = 15) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ITTrendBriefBot/1.0)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def clean_news_title(title: str) -> str:
    title = re.sub(r"\s+-\s+[^-]+$", "", title)
    return title.strip()


def parse_google_news_rss(query: str, limit: int, source_keyword: str = "") -> List[Dict[str, str]]:
    url = GOOGLE_NEWS_RSS.format(query=quote_plus(query))
    root = ET.fromstring(fetch_url(url))

    items: List[Dict[str, str]] = []
    seen = set()
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source = (item.findtext("source") or "").strip()

        if source_keyword and source_keyword.lower() not in source.lower():
            continue
        if not title or not link or link in seen:
            continue

        seen.add(link)
        items.append(
            {
                "title": clean_news_title(title),
                "link": link,
                "pub_date": pub_date,
                "source": source,
            }
        )
        if len(items) >= limit:
            break

    return items


def parse_standard_feed(url: str, limit: int, include_keywords: Optional[List[str]] = None) -> List[Dict[str, str]]:
    root = ET.fromstring(fetch_url(url))
    out: List[Dict[str, str]] = []
    seen = set()

    rss_items = root.findall("./channel/item")
    if rss_items:
        for item in rss_items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            desc = (item.findtext("description") or "").strip()

            if not title or not link or link in seen:
                continue
            if include_keywords:
                text = f"{title} {desc}".lower()
                if not any(k.lower() in text for k in include_keywords):
                    continue

            seen.add(link)
            out.append({"title": clean_news_title(unescape(title)), "link": link, "pub_date": pub_date})
            if len(out) >= limit:
                return out

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    atom_entries = root.findall("atom:entry", ns)
    if atom_entries:
        for entry in atom_entries:
            title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
            updated = (entry.findtext("atom:updated", default="", namespaces=ns) or "").strip()
            summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
            link = ""

            for link_el in entry.findall("atom:link", ns):
                href = (link_el.attrib.get("href") or "").strip()
                rel = (link_el.attrib.get("rel") or "alternate").strip()
                if href and rel == "alternate":
                    link = href
                    break
            if not link:
                first_link = entry.find("atom:link", ns)
                if first_link is not None:
                    link = (first_link.attrib.get("href") or "").strip()

            if not title or not link or link in seen:
                continue
            if include_keywords:
                text = f"{title} {summary}".lower()
                if not any(k.lower() in text for k in include_keywords):
                    continue

            seen.add(link)
            out.append({"title": clean_news_title(unescape(title)), "link": link, "pub_date": updated})
            if len(out) >= limit:
                return out

    return out


def fetch_hn_front_page(limit: int = 1) -> List[Dict[str, str]]:
    payload = json.loads(fetch_url("https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=20"))
    results: List[Dict[str, str]] = []

    for hit in payload.get("hits", []):
        title = (hit.get("title") or hit.get("story_title") or "").strip()
        object_id = str(hit.get("objectID") or "").strip()
        if not title or not object_id:
            continue

        results.append(
            {
                "title": title,
                "link": f"https://news.ycombinator.com/item?id={object_id}",
                "pub_date": (hit.get("created_at") or ""),
            }
        )
        if len(results) >= limit:
            break

    return results


def safe_get(items: List[Dict[str, str]], idx: int, fallback_title: str) -> Dict[str, str]:
    if idx < len(items):
        return items[idx]
    return {"title": fallback_title, "link": "https://news.google.com/", "pub_date": ""}


def collect_brief_data() -> Dict[str, object]:
    now = datetime.now(KST)
    weekday = WEEKDAY_KO[now.weekday()]
    date_str = now.strftime(f"%Y-%m-%d({weekday})")

    zdnet_items = parse_google_news_rss(
        "site:zdnet.co.kr AI OR 반도체 OR 클라우드 OR 보안 OR 플랫폼",
        limit=4,
        source_keyword="ZDNet Korea",
    )
    if len(zdnet_items) < 4:
        zdnet_items = parse_google_news_rss(
            "site:zdnet.co.kr AI OR 반도체 OR 클라우드 OR 보안 OR 플랫폼",
            limit=4,
        )

    itworld_items = parse_google_news_rss(
        "site:itworld.co.kr AI OR 보안 OR 클라우드 OR 개발 OR 인프라",
        limit=4,
        source_keyword="ITWorld",
    )
    if len(itworld_items) < 4:
        itworld_items = parse_google_news_rss(
            "site:itworld.co.kr AI OR 보안 OR 클라우드 OR 개발 OR 인프라",
            limit=4,
        )

    techcrunch_items = parse_standard_feed(
        "https://techcrunch.com/feed/",
        limit=1,
        include_keywords=["ai", "startup", "funding", "enterprise", "openai", "anthropic"],
    )
    if not techcrunch_items:
        techcrunch_items = parse_standard_feed("https://techcrunch.com/feed/", limit=1)

    verge_items = parse_standard_feed(
        "https://www.theverge.com/rss/index.xml",
        limit=1,
        include_keywords=["ai", "apple", "google", "meta", "microsoft", "product", "launch"],
    )
    if not verge_items:
        verge_items = parse_standard_feed("https://www.theverge.com/rss/index.xml", limit=1)

    hn_items = fetch_hn_front_page(limit=1)

    market_notes = [
        "국내 산업/정책 변화가 분기 우선순위에 직접 영향",
        "경쟁사 대응 속도와 시장 체감 온도를 확인",
        "기술 도입 신호가 실제 사업/공급망으로 확산",
        "단기 이슈가 중기 로드맵 리스크로 전환 가능",
    ]
    practice_notes = [
        "바로 적용 가능한 운영/개발 방식 변화 포착",
        "비용 대비 효과가 큰 자동화/보안 우선순위 확인",
        "팀 생산성에 영향을 주는 도구/워크플로우 업데이트",
        "파일럿 실험으로 검증할 액션 아이템 도출",
    ]

    return {
        "date": date_str,
        "zdnet_items": [safe_get(zdnet_items, i, "오늘 주요 국내 시장 기사") for i in range(4)],
        "itworld_items": [safe_get(itworld_items, i, "오늘 주요 실무 해석 기사") for i in range(4)],
        "techcrunch_item": safe_get(techcrunch_items, 0, "오늘 주요 글로벌 비즈니스 기사"),
        "verge_item": safe_get(verge_items, 0, "오늘 주요 제품 감도 기사"),
        "hn_item": safe_get(hn_items, 0, "오늘 주요 Hacker News 토픽"),
        "market_notes": market_notes,
        "practice_notes": practice_notes,
    }


def news_widgets(items: List[Dict[str, str]], notes: List[str]) -> List[Dict[str, object]]:
    widgets: List[Dict[str, object]] = []
    for idx, item in enumerate(items):
        title = escape(item["title"])
        note = escape(notes[idx])
        widgets.append(
            {
                "decoratedText": {
                    "text": f"<b>{title}</b><br/><font color=\"#5f6368\">{note}</font>",
                    "wrapText": True,
                }
            }
        )
        widgets.append(
            {
                "buttonList": {
                    "buttons": [
                        {
                            "text": "바로가기 >",
                            "onClick": {"openLink": {"url": item["link"]}},
                        }
                    ]
                }
            }
        )
    return widgets


def build_card_payload() -> Dict[str, object]:
    data = collect_brief_data()
    tc = data["techcrunch_item"]
    vg = data["verge_item"]
    hn = data["hn_item"]

    sections = [
        {
            "header": "오늘의 목적",
            "widgets": [
                {
                    "textParagraph": {
                        "text": "• 의사결정에 영향 줄 변화 1개<br/>• 실무에 바로 적용할 힌트 1개<br/>• 장기적으로 추적할 약신호 1개"
                    }
                }
            ],
        },
        {
            "header": "1) 국내 시장 (4개 스캔) - ZDNet Korea",
            "widgets": news_widgets(data["zdnet_items"], data["market_notes"]),
            "collapsible": True,
            "uncollapsibleWidgetsCount": 2,
        },
        {
            "header": "2) 실무 해석 (4개 스캔) - ITWorld Korea",
            "widgets": news_widgets(data["itworld_items"], data["practice_notes"]),
            "collapsible": True,
            "uncollapsibleWidgetsCount": 2,
        },
        {
            "header": "3) 글로벌 비즈니스 - TechCrunch",
            "widgets": [
                {
                    "decoratedText": {
                        "text": f"<b>{escape(tc['title'])}</b><br/><font color=\"#5f6368\">글로벌 자본/플랫폼 움직임이 국내 전략에 선반영될 가능성</font>",
                        "wrapText": True,
                    }
                },
                {
                    "buttonList": {
                        "buttons": [
                            {"text": "바로가기 >", "onClick": {"openLink": {"url": tc["link"]}}}
                        ]
                    }
                },
            ],
        },
        {
            "header": "4) 제품 감도 - The Verge",
            "widgets": [
                {
                    "decoratedText": {
                        "text": f"<b>{escape(vg['title'])}</b><br/><font color=\"#5f6368\">UX/포지셔닝 변화에서 다음 분기 제품 방향 힌트 확보</font>",
                        "wrapText": True,
                    }
                },
                {
                    "buttonList": {
                        "buttons": [
                            {"text": "바로가기 >", "onClick": {"openLink": {"url": vg["link"]}}}
                        ]
                    }
                },
            ],
        },
        {
            "header": "5) 약신호 - Hacker News",
            "widgets": [
                {
                    "decoratedText": {
                        "text": f"<b>{escape(hn['title'])}</b><br/><font color=\"#5f6368\">초기 개발자 반응으로 2~3개월 뒤 수요 신호 선확인</font>",
                        "wrapText": True,
                    }
                },
                {
                    "buttonList": {
                        "buttons": [
                            {"text": "바로가기 >", "onClick": {"openLink": {"url": hn["link"]}}}
                        ]
                    }
                },
            ],
        },
    ]

    return {
        "cardsV2": [
            {
                "cardId": "it_trend_brief",
                "card": {
                    "header": {
                        "title": "10분 IT 트렌드 브리프",
                        "subtitle": f"{data['date']} 09:40 KST",
                    },
                    "sections": sections,
                },
            }
        ]
    }


def send_to_google_chat(webhook_url: str, payload: Dict[str, object]) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json; charset=UTF-8"},
        method="POST",
    )
    with urlopen(req, timeout=20) as resp:
        resp.read()


def main() -> int:
    webhook_url = os.getenv("GOOGLE_CHAT_WEBHOOK_URL", "").strip()
    dry_run = "--dry-run" in sys.argv

    payload = build_card_payload()

    if dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not webhook_url:
        print("ERROR: GOOGLE_CHAT_WEBHOOK_URL is not set", file=sys.stderr)
        return 1

    send_to_google_chat(webhook_url, payload)
    print("Card sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
