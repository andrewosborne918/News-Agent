# Fix Facebook Token Issue

## Problem
Your Facebook access token has been invalidated with error:
```
Error validating access token: The session has been invalidated because the user changed their password or Facebook has changed the session for security reasons.
```

## Solution: Generate a New Page Access Token

### Step 1: Get a Long-Lived User Access Token

1. Go to [Facebook Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Select your app from the dropdown
3. Click "Generate Access Token"
4. Select the following permissions:
   - `pages_show_list`
   - `pages_manage_posts`
   - `pages_read_engagement`
   - `pages_manage_metadata` (for video uploads)
   - `publish_video`
5. Copy the generated token (this is a SHORT-LIVED user token)

### Step 2: Exchange for Long-Lived User Token

Run this command (replace `YOUR_SHORT_LIVED_TOKEN`, `YOUR_APP_ID`, and `YOUR_APP_SECRET`):

```bash
curl -G "https://graph.facebook.com/v19.0/oauth/access_token" \
  -d "grant_type=fb_exchange_token" \
  -d "client_id=YOUR_APP_ID" \
  -d "client_secret=YOUR_APP_SECRET" \
  -d "fb_exchange_token=YOUR_SHORT_LIVED_TOKEN"
```

This returns a long-lived user token (valid ~60 days).

### Step 3: Get Your Page Access Token

Run this command with your long-lived user token:

```bash
curl "https://graph.facebook.com/v19.0/me/accounts?access_token=YOUR_LONG_LIVED_USER_TOKEN"
```

This returns a JSON list of your pages. Find your page and copy its `access_token` field. This is your **Page Access Token**.

Example output:
```json
{
  "data": [
    {
      "access_token": "EAAxxxxxxxxxxxxxxxxxxxxx",  // <-- This is your PAGE TOKEN
      "category": "News & Media Website",
      "name": "Your Page Name",
      "id": "842125228986344",
      "tasks": ["ANALYZE", "ADVERTISE", "MODERATE", "CREATE_CONTENT"]
    }
  ]
}
```

### Step 4: Test the Token

```bash
# Validate the token
curl "https://graph.facebook.com/debug_token?input_token=YOUR_PAGE_TOKEN&access_token=YOUR_APP_ID|YOUR_APP_SECRET"

# Test a simple upload (use a small test video)
curl -F "file=@test.mp4" \
     -F "description=Test upload" \
     -F "access_token=YOUR_PAGE_TOKEN" \
     "https://graph-video.facebook.com/v19.0/842125228986344/videos"
```

### Step 5: Update Secret Manager

Update the secret in Google Cloud:

```bash
# Update the FB_PAGE_TOKEN secret
echo -n "YOUR_NEW_PAGE_TOKEN" | gcloud secrets versions add FB_PAGE_TOKEN --data-file=-
```

### Step 6: Redeploy Cloud Function (if needed)

If the secret isn't automatically picked up:

```bash
cd uploader
gcloud functions deploy gcs-to-social \
  --gen2 \
  --region=us-central1 \
  --runtime=python311 \
  --source=. \
  --entry-point=gcs_to_social \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=news-videos-1762459809" \
  --timeout=540s \
  --memory=1GiB
```

## Alternative: Use a System User Token (Recommended for Production)

For a **permanent** token that never expires:

1. Go to [Meta Business Suite](https://business.facebook.com/)
2. Navigate to: Business Settings → Users → System Users
3. Click "Add" to create a new System User
4. Assign the user to your app with the necessary permissions
5. Generate a token for the System User
6. Grant the System User access to your Page (in Page settings)
7. Use this token as your `FB_PAGE_TOKEN`

System User tokens don't expire and are more reliable for automated workflows.

## Verification

After updating the token, trigger the Cloud Function again. You should see in the logs:

```
Facebook token preflight...
FB token valid: True | Granted perms: ['pages_manage_posts', 'pages_read_engagement', 'publish_video', ...]
✅ Facebook upload complete: Video ID xxxxx
```

## Troubleshooting

### "Missing required permissions"
Re-generate the token with ALL required scopes checked in Graph API Explorer.

### "Invalid OAuth access token"
Make sure you're using the PAGE token, not the USER token. The Page token comes from the `/me/accounts` endpoint.

### "Permissions error" when posting
The Page token must have `publish_video` scope AND the app must be in Production mode (or you must be a tester/admin).

### Token keeps expiring
Use a System User token instead of a regular user token for permanent access.
