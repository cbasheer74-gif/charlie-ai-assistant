"""GitHub integration plugin for CHARLIE.

Enables GitHub repository inspection, issues, pull requests, commit activity,
and developer workflow automation.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from memory.config_manager import get_plugin_config

PLUGIN = {
    "name": "github_integration",
    "description": (
        "Inspect GitHub repositories, branches, open issues, pull requests, and "
        "commits. Use when the user asks about GitHub status, repository updates, "
        "checking issues, reviewing pull requests, or cloning repos."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'status', 'list_repos', 'list_issues', 'list_prs', 'recent_commits', or 'repo_summary'",
            },
            "repo": {
                "type": "STRING",
                "description": "Target repository in 'owner/repo' format (e.g. 'octocat/Hello-World')",
            },
        },
        "required": ["action"],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "github_integration",
    "title": "GitHub Integration",
    "fields": [
        {
            "key": "token",
            "label": "Personal Access Token (PAT)",
            "type": "text",
            "default": "",
            "placeholder": "ghp_xxxxxxxxxxxxxxxxxxxx",
        },
        {
            "key": "default_repo",
            "label": "Default repository",
            "type": "text",
            "default": "",
            "placeholder": "owner/repo",
        },
        {
            "key": "auto_sync",
            "label": "Sync issues on startup",
            "type": "toggle",
            "default": True,
        },
    ],
    "action": {"label": "TEST GITHUB CONNECTION", "run": lambda: _test_connection()},
}


def _get_headers() -> dict[str, str]:
    cfg = get_plugin_config("github_integration")
    token = str(cfg.get("token") or "").strip()
    headers = {
        "User-Agent": "Charlie-AI-Assistant",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _test_connection() -> str:
    cfg = get_plugin_config("github_integration")
    token = str(cfg.get("token") or "").strip()
    if not token:
        return "Connected in public mode (no PAT set). Add a GitHub Personal Access Token for private repos."
    try:
        req = urllib.request.Request("https://api.github.com/user", headers=_get_headers())
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            user = data.get("login", "unknown")
            return f"Connected to GitHub as @{user} (Public repos: {data.get('public_repos', 0)}, Private: {data.get('total_private_repos', 0)})."
    except Exception as e:
        return f"GitHub connection test failed: {e}"


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "status").lower().strip()
    cfg = get_plugin_config("github_integration")
    repo = str(parameters.get("repo") or cfg.get("default_repo") or "").strip()
    headers = _get_headers()

    try:
        if action == "status" or not repo:
            test_res = _test_connection()
            result_text = f"GitHub Integration is active. {test_res}"
            if repo:
                result_text += f" Default repo configured: {repo}."
        elif action in ("list_issues", "issues"):
            url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page=5"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                items = json.loads(resp.read().decode())
                if not items:
                    result_text = f"No open issues found for {repo}."
                else:
                    titles = [f"#{item['number']}: {item['title']}" for item in items if "pull_request" not in item][:5]
                    result_text = f"Open issues for {repo}: " + ("; ".join(titles) if titles else "None.")
        elif action in ("list_prs", "prs"):
            url = f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=5"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                items = json.loads(resp.read().decode())
                if not items:
                    result_text = f"No open pull requests for {repo}."
                else:
                    titles = [f"PR #{item['number']}: {item['title']}" for item in items][:5]
                    result_text = f"Open PRs for {repo}: " + "; ".join(titles)
        elif action in ("recent_commits", "commits"):
            url = f"https://api.github.com/repos/{repo}/commits?per_page=5"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                items = json.loads(resp.read().decode())
                msgs = [item["commit"]["message"].splitlines()[0] for item in items][:4]
                result_text = f"Latest commits on {repo}: " + " | ".join(msgs)
        else:
            url = f"https://api.github.com/repos/{repo}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                stars = data.get("stargazers_count", 0)
                forks = data.get("forks_count", 0)
                desc = data.get("description", "")
                result_text = f"{repo}: {desc} ({stars} stars, {forks} forks)."
    except urllib.error.HTTPError as he:
        result_text = f"GitHub API error ({he.code}): {he.reason}. Please verify repository access permissions."
    except Exception as exc:
        result_text = f"Unable to reach GitHub: {exc}"

    if player:
        try:
            player.write_log(f"SYS: [GitHub] {result_text}")
        except Exception:
            pass
    return result_text
