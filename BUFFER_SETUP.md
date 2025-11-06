# Buffer Integration Setup

This guide will help you set up automatic posting to Buffer for your generated news videos.

## Prerequisites

- Buffer account (free or paid)
- Social media accounts connected to Buffer (Twitter, Facebook, LinkedIn, etc.)

## Step 1: Get Your Buffer Access Token

### Option A: Using Buffer's Developer App (Recommended)

1. Go to https://account.buffer.com/developers/apps
2. Click "Create App"
3. Fill in the details:
   - **Name**: News Agent Auto Poster
   - **Description**: Automated news video posting
   - **Website URL**: https://github.com/andrewosborne918/News-Agent
4. Click "Create App"
5. Copy your **Access Token** (it will look like: `1/abc123def456...`)

### Option B: Using OAuth Flow (Advanced)

If you need to post to multiple Buffer accounts, follow Buffer's OAuth documentation:
https://buffer.com/developers/api/oauth

## Step 2: Add Buffer Token to GitHub Secrets

1. Go to your GitHub repository: https://github.com/andrewosborne918/News-Agent
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add secret:
   - **Name**: `BUFFER_ACCESS_TOKEN`
   - **Value**: Your Buffer access token from Step 1
5. Click **Add secret**

## Step 3: Test the Integration Locally (Optional)

```bash
# Set your Buffer token
export BUFFER_ACCESS_TOKEN="your_token_here"

# Test posting a video
python post_to_buffer.py output/final.mp4
```

## Step 4: Verify Everything Works

The workflow will now:
1. ✅ Generate news content (6am, 9am, 12pm, 3pm, 6pm EST)
2. ✅ Create video with background music
3. ✅ Upload video to Buffer
4. ✅ Post to your connected social accounts

## Buffer Posting Behavior

### Default Behavior
- Posts are added to your Buffer queue
- They'll be published based on your Buffer posting schedule
- To post immediately, adjust your Buffer settings to "Post Now"

### Customize Posting Schedule
1. Go to Buffer → **Settings** → **Posting Schedule**
2. Set your preferred times for each social account
3. Buffer will automatically schedule posts at the next available slot

## Customizing Captions

Edit `post_to_buffer.py` to customize the captions:

```python
def generate_caption(run_id):
    captions = [
        "🔥 Your custom caption here",
        "📰 Another caption option",
        # Add more...
    ]
    # ...
```

## Troubleshooting

### "No Buffer profiles found"
- **Cause**: No social accounts connected to Buffer
- **Fix**: Go to https://buffer.com and connect at least one social account

### "Invalid access token"
- **Cause**: Token expired or incorrect
- **Fix**: Generate a new token and update the GitHub secret

### "Video upload failed"
- **Cause**: Video file too large (Buffer limit: 512 MB for videos)
- **Fix**: Videos should be under 10 MB with current settings, so this shouldn't happen

### "Rate limit exceeded"
- **Cause**: Too many API requests
- **Fix**: Buffer free tier allows 10 scheduled posts. Upgrade to paid plan for more.

## Buffer API Limits

### Free Plan
- 10 scheduled posts per profile
- 1 connected social account per service

### Paid Plans
- More scheduled posts
- Multiple accounts per service
- Priority support

See: https://buffer.com/pricing

## Current Schedule

Videos are generated and posted:
- **6:00 AM EST** (11:00 UTC)
- **9:00 AM EST** (14:00 UTC)
- **12:00 PM EST** (17:00 UTC)
- **3:00 PM EST** (20:00 UTC)
- **6:00 PM EST** (23:00 UTC)

5 videos per day, evenly spaced throughout business hours.

## Support

- Buffer API Docs: https://buffer.com/developers/api
- Buffer Support: https://support.buffer.com
