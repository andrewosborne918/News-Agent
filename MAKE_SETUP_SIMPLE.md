# Make.com Setup - SIMPLIFIED (No Google Drive Needed!)

## Overview: Simpler Flow

```
GitHub Actions
    ↓
Sends video directly to Make.com webhook (as base64)
    ↓
Make.com receives video
    ↓
Posts to Facebook/YouTube/TikTok
    ↓
Done! ✅
```

**No Google Drive needed!** Much simpler.

---

## Step-by-Step Setup

### Step 1: Create Make.com Scenario

1. Log in to Make.com
2. Click "Scenarios" → "Create a new scenario"
3. Name it: "News Video Auto-Poster"

### Step 2: Add Webhook (Receives Video)

1. Click the "+" button
2. Search for "Webhooks"
3. Select "Custom webhook"
4. Click "Create a webhook"
5. Webhook name: "news-video-webhook"
6. Click "Save"
7. **COPY THE WEBHOOK URL** - looks like: `https://hook.us1.make.com/abcdef123456`

### Step 3: Add Facebook Module

1. Click "+" after the webhook module
2. Search for "Facebook"
3. Select "Create a Post"
4. Click "Create a connection"
   - Click "Sign in with Facebook"
   - Authorize Make.com
   - Select your Facebook Page
5. Configure:
   - **Page**: Select your page
   - **Message**: `{{1.caption.description}}`
   - **Video**: Click field → select "Map" → enter: `{{base64(1.video.data)}}`
   - **Published**: Yes
6. Click "OK"

### Step 4: Add YouTube Module

1. Click "+" (you can add it parallel to Facebook or after it)
2. Search for "YouTube"
3. Select "Upload a Video"
4. Click "Create a connection"
   - Sign in with Google
   - Authorize Make.com
5. Configure:
   - **Title**: `{{1.caption.title}}`
   - **Description**: `{{1.caption.description}}`
   - **Video**: `{{base64(1.video.data)}}`
   - **Privacy Status**: Public
   - **Category**: 25 (News & Politics)
   - **Tags**: `{{join(1.caption.hashtags; ",")}}`
6. Click "OK"

### Step 5: Add TikTok Module

1. Click "+" (parallel to others)
2. Search for "TikTok"
3. Select "Upload a Video"
4. Click "Create a connection"
   - Sign in with TikTok
   - Authorize Make.com
5. Configure:
   - **Caption**: `{{1.caption.description}} {{join(1.caption.hashtags; " ")}}`
   - **Video**: `{{base64(1.video.data)}}`
   - **Privacy**: Public
6. Click "OK"

### Step 6: Save & Activate

1. Click "Save" at the bottom
2. Toggle the scenario to "ON"
3. Done!

---

## Step 7: Add Webhook URL to GitHub

1. Go to your GitHub repository
2. Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Name: `MAKE_WEBHOOK_URL`
5. Value: Paste the webhook URL from Make.com (step 2 above)
6. Click "Add secret"

---

## Testing

### Test Make.com Scenario

Click "Run once" in Make.com, then in your terminal run:

```bash
# Test the webhook (replace with your webhook URL)
curl -X POST 'YOUR_WEBHOOK_URL' \
  -H 'Content-Type: application/json' \
  -d '{
    "video": {
      "data": "dGVzdA==",
      "filename": "test.mp4"
    },
    "caption": {
      "title": "Test Video",
      "description": "This is a test",
      "hashtags": ["test", "news"]
    }
  }'
```

You should see the data appear in Make.com!

### Test Full Workflow

1. GitHub → Actions → "Daily News Video Generator"
2. Click "Run workflow"
3. Wait for it to complete
4. Check Make.com execution history
5. Check your social media accounts!

---

## Troubleshooting

### "Video data is not valid base64"
- The script handles base64 encoding automatically
- Make sure you're using `{{base64(1.video.data)}}` in Make.com modules

### "File too large"
- Our videos are ~10MB, well within limits
- If GitHub Actions fails, check the video generation step

### Social media post fails
- Re-authorize the connection in Make.com
- Check that your accounts have posting permissions
- Verify video meets platform requirements (< 60s for YouTube Shorts)

---

## What You DON'T Need Anymore

❌ Google Drive folder  
❌ Google Cloud service account  
❌ Google Drive API credentials  
❌ GOOGLE_DRIVE_FOLDER_ID secret  
❌ GOOGLE_SERVICE_ACCOUNT_JSON_B64 secret  

## What You DO Need

✅ Make.com account (free trial, then $9/month)  
✅ MAKE_WEBHOOK_URL in GitHub secrets  
✅ Facebook/YouTube/TikTok accounts connected in Make.com  

---

## Cost

**Still just $9/month** for Make.com Core plan!

---

## Summary

This is **MUCH SIMPLER** than the Google Drive approach:

- ✅ No Google Cloud setup needed
- ✅ No service account JSON files
- ✅ Fewer steps to configure
- ✅ Faster (no upload/download from Drive)
- ✅ Same result - automated posting!

**Your Make.com scenario should have:**
1. Webhook (receives video + caption)
2. Facebook post (or skip if you don't use Facebook)
3. YouTube upload
4. TikTok upload (or skip if you don't use TikTok)

That's it! 🎉
