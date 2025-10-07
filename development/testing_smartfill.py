# oauth_related_test.py
import os
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Files
CLIENT_SECRETS_FILE = "client_secret.json"   # from Google Cloud Console (Desktop app)
TOKEN_FILE = "token.json"

# Scopes
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

# Helpers for OAuth
def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            return creds
        except Exception as e:
            print("Could not refresh token:", e)

    # Need to run auth flow
    if not os.path.exists(CLIENT_SECRETS_FILE):
        print(f"Missing {CLIENT_SECRETS_FILE}. Create OAuth client (Desktop) in Google Cloud Console and save it here.")
        raise SystemExit(1)

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)  # opens browser for user to sign in
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    return creds

# Call YouTube Data API (authorized)
def youtube_search_authorized(query, creds, max_results=6):
    url = "https://www.googleapis.com/youtube/v3/search"
    headers = {"Authorization": f"Bearer {creds.token}"}
    params = {
        "part": "snippet",
        "type": "video",
        "q": query,
        "maxResults": max_results,
    }
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    out = []
    for it in data.get("items", []):
        vid = it["id"].get("videoId")
        title = it["snippet"]["title"]
        out.append({"id": vid, "title": title})
    return out

def fetch_related_oauth(video_id, creds, max_results=10):
    url = "https://www.googleapis.com/youtube/v3/search"
    headers = {"Authorization": f"Bearer {creds.token}"}
    params = {
        "part": "snippet",
        "type": "video",
        "relatedToVideoId": video_id,
        "maxResults": max_results,
    }
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    out = []
    for it in data.get("items", []):
        vid = it["id"].get("videoId")
        title = it["snippet"]["title"]
        out.append({"id": vid, "title": title})
    return out

# CLI flow
if __name__ == "__main__":
    creds = get_credentials()
    # ensure token is fresh
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    query = input("Enter search query: ").strip()
    if not query:
        print("No query given.")
        raise SystemExit(1)

    try:
        results = youtube_search_authorized(query, creds, max_results=6)
    except requests.HTTPError as e:
        print("Search failed:", e.response.text)
        raise SystemExit(1)

    if not results:
        print("No search results.")
        raise SystemExit(0)

    print("\nSearch results:")
    for i, r in enumerate(results):
        print(f"[{i}] {r['title']} — https://www.youtube.com/watch?v={r['id']}")

    choice = input("\nChoose index for smart-fill (number): ").strip()
    if not choice.isdigit() or int(choice) >= len(results):
        print("Invalid choice.")
        raise SystemExit(1)

    chosen = results[int(choice)]
    print(f"\nSelected: {chosen['title']} ({chosen['id']})\n")

    # Fetch related using OAuth (this should work)
    try:
        recs = fetch_related_oauth(chosen["id"], creds, max_results=10)
    except requests.HTTPError as e:
        print("Related fetch failed:", e.response.text)
        raise SystemExit(1)

    if not recs:
        print("No related videos returned.")
    else:
        print("Related (YouTube recommendations):")
        for i, r in enumerate(recs, 1):
            print(f"{i}. {r['title']} — https://www.youtube.com/watch?v={r['id']}")

