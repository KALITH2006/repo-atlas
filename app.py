"""Repo Atlas - groups popular GitHub repositories by domain.

Run:  python app.py   ->  http://localhost:5000
Optional: set GITHUB_TOKEN for 30 req/min instead of 10 req/min.
"""
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import Flask, g, jsonify, request, send_from_directory

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

MAX_CACHE_ENTRIES = 200
SAFE_TERM = re.compile(r"^[\w .+#/-]{2,80}$")  # blocks GitHub qualifiers like user:, repo:, and quotes
RATE_WINDOW, RATE_MAX, REFRESH_COOLDOWN = 60, 30, 60
_hits = {}      # ip -> [timestamps] of API calls
_refreshed = {}  # ip -> last forced-refresh time
_cache = {}
_lock = threading.Lock()


def client_ip():
    # Vercel sets X-Forwarded-For; first entry is the real client
    return (request.headers.get("X-Forwarded-For", request.remote_addr or "") or "").split(",")[0].strip()


@app.before_request
def throttle():
    """Per-IP limit so one visitor can't burn the shared GitHub quota."""
    if not request.path.startswith("/api/"):
        return None
    now, ip = time.time(), client_ip()
    hits = [t for t in _hits.get(ip, []) if now - t < RATE_WINDOW]
    if len(hits) >= RATE_MAX:
        return jsonify(error="Too many requests. Please slow down."), 429
    hits.append(now)
    _hits[ip] = hits
    if len(_hits) > 5000:  # bound memory
        _hits.clear()
    if request.args.get("refresh") == "1":
        if now - _refreshed.get(ip, 0) < REFRESH_COOLDOWN:
            g.no_refresh = True  # serve from cache instead of forcing a refresh
        else:
            _refreshed[ip] = now
    return None


@app.after_request
def security_headers(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' https://avatars.githubusercontent.com data:; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


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
    refresh = request.args.get("refresh") == "1" and not g.get("no_refresh")
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
        return jsonify(error="GitHub request failed. Try again shortly."), 502
    _cache[domain] = {"ts": time.time(), "repos": data}
    _save_cache()
    return jsonify(repos=data, fetched=_cache[domain]["ts"], cached=False)


@app.get("/api/search")
def search():
    term = " ".join(request.args.get("q", "").split())
    refresh = request.args.get("refresh") == "1" and not g.get("no_refresh")
    if not SAFE_TERM.match(term):
        return jsonify(error="Use 2-80 letters, numbers, spaces or . + # / -"), 400
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
        return jsonify(error="GitHub request failed. Try again shortly."), 502
    while len(_cache) >= MAX_CACHE_ENTRIES:  # evict oldest
        _cache.pop(min(_cache, key=lambda k: _cache[k]["ts"]))
    _cache[key] = {"ts": time.time(), "repos": data}
    _save_cache()
    return jsonify(repos=data, fetched=_cache[key]["ts"], cached=False)


@app.get("/")
def landing():
    return send_from_directory("static", "landing.html")


@app.get("/app")
def index():
    return send_from_directory("static", "index.html")


_load_cache()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
