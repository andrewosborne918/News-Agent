# Check Facebook Posting Logs

## To check why Facebook posting isn't working, run these commands in Google Cloud Shell:

### 1. View recent Cloud Function logs
```bash
gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=100
```

### 2. Filter for Facebook-related errors
```bash
gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=100 | grep -A 10 -B 5 "Facebook\|FB_PAGE"
```

### 3. Check for any errors in the last execution
```bash
gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=50 | grep -i "error\|exception\|failed"
```

### 4. View just the most recent function execution
```bash
gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=20
```

## Common Facebook Issues:

### Issue 1: Token Expired
If you see "OAuthException" or "token expired", the Facebook Page Access Token needs to be refreshed.

**Fix:**
1. Go to https://developers.facebook.com/tools/explorer/
2. Select your app "News Automation"
3. Get User Access Token with permissions: `pages_manage_posts`, `pages_read_engagement`, `publish_video`, `pages_show_list`
4. Convert to Page Token:
```bash
curl -X GET "https://graph.facebook.com/v19.0/me/accounts?access_token=YOUR_USER_TOKEN"
```
5. Update secret in Cloud Shell:
```bash
echo -n "NEW_PAGE_TOKEN" | gcloud secrets versions add FB_PAGE_TOKEN --data-file=-
```

### Issue 2: Video Format/Size
Facebook has video requirements:
- Max file size: 10GB
- Min resolution: 720p recommended
- Aspect ratio: 9:16 for Reels (vertical)

### Issue 3: Permissions
Check if the Page Access Token has the right permissions:
```bash
curl "https://graph.facebook.com/v19.0/me/permissions?access_token=YOUR_PAGE_TOKEN"
```

Should show:
- `pages_manage_posts`: granted
- `pages_read_engagement`: granted
- `publish_video`: granted

## Debug Mode

To see detailed Facebook API responses, check the logs right after uploading:
```bash
# Upload a test video
gcloud storage cp test.mp4 gs://news-videos-1762459809/incoming/

# Wait 30 seconds, then check logs
sleep 30
gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=30
```
