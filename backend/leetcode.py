import httpx

LEETCODE_URL = "https://leetcode.com/graphql"

# The GraphQL query: "for this username, give me solved counts by difficulty."
QUERY = """
query getStats($username: String!) {
  matchedUser(username: $username) {
    submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
      }
    }
  }
}
"""

def fetch_leetcode_stats(username):
    resp = httpx.post(LEETCODE_URL, json={"query": QUERY, "variables": {"username": username}})
    profile = resp.json()
    cleanDict = {}
    submissions = profile["data"]["matchedUser"]["submitStatsGlobal"]["acSubmissionNum"]
    for p in submissions:
        cleanDict[p["difficulty"]] = p["count"]
    return cleanDict


# Look up a single problem by its URL slug (e.g. "two-sum"). Used to VERIFY that a
# slug the AI suggested is a real problem before we link to it — the model can
# invent plausible-looking slugs that 404.
PROBLEM_QUERY = """
query getProblem($slug: String!) {
  question(titleSlug: $slug) {
    title
    difficulty
  }
}
"""

def fetch_problem(slug):
    try:
        resp = httpx.post(LEETCODE_URL, json={"query": PROBLEM_QUERY, "variables": {"slug": slug}})
        question = resp.json().get("data", {}).get("question")
    except Exception:
        return None
    if not question:
        return None   # slug doesn't exist → don't trust the AI's link
    return {"title": question["title"], "difficulty": question["difficulty"].lower()}


# The user's most recent accepted submissions. LeetCode only exposes the latest
# ~20 publicly (no full "solved history"), so this catches problems solved recently
# or from now on — used to auto-complete specific-problem tasks.
RECENT_QUERY = """
query recentAc($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    titleSlug
  }
}
"""

def fetch_recent_solves(username, limit=20):
    try:
        resp = httpx.post(LEETCODE_URL, json={"query": RECENT_QUERY,
                                              "variables": {"username": username, "limit": limit}})
        subs = resp.json().get("data", {}).get("recentAcSubmissionList") or []
    except Exception:
        return set()
    return {s["titleSlug"] for s in subs}
