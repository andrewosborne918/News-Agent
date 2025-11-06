# Make.com Complete Setup Guide

🎯 **Goal**: Fully automate posting videos to Facebook, YouTube, and TikTok without bot detection

💰 **Cost**: $9/month (Core plan)

⏱️ **Setup Time**: 30-45 minutes

---

## Overview: How It Works

```
GitHub Actions (every 3 hours)
    ↓
Generates video + AI caption
    ↓
Uploads to Google Drive
    ↓
Triggers Make.com webhook
    ↓
Make.com downloads video
    ↓
Posts to Facebook/YouTube/TikTok (via OAuth)
    ↓
You get notifications ✅
```

---

## Part 1: Create Make.com Account

### Step 1: Sign Up
1. Go to: https://www.make.com/en/register
2. Click "Sign up for free"
3. Enter your email and create password
4. Verify your email

### Step 2: Start Free Trial
- Make.com offers a **free trial** (14 days)
- You can test everything before paying
- After trial: $9/month for Core plan (1,000 operations)
- Each video post = ~5 operations, so 200 videos/month

### Step 3: Upgrade to Core Plan (After Trial)
1. Go to: Settings → Subscription
2. Select "Core" plan ($9/month)
3. Enter payment details
4. Activate subscription

**💡 Tip**: Complete setup during free trial to test before paying!

---

## Part 2: Set Up Google Drive Integration

### Step 1: Create Google Cloud Project (If Not Done)
1. Go to: https://console.cloud.google.com/
2. Create new project: "make-news-automation"
3. Enable APIs:
   - Click "APIs & Services" → "Library"
   - Search and enable: **Google Drive API**
   - Search and enable: **Google Sheets API**

### Step 2: Create Service Account
1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "Service Account"
3. Name: "make-integration"
4. Role: "Editor"
5. Click "Done"

### Step 3: Create Service Account Key
1. Click on the service account you just created
2. Go to "Keys" tab
3. Click "Add Key" → "Create new key"
4. Choose JSON format
5. Download the JSON file (keep it safe!)

### Step 4: Create Google Drive Folder
1. Go to: https://drive.google.com/
2. Create new folder: "News Videos"
3. Right-click folder → "Share"
4. Add the service account email (from JSON file, looks like `xxx@yyy.iam.gserviceaccount.com`)
5. Give it "Editor" permission
6. Copy the folder ID from URL:
   ```
   https://drive.google.com/drive/folders/1ABC-XYZ123
                                            ^^^^^^^^^^
                                            This is the ID
   ```

### Step 5: Add to GitHub Secrets
1. Go to your GitHub repository
2. Settings → Secrets and variables → Actions
3. Add these secrets:
   - **GOOGLE_DRIVE_FOLDER_ID**: The folder ID from step 4
   - **GOOGLE_SERVICE_ACCOUNT_JSON_B64**: Base64-encoded JSON file

To encode the JSON file:
```bash
# On Mac/Linux
cat path/to/service-account.json | base64 | tr -d '\n'

# Copy the output and paste as secret value
```

---

## Part 3: Create Make.com Scenario

### Step 1: Create New Scenario
1. Log in to Make.com
2. Click "Scenarios" in sidebar
3. Click "Create a new scenario"
4. Name it: "News Video Auto-Poster"

### Step 2: Add Webhook Trigger
1. Click the "+" button
2. Search for "Webhooks"
3. Select "Custom webhook"
4. Click "Create a webhook"
5. Webhook name: "news-video-upload"
6. Click "Save"
7. **COPY THE WEBHOOK URL** - you'll need this for GitHub!
   - It looks like: `https://hook.us1.make.com/abcdef123456`

### Step 3: Add Google Drive - Download Video
1. Click "+" after webhook
2. Search for "Google Drive"
3. Select "Download a file"
4. Click "Create a connection"
   - Choose "Service Account"
   - Upload your service account JSON file
   - Click "Save"
5. Configure the module:
   - **File ID**: `{{1.video.id}}` (from webhook data)
   - Click "OK"

### Step 4: Add Facebook Post
1. Click "+" after Google Drive
2. Search for "Facebook"
3. Select "Create a Post"
4. Click "Create a connection"
   - Click "Sign in with Facebook"
   - Authorize Make.com
   - Select your Facebook Page
