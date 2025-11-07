# Fix YouTube Upload Limit Exceeded

## Problem
You're seeing this error:
```
The user has exceeded the number of videos they may upload.
uploadLimitExceeded
```

This is **NOT** an API quota issue. It's your YouTube channel's upload limit.

## Root Causes

### 1. Unverified Channel (Most Common)
New or unverified YouTube channels have strict upload limits:
- **6 uploads per 24 hours** for unverified channels
- **Unlimited uploads** for verified channels

### 2. Recent Account Creation
Brand new channels may have additional restrictions for the first few weeks.

### 3. Trust Score
YouTube may limit uploads if the channel has received strikes or violations.

## Solutions

### Solution 1: Verify Your YouTube Channel (RECOMMENDED)

This is the quickest fix:

1. Go to [YouTube Studio](https://studio.youtube.com)
2. Click on your profile icon → Settings
3. Navigate to "Channel" → "Feature eligibility"
4. Look for "Intermediate features" or "Advanced features"
5. Click **"Verify"** next to phone verification
6. Follow the steps to verify via SMS or voice call
7. **Wait 10-15 minutes** after verification

After verification, you should be able to upload without daily limits.

### Solution 2: Rate Limit Your Uploads

If you need to upload multiple videos per day, space them out:

**Current implementation already includes basic rate limiting**, but you can enhance it:

#### Option A: Limit uploads per hour
```python
# In your workflow, add a delay between video generation
# Example: Only generate 1 video every 2 hours
```

#### Option B: Track uploads in Firestore
```python
from google.cloud import firestore
from datetime import datetime, timedelta

def check_upload_quota():
    """Return True if we can upload, False if we should wait"""
    db = firestore.Client()
    today = datetime.now().date()
    
    # Count uploads today
    uploads_ref = db.collection('youtube_uploads')
    today_uploads = uploads_ref.where('date', '==', today).stream()
    count = sum(1 for _ in today_uploads)
    
    MAX_DAILY_UPLOADS = 5  # Conservative limit
    return count < MAX_DAILY_UPLOADS

def record_upload(video_id):
    """Record successful upload"""
    db = firestore.Client()
    db.collection('youtube_uploads').add({
        'video_id': video_id,
        'date': datetime.now().date(),
        'timestamp': datetime.now()
    })
```

### Solution 3: Queue System for Retry

Instead of failing, queue videos for retry:

```python
# In uploader/main.py, modify the YouTube upload section:

try:
    yt_video_id = _upload_youtube(local_path, title, description, tags)
    yt_success = True
except Exception as yt_err:
    err_text = str(yt_err)
    if "uploadLimitExceeded" in err_text or "exceeded the number of videos" in err_text:
        # Move file to a "retry" folder instead of processing
        retry_blob_name = blob_name.replace("incoming/", "retry_tomorrow/")
        client = storage.Client()
        bucket_obj = client.bucket(bucket)
        source_blob = bucket_obj.blob(blob_name)
        bucket_obj.copy_blob(source_blob, bucket_obj, retry_blob_name)
        print(f"✅ Moved to retry queue: {retry_blob_name}")
        # Also copy the metadata JSON
        meta_blob_name = blob_name.replace(".mp4", ".json")
        meta_blob = bucket_obj.blob(meta_blob_name)
        if meta_blob.exists():
            retry_meta_name = retry_blob_name.replace(".mp4", ".json")
            bucket_obj.copy_blob(meta_blob, bucket_obj, retry_meta_name)
```

Then set up a daily Cloud Scheduler job to move retry videos back to incoming/:

```bash
# Create a Cloud Scheduler job that runs daily
gcloud scheduler jobs create http retry-youtube-uploads \
  --schedule="0 2 * * *" \
  --uri="YOUR_RETRY_FUNCTION_URL" \
  --http-method=POST \
  --location=us-central1
```

## Current State of Your Code

The updated `uploader/main.py` now includes:

✅ **Better error detection** - Catches both `HttpError` and `ResumableUploadError`  
✅ **Clear error messages** - Tells you exactly what to do when limit is hit  
✅ **Graceful degradation** - Continues to Facebook even if YouTube fails  
✅ **Detailed logging** - Shows which platform succeeded/failed  

## Immediate Actions

### 1. Verify Your Channel (Do this NOW)
This takes 5 minutes and solves 90% of upload limit issues.

### 2. Check Current Upload Count
```bash
# See how many uploads happened today
gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=500 | \
  grep "YouTube upload complete" | \
  grep "$(date +%Y-%m-%d)" | \
  wc -l
```

### 3. Space Out Uploads
If you're generating videos with a scheduler:
- Change from hourly to every 2-3 hours
- Or generate videos but upload only 4-5 per day

### 4. Deploy Updated Code
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

## Expected Behavior After Fix

Once you verify your channel and deploy the updated code:

### Success case:
```
Uploading to YouTube: Your Video Title
Upload 16% complete
Upload 33% complete
...
✅ YouTube upload complete: https://youtube.com/shorts/abc123
```

### Limit exceeded case (with helpful guidance):
```
⚠️ YouTube upload limit exceeded.
   Action needed:
   1. Verify your YouTube channel (phone verification in YouTube Studio)
   2. Wait 24 hours before uploading more videos
   3. Consider rate-limiting uploads to avoid hitting this limit
   Continuing with Facebook upload...
```

## Monitoring

Add this to your monitoring:

```bash
# Daily report of upload success rate
gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=200 | \
  grep -E "YouTube upload complete|upload limit exceeded" | \
  head -20
```

## FAQ

**Q: Will verification remove all limits?**  
A: Yes, verified channels can upload unlimited videos per day.

**Q: How long does verification take?**  
A: Immediate. You enter a phone number, get a code, enter it, and you're verified.

**Q: Can I verify multiple channels?**  
A: Yes, but each needs its own phone number.

**Q: What if I already verified but still hit limits?**  
A: Check your channel status in YouTube Studio. If verified, you may have hit a different limit (strikes/violations). Contact YouTube support.

**Q: Is there an API quota separate from upload limits?**  
A: Yes, but that's different. API quota errors say "quotaExceeded", not "uploadLimitExceeded".
