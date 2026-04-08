#!/usr/bin/env python3
"""Tavily API client — extract content from URLs and search the web."""

import json
import os
import sys

import requests

API_BASE = "https://api.tavily.com"


def load_api_key():
    """Load TAVILY_API_KEY from env vars or .env file in current directory."""
    key = os.environ.get("TAVILY_API_KEY")
    if key:
        return key

    # Search for .env in cwd and parent dirs (up to 5 levels), then global skill dir
    search_paths = []

    # 1. Current project .env (cwd + parents)
    path = os.getcwd()
    for _ in range(5):
        search_paths.append(os.path.join(path, ".env"))
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent

    # 2. Global fallback — .env рядом со скриптом
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_paths.append(os.path.join(script_dir, ".env"))

    for env_file in search_paths:
        if os.path.isfile(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("TAVILY_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")

    print("ERROR: TAVILY_API_KEY not found. Add it to .env or ~/.claude/skills/tavily/.env", file=sys.stderr)
    sys.exit(1)


def extract(api_key, urls, depth="basic"):
    """Extract content from URLs using Tavily Extract API."""
    resp = requests.post(
        f"{API_BASE}/extract",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "urls": urls,
            "extract_depth": depth,
            "format": "markdown",
            "include_images": False,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    # Print successful results
    for r in data.get("results", []):
        print(f"## {r['url']}\n")
        print(r.get("raw_content", "(no content)"))
        print("\n---\n")

    # Print failures
    for f in data.get("failed_results", []):
        print(f"FAILED: {f['url']} — {f.get('error', 'unknown error')}", file=sys.stderr)

    if not data.get("results") and data.get("failed_results"):
        sys.exit(1)


def search(api_key, query, depth="basic"):
    """Search the web using Tavily Search API."""
    resp = requests.post(
        f"{API_BASE}/search",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "search_depth": depth,
            "include_answer": True,
            "include_raw_content": False,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    # Print answer if available
    if data.get("answer"):
        print(f"## Answer\n\n{data['answer']}\n\n---\n")

    # Print search results
    for r in data.get("results", []):
        print(f"### {r.get('title', 'No title')}")
        print(f"{r['url']}\n")
        print(r.get("content", "(no content)"))
        print("\n---\n")

    if not data.get("results"):
        print("No results found.", file=sys.stderr)
        sys.exit(1)


def main():
    if len(sys.argv) < 3:
        print("Usage:", file=sys.stderr)
        print("  tavily_client.py extract URL1 [URL2 ...] [--depth advanced]", file=sys.stderr)
        print("  tavily_client.py search \"query\" [--depth advanced]", file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]
    args = sys.argv[2:]

    # Parse --depth flag
    depth = "basic"
    if "--depth" in args:
        idx = args.index("--depth")
        if idx + 1 < len(args):
            depth = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
        else:
            args = args[:idx]

    api_key = load_api_key()

    if mode == "extract":
        if not args:
            print("ERROR: provide at least one URL", file=sys.stderr)
            sys.exit(1)
        extract(api_key, args, depth)
    elif mode == "search":
        query = " ".join(args)
        if not query:
            print("ERROR: provide a search query", file=sys.stderr)
            sys.exit(1)
        search(api_key, query, depth)
    else:
        print(f"ERROR: unknown mode '{mode}'. Use 'extract' or 'search'.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
