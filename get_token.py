import google.auth.transport.requests
from google_auth_oauthlib.flow import InstalledAppFlow

# --- PASTE YOUR CLIENT ID AND SECRET HERE ---
CLIENT_ID = "222876473651-329tuklvaieglo8q5t7ma0rp2cluguml.apps.googleusercontent.com"
CLIENT_SECRET = "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"
# ---

SCOPES = ['https://www.googleapis.com/auth/drive']

def main():
    flow = InstalledAppFlow.from_client_config(
        {"web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }},
        SCOPES
    )

    # This will print a URL. Open it in your browser.
    creds = flow.run_local_server(port=8080)

    print("\n--- YOUR CREDENTIALS ---")
    print(f"Refresh Token: {creds.refresh_token}")
    print("\n---")
    print("COPY THIS REFRESH TOKEN. You will need it for your GitHub Secret.")

if __name__ == "__main__":
    main()