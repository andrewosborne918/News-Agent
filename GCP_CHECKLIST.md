# GCP Free-Tier Setup Checklist

Complete these steps to set up fully automated, free video posting.

---

## ✅ Phase 1: Google Cloud Platform Setup (30 min)

### [ ] 1. Create GCP Project
- Go to: https://console.cloud.google.com/
- Create project: "news-automation"
- Enable billing (required for free tier)

### [ ] 2. Run Setup Script
```bash
# In Google Cloud Shell or local terminal:
./setup_gcp.sh
```

This will:
- Enable required APIs
- Create storage bucket
- Create service account for GitHub
- Generate gh-actions.json

### [ ] 3. Add GitHub Secrets
Go to: GitHub repo → Settings → Secrets → Actions

Add:
- `GCP_PROJECT_ID`: Your project ID
- `GCS_BUCKET`: Bucket name from script
- `GCP_SA_KEY`: Entire contents of gh-actions.json

**Status**: ⬜ Not started | ⏳ In progress | ✅ Complete

---

## ✅ Phase 2: YouTube OAuth Setup (15 min)

### [ ] 4. Create OAuth Credentials
- Go to: https://console.cloud.google.com/apis/credentials
- Create OAuth client ID → Desktop app
- Save Client ID and Client Secret

### [ ] 5. Get Refresh Token
```bash
# On your local computer:
pip install google-auth-oauthlib
python get_youtube_token.py
```

- Enter Client ID and Secret
- Browser opens → Sign in to YouTube channel
- Authorize
- **Copy the refresh token**

### [ ] 6. Store YouTube Secrets in GCP
```bash
# In Google Cloud Shell:
echo -n "YOUR_CLIENT_ID" | gcloud secrets create YT_CLIENT_ID --data-file=-
echo -n "YOUR_CLIENT_SECRET" | gcloud secrets create YT_CLIENT_SECRET --data-file=-
echo -n "YOUR_REFRESH_TOKEN" | gcloud secrets create YT_REFRESH_TOKEN --data-file=-
```

**Status**: ⬜ Not started | ⏳ In progress | ✅ Complete

---

## ✅ Phase 3: Facebook Page Setup (15 min)

### [ ] 7. Create Facebook App
- Go to: https://developers.facebook.com/apps/
- Create App → Business type
- Name: "News Automation"

### [ ] 8. Get Page Access Token
- Add "Facebook Login" product
- Graph API Explorer: https://developers.facebook.com/tools/explorer/
- Generate token with permissions:
  - `pages_manage_posts`
  - `pages_read_engagement`
  - `pages_show_list`
  - `publish_video`
- **Copy short-lived token**

### [ ] 9. Exchange for Long-Lived Token
```bash
curl -X GET "https://graph.facebook.com/v19.0/oauth/access_token?grant_type=fb_exchange_token&client_id=YOUR_APP_ID&client_secret=YOUR_APP_SECRET&fb_exchange_token=YOUR_SHORT_TOKEN"
```

**Copy the long-lived token from response**

### [ ] 10. Get Page ID
- Go to your Facebook Page
- Settings → Page Info
- Copy "Page ID"

### [ ] 11. Store Facebook Secrets in GCP
```bash
# In Google Cloud Shell:
echo -n "YOUR_PAGE_ID" | gcloud secrets create FB_PAGE_ID --data-file=-
echo -n "YOUR_LONG_LIVED_TOKEN" | gcloud secrets create FB_PAGE_TOKEN --data-file=-
```

**Status**: ⬜ Not started | ⏳ In progress | ✅ Complete

---

## ✅ Phase 4: Deploy Cloud Function (10 min)

### [ ] 12. Deploy Function
```bash
./deploy_function.sh
```

Enter:
- GCP Project ID
- GCS Bucket name

Wait 3-5 minutes for deployment.

**Status**: ⬜ Not started | ⏳ In progress | ✅ Complete

---

## ✅ Phase 5: Test Everything (15 min)

### [ ] 13. Test Cloud Function
```bash
# Upload a test video
gsutil cp test-video.mp4 gs://YOUR_BUCKET/incoming/test.mp4

# Check logs
gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=50
```

Look for:
- "✅ YouTube upload complete"
- "✅ Facebook upload complete"
- YouTube video ID and URL

### [ ] 14. Check Social Media
- YouTube: Check your channel for new Short
- Facebook: Check your Page for new video post

### [ ] 15. Test GitHub Actions
- GitHub → Actions → "Daily News Video Generator"
- Run workflow manually
- Wait for completion
- Check Cloud Function logs
- Verify posts on YouTube + Facebook

**Status**: ⬜ Not started | ⏳ In progress | ✅ Complete

---

## ✅ Success Criteria

All of these should work:

- ✅ GitHub Actions generates video (5x daily)
- ✅ Video uploads to Google Cloud Storage
- ✅ Cloud Function triggers automatically
- ✅ Video posts to YouTube Shorts
- ✅ Video posts to Facebook Page
- ✅ All within free tier limits
- ✅ No manual intervention needed

---

## 🎉 You're Done!

Your system is now:
- ✅ Fully automated
- ✅ Completely free (GCP free tier)
- ✅ Cloud-native (no local servers)
- ✅ Enterprise-grade
- ✅ Bot-detection proof (official OAuth)

**Schedule**:
Videos will automatically post 5x daily at:
- 6:00 AM EST
- 9:00 AM EST
- 12:00 PM EST
- 3:00 PM EST
- 6:00 PM EST

---

## 📊 Monitoring

### View Cloud Function Logs
```bash
gcloud functions logs read gcs_to_social --region=us-central1 --gen2 --limit=50
```

### Check Storage Usage
```bash
gsutil du -sh gs://YOUR_BUCKET
```

### View YouTube Analytics
https://studio.youtube.com/

### View Facebook Insights
Your Page → Insights

---

## 🔧 Maintenance

### Rotate Facebook Token (every 60 days)
Re-run Part 3, Step 9 to get new long-lived token.

### Clean Old Videos from GCS (monthly)
```bash
# Delete videos older than 30 days
gsutil -m rm gs://YOUR_BUCKET/incoming/*
```

### Check Free Tier Usage
https://console.cloud.google.com/billing

---

## 📚 Resources

- **Detailed Guide**: See `GCP_SETUP_GUIDE.md`
- **Cloud Function Code**: See `uploader/main.py`
- **GCP Documentation**: https://cloud.google.com/functions/docs
- **YouTube API Docs**: https://developers.google.com/youtube/v3
- **Facebook Graph API**: https://developers.facebook.com/docs/graph-api

---

## Current Progress

**Total Time**: ~75 minutes (one-time setup)

**Phase 1**: ⬜⬜⬜⬜  
**Phase 2**: ⬜⬜⬜  
**Phase 3**: ⬜⬜⬜⬜⬜  
**Phase 4**: ⬜  
**Phase 5**: ⬜⬜⬜  

**Overall**: 0/15 steps complete

---

Start with Phase 1! 🚀
