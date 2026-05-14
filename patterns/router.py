from __future__ import annotations

import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

# 按你的要求依赖 workflows/model_client.py
# 如果你本地实际路径不同（例如 pipeline.model_client），把这行改掉即可。
from pipeline.model_client import chat, chat_json


ROOT_DIR = Path(__file__).resolve().parent.parent
INDEX_FILE = ROOT_DIR / "knowledge" / "articles" / "index.json"

INTENT_GITHUB = "github_search"
INTENT_KNOWLEDGE = "knowledge_query"
INTENT_GENERAL = "general_chat"


def _keyword_intent(query: str) -> str | None:
    """第一层：零成本关键词路由。命中就直接返回，不调用 LLM。"""
    q = query.lower()

    github_keywords = [
        "github", "repo", "仓库", "代码库", "开源", "star", "stars",
        "issue", "pr", "pull request", "项目地址", "搜仓库",
    ]
    knowledge_keywords = [
        "知识库", "knowledge", "文章", "资料", "文档", "索引", "本地内容",
        "总结", "归档", "articles",
    ]

    if any(k in q for k in github_keywords):
        return INTENT_GITHUB
    if any(k in q for k in knowledge_keywords):
        return INTENT_KNOWLEDGE
    return None


def _llm_intent(query: str) -> str:
    """第二层：LLM 分类兜底。只允许返回三种意图之一。"""
    system_prompt = (
        "你是意图分类器。"
        "你只能输出 JSON，格式为: {\"intent\":\"github_search|knowledge_query|general_chat\"}。"
        "不要输出其他字段。"
    )
    user_prompt = (
        "请判断用户意图。\n"
        f"用户输入: {query}\n"
        "可选意图:\n"
        "- github_search: 用户想搜索 GitHub 仓库、项目、star 排行等\n"
        "- knowledge_query: 用户想查询本地知识库内容\n"
        "- general_chat: 其他闲聊或通用问答\n"
    )

    try:
        # 按你的说明，chat_json 返回 (json_obj, usage)
        payload, _usage = chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
    except TypeError:
        # 兼容另一种常见签名（若你的 chat_json 不是 messages 风格）
        payload, _usage = chat_json(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.0,
        )

    intent = str((payload or {}).get("intent", "")).strip()
    if intent in {INTENT_GITHUB, INTENT_KNOWLEDGE, INTENT_GENERAL}:
        return intent
    return INTENT_GENERAL


def handle_github_search(query: str) -> str:
    """处理 github_search：调用 GitHub Search API，query 必须 quote 编码。"""
    sort_key = "updated" if _looks_like_recent_query(query) else "stars"
    items, error = _search_github_repositories(query, sort_key=sort_key)
    if error:
        return f"GitHub 搜索失败: {error}"

    if not items:
        fallback_query = _build_github_fallback_query(query)
        if fallback_query and fallback_query != query:
            items, error = _search_github_repositories(fallback_query, sort_key=sort_key)
            if error:
                return f"GitHub 搜索失败: {error}"

    if not items:
        return "没有找到相关 GitHub 仓库。"

    lines: list[str] = ["GitHub 搜索结果："]
    for item in items:
        full_name = item.get("full_name", "unknown")
        html_url = item.get("html_url", "")
        desc = item.get("description") or "（无描述）"
        stars = item.get("stargazers_count", 0)
        lines.append(f"- {full_name} | Stars: {stars}")
        lines.append(f"  {desc}")
        lines.append(f"  {html_url}")

    return "\n".join(lines)


def _looks_like_recent_query(query: str) -> bool:
    q = (query or "").lower()
    hints = ("最近", "最新", "recent", "latest", "new")
    return any(h in q for h in hints)


def _build_github_fallback_query(query: str) -> str | None:
    # 中文自然语言里常带有“搜索/最近/框架”这类词，直接发给 GitHub 往往命中率很低。
    # 这里提取英文/数字关键词，作为第二次检索的最小兜底策略。
    tokens = re.findall(r"[a-zA-Z0-9_-]+", query or "")
    if not tokens:
        return None
    normalized = " ".join(tokens[:4]).strip()
    return normalized or None


