# Quick Fix Checklist ✅

## The Problem
- ❌ YouTube: Upload limit exceeded (6/day max for unverified channels)
- ❌ Facebook: Token invalid/expired

## The Solution (20 minutes total)

### ☑️ Step 1: Verify YouTube Channel (5 min)
```
1. Go to: https://studio.youtube.com
2. Settings → Channel → Feature eligibility → Verify
3. Complete phone verification
4. Wait 10-15 minutes
```
**Result**: Unlimited uploads per day

---

### ☑️ Step 2: Fix Facebook Token (10 min)

#### A. Get Page Token
```bash
# 1. Graph API Explorer (https://developers.facebook.com/tools/explorer/)
#    Select app → Generate Token → Select permissions:
#    - pages_show_list
#    - pages_manage_posts  
#    - pages_read_engagement
#    - pages_manage_metadata
#    - publish_video

# 2. Exchange for long-lived token
curl -G "https://graph.facebook.com/v19.0/oauth/access_token" \
  -d "grant_type=fb_exchange_token" \
  -d "client_id=YOUR_APP_ID" \
  -d "client_secret=YOUR_APP_SECRET" \
  -d "fb_exchange_token=YOUR_SHORT_TOKEN"

# 3. Get Page token
curl "https://graph.facebook.com/v19.0/me/accounts?access_token=YOUR_LONG_TOKEN"

# Copy the "access_token" from your page
```

#### B. Update Secret
```bash
# In Google Cloud Shell:
echo -n "YOUR_PAGE_TOKEN" | gcloud secrets versions add FB_PAGE_TOKEN --data-file=-
```

---

### ☑️ Step 3: Deploy Updated Code (5 min)

**From Google Cloud Shell:**
```bash
cd ~/News-Agent
./deploy_updated_function.sh
```

**Or manually:**
```bash
cd ~/News-Agent/uploader
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

---

### ☑️ Step 4: Test (5 min)

```bash
# Upload a test video
gsutil cp test.mp4 gs://news-videos-1762459809/incoming/

# Check logs
gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=20
```

**Look for:**
- ✅ `YouTube upload complete`
- ✅ `Facebook upload complete`  
- ✅ `COMPLETE SUCCESS!`

---

## Quick Verification

### YouTube Channel Verified?
```
Go to https://studio.youtube.com
→ Settings → Channel → Status
Should show: "Phone verified ✓"
```

### Facebook Token Valid?
```bash
curl "https://graph.facebook.com/debug_token?\
input_token=YOUR_TOKEN&\
access_token=YOUR_APP_ID|YOUR_APP_SECRET"
```
Look for: `"is_valid": true`

---

## What Changed in the Code

✅ Catches YouTube upload limit errors gracefully  
✅ Validates Facebook token before upload  
✅ Continues to Facebook even if YouTube fails  
✅ Better error messages with actionable steps  
✅ Detailed success/failure tracking per platform  

---

## Expected Behavior After Fix

### Full Success:
```
✅ YouTube upload complete: https://youtube.com/shorts/abc123
✅ Facebook upload complete: Video ID 987654
✅ COMPLETE SUCCESS! (Both platforms)
```

### Partial Success (if limit still hit):
```
⚠️ YouTube upload limit exceeded.
✅ Facebook upload complete: Video ID 987654
⚠️ PARTIAL SUCCESS (at least one platform succeeded)
```

---

## Need More Details?

📖 **FIX_YOUTUBE_LIMITS.md** - Complete YouTube guide  
📖 **FIX_FACEBOOK_TOKEN.md** - Complete Facebook guide  
📖 **ERROR_FIX_SUMMARY.md** - Full explanation  

---

## Still Having Issues?

### Check logs:
```bash
gcloud functions logs read gcs_to_social \
  --region=us-central1 --gen2 --limit=50 | less
```

### Verify secrets are set:
```bash
gcloud secrets list
gcloud secrets versions access latest --secret="FB_PAGE_TOKEN"
```

### Check Cloud Function status:
```bash
gcloud functions describe gcs-to-social \
  --region=us-central1 --gen2
```

---

**Priority**: Do Steps 1-3 NOW. Step 4 is testing. Total: 20 minutes. 🚀
