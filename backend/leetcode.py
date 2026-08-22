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
