import re
import httpx

GITHUB_API = "https://api.github.com"


def count_repo_commits(full_name, token):
    # Total commits on the repo's default branch.
    #
    # We only want the COUNT, not the commits themselves. Trick: ask for one
    # commit per page. GitHub then adds a "Link" response header pointing at the
    # LAST page — and at 1 commit per page, the last page number IS the total
    # commit count. So we learn the count from ONE request instead of paging
    # through the whole history.
    resp = httpx.get(
        f"{GITHUB_API}/repos/{full_name}/commits",
        params={"per_page": 1},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    if resp.status_code != 200:
        # Repo missing/renamed/private-without-access → treat as 0 so detection
        # just doesn't fire (better than crashing the cron for every user).
        return 0

    # Link header looks like:
    #   <...&page=2>; rel="next", <...&page=57>; rel="last"
    # We pull the page number attached to rel="last".
    link = resp.headers.get("Link", "")
    match = re.search(r'[?&]page=(\d+)>;\s*rel="last"', link)
    if match:
        return int(match.group(1))

    # No Link header means there's only one page: either 0 or 1 commits.
    # The body length (0 or 1 items) tells us which.
    return len(resp.json())
