# Redeploy Cloud Function with Facebook Fix

## The Fix
Updated the Cloud Function to pass the title to Facebook so videos have proper text content instead of "No text content".

## Redeploy Steps

### Option 1: In Cloud Shell Editor (Recommended)

1. Open Cloud Shell: https://shell.cloud.google.com
2. Navigate to your function directory:
```bash
cd ~/cloud-function
```

3. Edit `main.py` and make these changes:

**Change 1:** Update the function signature (around line 159):
```python
def _upload_facebook(filepath: str, title: str, description: str) -> str:
    """Upload video to Facebook Page"""
    print(f"Uploading to Facebook")
    
    page_id = _get_secret("FB_PAGE_ID")
    token = _get_secret("FB_PAGE_TOKEN")
    
    # Facebook Graph API endpoint for video upload
    url = f"https://graph-video.facebook.com/v19.0/{page_id}/videos"
    
    # Create a formatted message with title and description
    message = f"{title}\n\n{description}" if title and description else (title or description or "Daily news update")
    
    # Upload video file
    with open(filepath, "rb") as video_file:
        response = requests.post(
            url,
            data={
                "access_token": token,
                "description": message  # Facebook uses "description" field for the post text
            },
            files={"source": video_file},
            timeout=300  # 5 minute timeout for large files
        )
    
    response.raise_for_status()
    video_id = response.json().get("id")
    
    print(f"✅ Facebook upload complete: Video ID {video_id}")
    
    return video_id
```

**Change 2:** Update the function call (around line 268):
```python
fb_video_id = _upload_facebook(local_path, title, description)
```

4. Save the file (Ctrl+S)

5. Redeploy:
```bash
gcloud functions deploy gcs_to_social \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=gcs_to_social \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=news-videos-1762459809" \
  --memory=512MB \
  --timeout=540s \
  --set-env-vars=GCP_PROJECT=news-automation-477419
```

### Option 2: Copy Updated File

Or simply copy the updated main.py to Cloud Shell:

```bash
# In Cloud Shell
cd ~/cloud-function
cloudshell edit main.py
# Then paste the updated content from your local file
```

## After Redeployment

Test with a new video upload:
```bash
# Trigger GitHub Actions to generate a new video
gh workflow run "News Agent (politics)" --ref main
```

Or wait for the next scheduled run at 12:00 PM EST (5:00 PM UTC).

The next Facebook post should have the proper title and description! 🎉