5. Configure the module:
   - **Page**: Choose your page
   - **Message**: `{{1.caption.description}}`
   - **Video**: `{{2.data}}` (from Google Drive download)
   - **Published**: Yes
   - Click "OK"

### Step 5: Add YouTube Upload
1. Click "+" (parallel to Facebook)
2. Search for "YouTube"
3. Select "Upload a Video"
4. Click "Create a connection"
   - Sign in with Google
   - Authorize Make.com
   - Select your YouTube channel
5. Configure the module:
   - **Title**: `{{1.caption.title}}`
   - **Description**: `{{1.caption.description}}`
   - **Video**: `{{2.data}}` (from Google Drive)
   - **Privacy Status**: Public
   - **Category**: News & Politics (25)
   - **Tags**: `{{join(1.caption.hashtags; ",")}}`
   - Click "OK"

### Step 6: Add TikTok Upload
1. Click "+" (parallel to Facebook/YouTube)
2. Search for "TikTok"
3. Select "Upload a Video"
4. Click "Create a connection"
   - Sign in with TikTok
   - Authorize Make.com
5. Configure the module:
   - **Caption**: `{{1.caption.description}} {{join(1.caption.hashtags; " ")}}`
   - **Video**: `{{2.data}}` (from Google Drive)
   - **Privacy Level**: Public
   - Click "OK"

### Step 7: Test the Scenario
1. Click "Run once" at the bottom
2. The webhook will wait for data
3. Test it manually:

```bash
# Copy your webhook URL from Make.com
# Then run this curl command:

curl -X POST 'YOUR_WEBHOOK_URL_HERE' \
  -H 'Content-Type: application/json' \
  -d '{
    "video": {
      "id": "test-id",
      "downloadLink": "https://example.com/video.mp4"
    },
    "caption": {
      "title": "Test News Video",
      "description": "This is a test description for the news video.",
      "hashtags": ["news", "politics", "breaking"]
    }
  }'
```

4. Check if Make.com received the data
5. If successful, click "Save" at the bottom

### Step 8: Activate Scenario
1. Toggle the switch at the bottom to "ON"
2. Your scenario is now active and waiting for webhooks!

---

## Part 4: Update GitHub Actions Workflow

### Step 1: Add Make.com Webhook URL to GitHub Secrets
1. Go to repository → Settings → Secrets
2. Click "New repository secret"
3. Name: `MAKE_WEBHOOK_URL`
4. Value: Paste the webhook URL from Make.com
5. Click "Add secret"

### Step 2: Update Workflow File
The workflow needs to be updated to upload to Google Drive and trigger Make.com.

I'll update the `.github/workflows/news_agent.yml` file for you.

### Step 3: Install Required Python Package
Add to `requirements.txt`:
```
google-api-python-client
google-auth
requests
```

---

## Part 5: Test End-to-End

### Step 1: Trigger GitHub Actions Manually
1. Go to your repository
2. Click "Actions" tab
3. Select "Daily News Video Generator"
4. Click "Run workflow"
5. Select branch: main
6. Click "Run workflow"

### Step 2: Monitor the Process

**In GitHub Actions:**
- Watch the workflow run
- Check each step completes successfully
- Look for "Upload to Google Drive" step

**In Google Drive:**
- Refresh your "News Videos" folder
- Verify video and caption.json appear

**In Make.com:**
- Go to Scenarios → Your scenario
- Click "History" at the bottom
- You should see a new execution
- Click it to see each step

**On Social Media:**
- Check Facebook page for new post
- Check YouTube channel for new Short
- Check TikTok profile for new video

### Step 3: Verify Scheduled Runs
- GitHub Actions will run automatically at:
  - 6:00 AM EST
  - 9:00 AM EST
  - 12:00 PM EST
  - 3:00 PM EST
  - 6:00 PM EST

---

## Part 6: Troubleshooting

### Webhook Not Triggering
**Problem**: Make.com doesn't receive webhook
**Solution**:
- Verify `MAKE_WEBHOOK_URL` in GitHub secrets
- Check webhook URL format (starts with `https://hook`)
- Look at GitHub Actions logs for upload step
- Test webhook manually with curl

