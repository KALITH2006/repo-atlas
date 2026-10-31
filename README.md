# Repo Atlas

Repo Atlas helps you discover popular GitHub repositories by field, without digging through GitHub yourself.

## What it does

- **Browse by domain.** Twelve ready-made categories: AI, Machine Learning, Data Science, Cybersecurity, Automobile, Web Dev, DevOps & Cloud, Blockchain, IoT & Embedded, Robotics, Game Dev and Mobile. Each shows the most-starred repositories in that field.
- **Search any topic or framework.** Type something like `fastapi` or `langchain` and press Enter to pull matching repositories straight from GitHub.
- **Filter and sort.** Narrow results by name, description or programming language, and sort by stars, forks or most recent activity.
- **Export.** Download the filtered list as a CSV file.
- **Live and reliable data.** Results come from the official GitHub Search API, so they stay accurate when GitHub changes. Recent results are cached for an hour, and if GitHub is temporarily limiting requests, the last saved results are shown instead of an error.

Each repository card shows its owner, description, language, topics, star and fork counts, and when it was last updated, with a direct link to the repo on GitHub.

## How results are chosen

Each domain maps to several GitHub topics (for example, Automobile covers `autonomous-driving`, `self-driving-car`, `automotive` and `can-bus`). Repo Atlas fetches the top repositories for each topic, merges them, removes duplicates and ranks them by stars.

## Known limitations

- **GitHub rate limits.** GitHub allows only a limited number of searches per minute, so clicking through many tabs very quickly can show a "rate limit" message. Saved results are shown when possible.
- **Results depend on GitHub topics.** Repositories are found by their topic tags and a minimum star count, so repos without matching topics won't appear, and matches aren't always perfectly relevant.
- **Top 100 only.** Each domain or search shows at most the 100 most-starred results.
- **Slower first load.** A tab fetches live data the first time you open it, which takes a few seconds.
