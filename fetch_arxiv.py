import urllib.request, xml.etree.ElementTree as ET, json, re, datetime, os

ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

url = "http://export.arxiv.org/api/query?search_query=all:agent+OR+all:LLM+OR+all:retrieval&start=0&max_results=100&sortBy=submittedDate&sortOrder=descending"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
resp = urllib.request.urlopen(req, timeout=60)
xml_data = resp.read().decode("utf-8")

root = ET.fromstring(xml_data)
entries = root.findall("atom:entry", ns)

papers = []
for entry in entries:
    full_id = entry.find("atom:id", ns).text.strip()
    m = re.search(r"(\d{4}\.\d{4,5})", full_id)
    base_id = m.group(1) if m else full_id

    raw_title = entry.find("atom:title", ns).text
    if raw_title:
        title = " ".join(raw_title.strip().split())
    else:
        title = ""

    authors = []
    for a in entry.findall("atom:author", ns):
        name = a.find("atom:name", ns)
        if name is not None and name.text:
            authors.append(name.text.strip())

    published = entry.find("atom:published", ns).text.strip()
    raw_summary = entry.find("atom:summary", ns).text
    if raw_summary:
        summary = " ".join(raw_summary.strip().split())
    else:
        summary = ""

    abs_url = full_id

    pdf_url = abs_url.replace("/abs/", "/pdf/") + ".pdf"

    cats = []
    for c in entry.findall("atom:category", ns):
        term = c.get("term", "")
        cats.append(term)

    primary = entry.find("arxiv:primary_category", ns)
    if primary is not None:
        pc = primary.get("term", "")
        if pc and pc not in cats:
            cats.insert(0, pc)

    if "cs.AI" not in cats and "cs.CL" not in cats:
        continue

    title_lower = title.lower()
    if any(
        kw in title_lower
        for kw in [
            "survey",
            "review",
            "a survey of",
            "a review of",
            "comprehensive review",
        ]
    ):
        continue

    version = "v1"
    ver_match = re.search(r"v(\d+)", full_id)
    if ver_match:
        version = "v" + ver_match.group(1)
    else:
        # check if version exists
        pass

    papers.append(
        {
            "id": base_id + version,
            "base_id": base_id,
            "title": title,
            "url": abs_url,
            "pdf_url": pdf_url,
            "published_at": published,
            "authors": authors,
            "categories": cats,
            "summary_raw": summary,
            "pub_ts": published,
        }
    )

papers.sort(key=lambda x: x["pub_ts"], reverse=True)

top15 = papers[:15]


def generate_summary(paper):
    title = paper["title"]
    summary = paper["summary_raw"]

    keywords = []
    if any(kw in title.lower() for kw in ["agent", "multi-agent", "agentic"]):
        keywords.append("Agent")
    if any(kw in title.lower() for kw in ["llm", "language model"]):
        keywords.append("LLM")
    if any(kw in title.lower() for kw in ["retrieval", "rag", "search"]):
        keywords.append("Retrieval")

    domain = ""
    if any(kw in title.lower() for kw in ["code", "programming"]):
        domain = "代码"
    elif any(kw in title.lower() for kw in ["video", "visual", "image"]):
        domain = "视觉"
    elif any(kw in title.lower() for kw in ["robot", "embodied", "navigation"]):
        domain = "机器人"
    elif any(kw in title.lower() for kw in ["security", "privacy", "attack"]):
        domain = "安全"
    elif any(kw in title.lower() for kw in ["math", "reasoning"]):
        domain = "推理"
    elif any(kw in title.lower() for kw in ["health", "medical", "clinical"]):
        domain = "医疗"
    elif any(kw in title.lower() for kw in ["translat", "text", "language", "nlp"]):
        domain = "NLP"
    elif any(kw in title.lower() for kw in ["benchmark", "evaluat"]):
        domain = "评估"
    elif any(kw in title.lower() for kw in ["planning", "planner"]):
        domain = "规划"

    kw_str = "、".join(keywords) if keywords else "AI"

    snippets = summary[:300]
    return (
        f"本文聚焦{domain or 'AI'}领域，提出了一种基于{kw_str}的方法。{snippets[:200]}"
    )


today = datetime.date.today().isoformat()

output = {
    "source": "arxiv",
    "skill": "arxiv-papers",
    "collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "items": [],
}

for p in top15:
    item = {
        "id": p["id"],
        "base_id": p["base_id"],
        "title": p["title"],
        "url": p["url"],
        "pdf_url": p["pdf_url"],
        "published_at": p["published_at"],
        "authors": p["authors"][:5],
        "categories": p["categories"],
        "summary": generate_summary(p),
    }
    output["items"].append(item)

os.makedirs("knowledge/raw", exist_ok=True)
out_path = f"knowledge/raw/arxiv-papers-{today}.json"

existing = {}
if os.path.exists(out_path):
    with open(out_path, "r", encoding="utf-8") as f:
        existing_data = json.load(f)
        for item in existing_data.get("items", []):
            existing[item["base_id"]] = item

for item in output["items"]:
    if item["base_id"] not in existing:
        existing[item["base_id"]] = item

merged = {
    "source": "arxiv",
    "skill": "arxiv-papers",
    "collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "items": sorted(existing.values(), key=lambda x: x["published_at"], reverse=True)[
        :15
    ],
}

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)

print(f"Saved {len(merged['items'])} papers to {out_path}")
print()
for i, p in enumerate(merged["items"]):
    print(f"{i + 1}. [{p['base_id']}] {p['title']}")
    print(f"   Categories: {', '.join(p['categories'])}")
    print(f"   Published: {p['published_at']}")
    print()
