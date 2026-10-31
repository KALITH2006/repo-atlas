"""Repo Atlas - groups popular GitHub repositories by domain.

Run:  python app.py   ->  http://localhost:5000
Optional: set GITHUB_TOKEN for 30 req/min instead of 10 req/min.
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")

GITHUB_API = "https://api.github.com/search/repositories"
TOKEN = os.getenv("GITHUB_TOKEN")
# Vercel's filesystem is read-only except /tmp
CACHE_FILE = "/tmp/cache.json" if os.getenv("VERCEL") else "cache.json"
CACHE_TTL = 60 * 60  # 1 hour
PER_TOPIC = 50       # repos fetched per topic (max 100)

# domain -> (GitHub topics to scan, minimum stars)
DOMAINS = {
    "AI":              (["artificial-intelligence", "llm", "generative-ai", "ai-agents"], 1000),
    "Machine Learning": (["machine-learning", "deep-learning", "pytorch", "scikit-learn"], 1000),
    "Data Science":    (["data-science", "data-visualization", "data-analysis", "pandas"], 500),
    "Cybersecurity":   (["cybersecurity", "penetration-testing", "hacking", "infosec"], 500),
    "Automobile":      (["autonomous-driving", "self-driving-car", "automotive", "can-bus"], 100),
    "Web Dev":         (["react", "nextjs", "tailwindcss", "frontend"], 2000),
    "DevOps & Cloud":  (["devops", "kubernetes", "docker", "terraform"], 1000),
    "Blockchain":      (["blockchain", "ethereum", "web3", "solidity"], 500),
    "IoT & Embedded":  (["iot", "esp32", "arduino", "embedded-systems"], 300),
    "Robotics":        (["robotics", "ros", "computer-vision", "slam"], 300),
    "Game Dev":        (["game-development", "game-engine", "unity", "godot"], 500),
    "Mobile":          (["android", "ios", "flutter", "react-native"], 1000),
}

_cache = {}
_lock = threading.Lock()


def _load_cache():
    global _cache
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            _cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _cache = {}


def _save_cache():
    try:
        with _lock, open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache, f)
    except OSError:
        pass  # cache is best-effort; in-memory copy still works


class RateLimited(Exception):
    pass


def fetch_query(query, label=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "repo-atlas"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": PER_TOPIC,
    }
    r = requests.get(GITHUB_API, params=params, headers=headers, timeout=20)
    if r.status_code in (403, 429):
        raise RateLimited("GitHub rate limit hit. Set GITHUB_TOKEN or wait a minute.")
    r.raise_for_status()
    return label or query, r.json().get("items", [])


def fetch_topic(topic, min_stars):
    return fetch_query(f"topic:{topic} stars:>{min_stars}", topic)


def to_repo(it):
    return {
        "name": it["full_name"],
        "url": it["html_url"],
        "description": it.get("description") or "",
        "stars": it["stargazers_count"],
        "forks": it["forks_count"],
        "language": it.get("language") or "Unknown",
        "topics": it.get("topics", [])[:6],
        "updated": it["pushed_at"][:10],
        "avatar": it["owner"]["avatar_url"],
        "matched": [],
    }


def build_search(term):
    """Free-text search: exact topic match plus name/description/topic text match."""
    slug = "-".join(term.lower().split())
    queries = [(f"topic:{slug}", "topic"), (f"{term} in:name,description,topics", "text")]
    merged = {}
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        for label, items in pool.map(lambda q: fetch_query(q[0], q[1]), queries):
            for it in items:
                merged.setdefault(it["full_name"], to_repo(it))["matched"].append(label)
    return sorted(merged.values(), key=lambda r: r["stars"], reverse=True)[:100]


def build_domain(domain):
    topics, min_stars = DOMAINS[domain]
    merged = {}
    with ThreadPoolExecutor(max_workers=len(topics)) as pool:
        for topic, items in pool.map(lambda t: fetch_topic(t, min_stars), topics):
            for it in items:
                repo = merged.setdefault(it["full_name"], {
                    "name": it["full_name"],
                    "url": it["html_url"],
                    "description": it.get("description") or "",
                    "stars": it["stargazers_count"],
                    "forks": it["forks_count"],
                    "language": it.get("language") or "Unknown",
                    "topics": it.get("topics", [])[:6],
                    "updated": it["pushed_at"][:10],
                    "avatar": it["owner"]["avatar_url"],
                    "matched": [],
                })
                repo["matched"].append(topic)
    repos = sorted(merged.values(), key=lambda r: r["stars"], reverse=True)
    return repos[:100]


@app.get("/api/domains")
def domains():
    return jsonify([
        {"name": d, "topics": t, "cached": d in _cache}
        for d, (t, _) in DOMAINS.items()
    ])


@app.get("/api/repos")
def repos():
    domain = request.args.get("domain", "")
    refresh = request.args.get("refresh") == "1"
    if domain not in DOMAINS:
        return jsonify(error="Unknown domain"), 400
    entry = _cache.get(domain)
    fresh = entry and time.time() - entry["ts"] < CACHE_TTL
    if fresh and not refresh:
        return jsonify(repos=entry["repos"], fetched=entry["ts"], cached=True)
    try:
        data = build_domain(domain)
    except RateLimited as e:
        if entry:  # serve stale data rather than failing
            return jsonify(repos=entry["repos"], fetched=entry["ts"], cached=True, stale=True)
        return jsonify(error=str(e)), 429
    except requests.RequestException as e:
        return jsonify(error=f"GitHub request failed: {e}"), 502
    _cache[domain] = {"ts": time.time(), "repos": data}
    _save_cache()
    return jsonify(repos=data, fetched=_cache[domain]["ts"], cached=False)


@app.get("/api/search")
def search():
    term = " ".join(request.args.get("q", "").split())[:80]
    refresh = request.args.get("refresh") == "1"
    if len(term) < 2:
        return jsonify(error="Type at least 2 characters to search GitHub"), 400
    key = "search:" + term.lower()
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < CACHE_TTL and not refresh:
        return jsonify(repos=entry["repos"], fetched=entry["ts"], cached=True)
    try:
        data = build_search(term)
    except RateLimited as e:
        if entry:
            return jsonify(repos=entry["repos"], fetched=entry["ts"], cached=True, stale=True)
        return jsonify(error=str(e)), 429
    except requests.RequestException as e:
        return jsonify(error=f"GitHub request failed: {e}"), 502
    _cache[key] = {"ts": time.time(), "repos": data}
    _save_cache()
    return jsonify(repos=data, fetched=_cache[key]["ts"], cached=False)


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


_load_cache()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
