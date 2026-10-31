# Repo Atlas

Browse popular GitHub repositories by domain (AI, Machine Learning, Cybersecurity, Automobile, Web Dev and more), or search GitHub for any topic or framework.

**Live demo:** _VERCEL_LINK_

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