### Video Upload Fails to Facebook
**Problem**: "Video format not supported"
**Solution**:
- Videos are MP4 format (correct ✅)
- Check video is < 4GB (ours are ~10MB ✅)
- Verify Facebook connection in Make.com
- Re-authorize Facebook connection

### YouTube Upload Fails
**Problem**: "Quota exceeded" or "forbidden"
**Solution**:
- YouTube has daily upload quota (typically 1,600 videos/day)
- Our 5 videos/day is well within limits
- Verify YouTube channel is verified (required for uploads)
- Re-authorize Google connection

### TikTok Upload Fails
**Problem**: "Video too long" or "format not supported"
**Solution**:
- TikTok videos must be < 60 seconds (ours are ~50s ✅)
- TikTok max file size: 287MB (ours are ~10MB ✅)
- Re-authorize TikTok connection
- Some TikTok accounts need creator status

### Google Drive Permission Denied
**Problem**: Can't upload to Drive folder
**Solution**:
- Verify service account email has Editor access to folder
- Check `GOOGLE_DRIVE_FOLDER_ID` is correct
- Verify service account JSON is base64 encoded correctly
- Re-share folder with service account

---

## Part 7: Monitor & Optimize

### Check Make.com Usage
1. Go to Make.com → Settings → Usage
2. Monitor operations used (each video = ~5 operations)
3. Core plan includes 1,000 operations/month
4. 5 videos/day × 30 days = 750 operations (well within limit ✅)

### Set Up Notifications
In Make.com scenario:
1. Add "Email" module after all posts
2. Configure to send you success/failure notifications
3. Or use "Slack" / "Discord" for instant alerts

### Review Analytics
- **Facebook Insights**: Track post reach and engagement
- **YouTube Studio**: Monitor views and watch time
- **TikTok Analytics**: Check video performance

---

## Cost Breakdown

| Item | Cost | Frequency |
|------|------|-----------|
| Make.com Core | $9/month | Monthly |
| Google Cloud | $0* | Free tier |
| NewsData.io | $0* | 500 calls/mo free |
| Pexels API | $0 | Free forever |
| Gemini API | $0* | Free tier |
| **Total** | **$9/month** | **Monthly** |

*Assuming you stay within free tiers (you will with 5 videos/day)

---

## Security Best Practices

### Protect Your Secrets
- ✅ Never commit service account JSON to GitHub
- ✅ Use GitHub Secrets for all API keys
- ✅ Base64 encode sensitive data
- ✅ Rotate API keys every 90 days

### OAuth Permissions
- ✅ Only grant minimum required permissions
- ✅ Review Make.com connected apps regularly
- ✅ Revoke unused connections
- ✅ Use separate social accounts for automation (optional)

### Webhook Security
- ✅ Make.com webhooks are unique and hard to guess
- ✅ Don't share webhook URLs publicly
- ✅ Monitor Make.com execution history for unusual activity

---

## Next Steps

1. ✅ Create Make.com account (start free trial)
2. ✅ Set up Google Drive folder and service account
3. ✅ Create Make.com scenario with webhook
4. ✅ Add MAKE_WEBHOOK_URL to GitHub secrets
5. ✅ Update GitHub Actions workflow
6. ✅ Test with manual workflow run
7. ✅ Monitor first scheduled run
8. ✅ Upgrade to Core plan after successful trial
9. 🎉 Enjoy fully automated video posting!

---

## Support Resources

- **Make.com Documentation**: https://www.make.com/en/help
- **Make.com Community**: https://community.make.com/
- **Video Tutorials**: https://www.make.com/en/academy
- **Support**: help@make.com

---

## Summary: What You've Achieved

✅ **100% automated** video generation and posting  
✅ **No bot detection** (using official OAuth integrations)  
✅ **Multi-platform** (Facebook, YouTube, TikTok)  
✅ **AI-powered** captions and content  
✅ **Scheduled** 5 times daily automatically  
✅ **Cost-effective** at just $9/month  
✅ **Scalable** - easy to add more platforms  

**You've built a professional automated news content system!** 🚀

---

## Questions or Issues?

If you run into any problems during setup:
1. Check the Troubleshooting section above
2. Review Make.com execution history
3. Check GitHub Actions logs
4. Verify all secrets are set correctly
5. Test each component individually

Ready to get started? Let's do this! 🎉
