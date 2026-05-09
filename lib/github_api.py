"""GitHub API utilities for fetching repository information."""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def get_repo_info(
    owner: str,
    repo: str,
    *,
    token: str | None = None,
    timeout: int = 30,
) -> dict[str, Any] | None:
    """Fetch basic information for a GitHub repository.

    Args:
        owner: Repository owner (user or organization).
        repo: Repository name.
        token: Optional GitHub personal access token for higher rate limits.
        timeout: Request timeout in seconds.

    Returns:
        A dict containing repository metadata, or None if the request fails.
        Example keys: full_name, description, stargazers_count, forks_count,
        language, topics, html_url, created_at, pushed_at, open_issues_count,
        default_branch, license.

    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "knowledgebase"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        logger.error(
            "GitHub API returned %s for %s/%s: %s",
            exc.code,
            owner,
            repo,
            exc.read().decode("utf-8", errors="replace")[:200],
        )
        return None
    except URLError as exc:
        logger.error("Network error fetching repo %s/%s: %s", owner, repo, exc.reason)
        return None
    except TimeoutError:
        logger.error("Request timed out for repo %s/%s", owner, repo)
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON for repo %s/%s: %s", owner, repo, exc)
        return None

    if not isinstance(data, dict):
        logger.error("Unexpected API response type for repo %s/%s", owner, repo)
        return None

    return {
        "full_name": data.get("full_name"),
        "description": data.get("description"),
        "html_url": data.get("html_url"),
        "stargazers_count": data.get("stargazers_count"),
        "forks_count": data.get("forks_count"),
        "open_issues_count": data.get("open_issues_count"),
        "language": data.get("language"),
        "topics": data.get("topics", []),
        "default_branch": data.get("default_branch"),
        "license": (data["license"].get("spdx_id") if data.get("license") else None),
        "created_at": data.get("created_at"),
        "pushed_at": data.get("pushed_at"),
    }
