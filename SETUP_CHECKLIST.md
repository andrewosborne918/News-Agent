# Make.com Setup Checklist

Follow these steps in order to set up complete automation with Make.com.

## ☐ Step 1: Create Make.com Account (10 min)
1. Go to https://www.make.com/en/register
2. Sign up for free account
3. Start 14-day free trial
4. Explore the dashboard

**Status**: ⬜ Not started | ⏳ In progress | ✅ Complete

---

## ☐ Step 2: Set Up Google Drive (15 min)

### Create Service Account
1. Go to https://console.cloud.google.com/
2. Create project: "make-news-automation"
3. Enable Google Drive API
4. Create service account: "make-integration"
5. Download JSON key file

### Create Drive Folder
1. Go to https://drive.google.com/
2. Create folder: "News Videos"
3. Share with service account email (from JSON)
4. Copy folder ID from URL

### Add to GitHub
1. Encode JSON: `cat service-account.json | base64 | tr -d '\n'`
2. GitHub → Settings → Secrets → New secret
3. Name: `GOOGLE_DRIVE_FOLDER_ID` (paste folder ID)
4. Name: `GOOGLE_SERVICE_ACCOUNT_JSON_B64` (paste encoded JSON)

**Status**: ⬜ Not started | ⏳ In progress | ✅ Complete

---

## ☐ Step 3: Create Make.com Scenario (20 min)

### Create Scenario
1. Make.com → Scenarios → Create new scenario
2. Name: "News Video Auto-Poster"

### Add Modules (in order)
1. **Webhook** → Custom webhook → Create webhook → Copy URL
2. **Google Drive** → Download file → File ID: `{{1.video.id}}`
3. **Facebook** → Create Post → Connect account → Configure
4. **YouTube** → Upload Video → Connect account → Configure  
5. **TikTok** → Upload Video → Connect account → Configure

### Save & Activate
1. Test with dummy data
2. Save scenario
3. Toggle to "ON"

### Add Webhook to GitHub
1. Copy webhook URL from Make.com
2. GitHub → Settings → Secrets → New secret
3. Name: `MAKE_WEBHOOK_URL`
4. Value: Paste webhook URL

**Status**: ⬜ Not started | ⏳ In progress | ✅ Complete

---

## ☐ Step 4: Connect Social Media Accounts (10 min)

### Facebook
- Sign in with Facebook
- Authorize Make.com
- Select your Facebook Page

### YouTube  
- Sign in with Google
- Authorize Make.com
- Select your channel

### TikTok
- Sign in with TikTok
- Authorize Make.com
- Grant upload permissions

**Status**: ⬜ Not started | ⏳ In progress | ✅ Complete

---

## ☐ Step 5: Test the System (15 min)

### Manual GitHub Actions Test
1. GitHub → Actions → Daily News Video Generator
2. Click "Run workflow"
3. Monitor the run
4. Check for errors

### Verify Upload
1. Check Google Drive "News Videos" folder
2. Verify video + caption.json appear
3. Check Make.com execution history

### Verify Posts
1. Check Facebook page
2. Check YouTube channel (Shorts)
3. Check TikTok profile

**Status**: ⬜ Not started | ⏳ In progress | ✅ Complete

---

## ☐ Step 6: Monitor First Scheduled Run

Wait for next scheduled time:
- 6:00 AM EST
- 9:00 AM EST  
- 12:00 PM EST
- 3:00 PM EST
- 6:00 PM EST

Check that automation works without manual trigger.

**Status**: ⬜ Not started | ⏳ In progress | ✅ Complete

---

## ☐ Step 7: Upgrade to Paid Plan (After Trial)

After 14-day trial:
1. Make.com → Settings → Subscription
2. Select "Core" plan ($9/month)
3. Enter payment details
4. Activate subscription

**Status**: ⬜ Not started | ⏳ In progress | ✅ Complete

---

## Troubleshooting

### Issue: Webhook not triggering
**Solution**: 
- Verify `MAKE_WEBHOOK_URL` in GitHub secrets
- Check Make.com scenario is "ON"
- Test webhook manually with curl

### Issue: Google Drive upload fails
**Solution**:
- Verify service account has Editor access
- Check `GOOGLE_DRIVE_FOLDER_ID` is correct
- Re-share folder with service account

### Issue: Social media post fails
**Solution**:
- Re-authorize account in Make.com
- Check video format/size limits
- Verify account permissions

---

## Success Criteria

✅ GitHub Actions runs successfully  
✅ Video uploads to Google Drive  
✅ Make.com webhook triggers  
✅ Posts appear on Facebook  
✅ Posts appear on YouTube (Shorts)  
✅ Posts appear on TikTok  
✅ Automation runs 5x daily on schedule  

---

## Resources

- **Detailed Guide**: See `MAKE_SETUP_GUIDE.md`
- **Make.com Help**: https://www.make.com/en/help
- **Support**: help@make.com

---

## Total Time: ~1 hour 10 minutes

Once complete, you'll have **fully automated** video posting to all platforms! 🎉

---

## Current Status

**Last Updated**: _______________

**Overall Progress**: ⬜⬜⬜⬜⬜⬜⬜ (0/7 steps complete)

**Notes**:
_______________________________________________________
_______________________________________________________
_______________________________________________________
