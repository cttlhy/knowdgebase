import logging
import requests

logger = logging.getLogger(__name__)


def get_repo_info(owner: str, repo: str, token: str | None = None) -> dict:
    """
    Fetch basic repository info from GitHub API.

    Args:
        owner: Repository owner (username or org).
        repo: Repository name.
        token: Optional GitHub personal access token (increases rate limit).

    Returns:
        dict with keys: full_name, stars, forks, description, language, url.

    Raises:
        requests.HTTPError: If the API request fails (e.g. 404, 403).
    """
    url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    logger.info("Fetching repo info: %s/%s", owner, repo)
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        logger.error("Failed to fetch repo info for %s/%s", owner, repo, exc_info=True)
        raise

    result = {
        "full_name": data.get("full_name"),
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "description": data.get("description"),
        "language": data.get("language"),
        "url": data.get("html_url"),
    }
    logger.info(
        "Fetched %s: stars=%d, forks=%d",
        result["full_name"],
        result["stars"],
        result["forks"],
    )
    return result