def _search_github_repositories(query: str, *, sort_key: str) -> tuple[list[dict], str | None]:
    encoded_query = urllib.parse.quote(query, safe="")
    url = (
        "https://api.github.com/search/repositories"
        f"?q={encoded_query}&sort={sort_key}&order=desc&per_page=5"
    )

    request_obj = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "router-demo",
        },
    )

    try:
        with urllib.request.urlopen(request_obj, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return [], str(exc)

    items = data.get("items", [])[:5]
    return items, None


def handle_knowledge_query(query: str) -> str:
    """处理 knowledge_query：从本地 knowledge/articles/index.json 检索。"""
    articles, load_error = _load_articles_from_index_or_files()
    if load_error:
        return load_error

    q = query.lower().strip()
    if not q:
        return "请输入要检索的知识库关键词。"

    query_terms = _extract_query_terms(q)
    scored: list[tuple[int, dict]] = []
    for article in articles:
        title = str(article.get("title", ""))
        summary = str(article.get("summary", ""))
        source_url = str(article.get("source_url", ""))
        tags = article.get("tags", [])
        tags_text = " ".join(str(t) for t in tags)

        haystack = f"{title} {summary} {tags_text}".lower()
        score = haystack.count(q)
        for term in query_terms:
            score += haystack.count(term)

        if score > 0:
            scored.append((score, article))

    if not scored:
        return "知识库里没有找到相关内容。"

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [item for _score, item in scored[:5]]

    lines = ["知识库检索结果："]
    for article in top:
        title = article.get("title", "未命名")
        summary = article.get("summary", "（无摘要）")
        source_url = article.get("source_url", "")
        lines.append(f"- {title}")
        lines.append(f"  {summary}")
        if source_url:
            lines.append(f"  {source_url}")

    return "\n".join(lines)


def _extract_query_terms(query: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9._-]*", query.lower())
    # 去重并保留顺序，避免重复加权。
    ordered_unique: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in seen:
            seen.add(token)
            ordered_unique.append(token)
    return ordered_unique


def _load_articles_from_index_or_files() -> tuple[list[dict], str | None]:
    if INDEX_FILE.exists():
        try:
            raw = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            return [], f"知识库索引读取失败: {exc}"
        if isinstance(raw, dict):
            return list(raw.get("items", [])), None
        if isinstance(raw, list):
            return raw, None
        return [], "知识库索引格式不正确。"

    article_files = sorted(INDEX_FILE.parent.glob("*.json"))
    if not article_files:
        return [], f"知识库索引不存在: {INDEX_FILE}"

    articles: list[dict] = []
    for file_path in article_files:
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(raw, dict):
            articles.append(raw)
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    articles.append(item)
    if not articles:
        return [], f"知识库索引不存在: {INDEX_FILE}"
    return articles, None


def handle_general_chat(query: str) -> str:
    """处理 general_chat：直接调用 LLM。"""
    try:
        # 按你的说明，chat 返回 (text, usage)
        text, _usage = chat(query)
    except TypeError:
        # 兼容另一种常见签名
        text, _usage = chat(
            messages=[{"role": "user", "content": query}],
            temperature=0.7,
        )
    return text


HANDLER_NAMES: dict[str, str] = {
    INTENT_GITHUB: "handle_github_search",
    INTENT_KNOWLEDGE: "handle_knowledge_query",
    INTENT_GENERAL: "handle_general_chat",
}


def route(query: str) -> str:
    """统一入口：route(query) -> str"""
    clean_query = (query or "").strip()
    if not clean_query:
        return "请输入问题。"

    # 第一层：关键词快速匹配（零成本）
    intent = _keyword_intent(clean_query)

    # 第二层：LLM 兜底分类
    if intent is None:
        intent = _llm_intent(clean_query)

    handler_name = HANDLER_NAMES.get(intent, "handle_general_chat")
    handler = globals().get(handler_name, handle_general_chat)
    return handler(clean_query)


if __name__ == "__main__":
    import sys

    # 简单测试入口：命令行参数优先，否则交互输入
    if len(sys.argv) > 1:
        query_text = " ".join(sys.argv[1:])
    else:
        query_text = input("请输入 query: ").strip()

    print(route(query_text))