from google_auth_oauthlib.flow import InstalledAppFlow

# Replace with your own OAuth credentials file
flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json",  # downloaded from Google Cloud
    scopes=["https://www.googleapis.com/auth/youtube.force-ssl"]
)

credentials = flow.run_local_server(port=0)

print("Access token:", credentials.token)
print("Refresh token:", credentials.refresh_token)

