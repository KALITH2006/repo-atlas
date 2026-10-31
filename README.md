# Repo Atlas

Browse popular GitHub repositories by domain (AI, Machine Learning, Cybersecurity, Automobile, Web Dev and more), or search GitHub for any topic or framework.

**Live demo:** https://repo-atlas-seven.vercel.app

Uses the official GitHub Search API. Each domain maps to several GitHub topics; results are merged, de-duplicated and ranked by stars. Includes a language filter, sorting, and CSV export.

## Run locally

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000.

Optional: set a `GITHUB_TOKEN` environment variable (no scopes needed) to raise the search rate limit from 10 to 30 requests per minute. Never commit tokens.

## Customize

Edit the `DOMAINS` dictionary at the top of `app.py`:

```python
"Quantum": (["quantum-computing", "qiskit"], 200),
```

## Known limitations

- **GitHub rate limits.** The app calls the GitHub Search API. Without a `GITHUB_TOKEN` that is about 10 requests per minute (30 with one). A domain tab costs 4 requests and a GitHub search costs 2, so clicking through many tabs quickly shows a "rate limit" error.
- **The live demo shares one limit.** The Vercel deployment runs without a token, so all visitors share the same limit and may hit rate limits when it is busy. Add a `GITHUB_TOKEN` in the Vercel project settings to raise it.
- **The cache is temporary on Vercel.** Serverless instances can only write to `/tmp`, so cached results are lost on cold starts. Locally, `cache.json` persists for an hour per entry.
- **Results depend on GitHub topics.** Repos are found by their topic tags and a minimum star count, so repos without matching topics won't appear, and the match is not always relevant.
- **Top 100 only.** Each domain or search shows at most the 100 most-starred merged results.
- **First load is slow.** Each tab fetches live data on first click, which takes a few seconds.
