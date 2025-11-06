# n8n Automation Setup Guide

## Why n8n is Perfect for This Project

**Advantages:**
- ✅ **100% Free & Open Source** (self-hosted)
- ✅ **No monthly fees** (unlike Make.com $9 or Zapier $20)
- ✅ **OAuth integrations** (same bot-detection protection as Make.com/Zapier)
- ✅ **Unlimited workflows** (no execution limits on self-hosted)
- ✅ **Better privacy** (your data stays on your server)
- ✅ **Active development** (17k+ GitHub stars)

**Options:**
1. **Self-hosted (FREE)** - Run on your own computer/server
2. **n8n Cloud ($20/month)** - Managed hosting (similar to Zapier pricing)

We'll focus on **self-hosted** since it's free and you control everything.

---

## Installation Options

### Option 1: Docker (Recommended - Easiest)

**Prerequisites:**
- Docker Desktop installed on macOS

**Installation:**
```bash
# Create n8n directory
mkdir -p ~/.n8n

# Run n8n with Docker
docker run -d --name n8n \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  -e N8N_BASIC_AUTH_USER=admin \
  -e N8N_BASIC_AUTH_PASSWORD=your_secure_password \
  n8nio/n8n

# n8n will be available at: http://localhost:5678
```

**Start/Stop n8n:**
```bash
# Start
docker start n8n

# Stop
docker stop n8n

# View logs
docker logs n8n -f
```

### Option 2: npm (Alternative)

```bash
# Install n8n globally
npm install -g n8n

# Run n8n
n8n start

# Access at: http://localhost:5678
```

### Option 3: Cloud-Based (If you have a VPS)

For 24/7 automation, you can deploy n8n on:
- **DigitalOcean** ($5/month droplet)
- **Railway.app** (Free tier available)
- **Render.com** (Free tier available)

---

## Complete Automation Flow

```
GitHub Actions (generates video)
    ↓
Google Drive (stores video + caption)
    ↓
n8n Webhook (triggered by new file)
    ↓
n8n reads caption.json
    ↓
Posts to Facebook/YouTube/TikTok (via OAuth)
```

---

## Step-by-Step Setup

### Step 1: Install n8n (Choose Docker or npm above)

### Step 2: Access n8n
1. Open browser: `http://localhost:5678`
2. Set up your account (first time only)

### Step 3: Set Up Google Drive Integration

#### 3.1 Create Google Cloud Project
1. Go to: https://console.cloud.google.com/
2. Create new project: "n8n-news-automation"
3. Enable APIs:
   - Go to "APIs & Services" → "Library"
   - Enable "Google Drive API"
   - Enable "Google Sheets API" (if needed)

#### 3.2 Create OAuth Credentials
1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. Application type: "Web application"
4. Name: "n8n automation"
5. Authorized redirect URIs:
   ```
   http://localhost:5678/rest/oauth2-credential/callback
   ```
6. Save Client ID and Client Secret

#### 3.3 Configure in n8n
1. In n8n, click "Credentials" in sidebar
2. Click "New Credential"
3. Search for "Google Drive OAuth2 API"
4. Paste Client ID and Client Secret
5. Click "Connect my account"
6. Authorize access

### Step 4: Set Up Social Media OAuth Credentials

#### 4.1 Facebook/Instagram (Meta)
1. Go to: https://developers.facebook.com/apps/
2. Create new app → "Business"
3. Add "Facebook Login" product
4. In n8n:
   - Credentials → New → "Facebook OAuth2 API"
   - Paste App ID and App Secret
   - Connect account

#### 4.2 YouTube
1. Same Google Cloud project as Drive
2. Enable "YouTube Data API v3"
3. Use same OAuth credentials
4. In n8n:
   - Credentials → New → "Google OAuth2 API"
   - Scopes: `https://www.googleapis.com/auth/youtube.upload`

#### 4.3 TikTok
1. Go to: https://developers.tiktok.com/
2. Create app → "Login Kit"
3. In n8n:
   - Credentials → New → "TikTok OAuth2 API"
   - Paste credentials

### Step 5: Update GitHub Actions Workflow

Add Google Drive upload to workflow:

```yaml
# Add this step after "Generate caption with AI"
- name: Upload to Google Drive
  env:
    GOOGLE_DRIVE_FOLDER_ID: ${{ secrets.GOOGLE_DRIVE_FOLDER_ID }}
    GOOGLE_SERVICE_ACCOUNT_JSON_B64: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON_B64 }}
  run: |
    python upload_to_drive.py
```

### Step 6: Create n8n Workflow

I'll provide a complete n8n workflow JSON you can import.

**Workflow Structure:**
1. **Webhook Trigger** - Triggered when file uploaded to Google Drive
2. **Google Drive - Download Video**
3. **Google Drive - Download Caption JSON**
4. **Facebook Post** - Upload video + caption
5. **YouTube Post** - Upload as Short
6. **TikTok Post** - Upload video
7. **Notifications** - Send success/error notifications

---

## n8n Workflow JSON (Import This)

Create a new workflow in n8n and import this:

```json
{
  "name": "News Video Auto-Poster",
  "nodes": [
    {
      "parameters": {
        "path": "news-video-webhook",
        "responseMode": "onReceived",
        "responseData": "firstEntryJson"
      },
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 1,
      "position": [250, 300]
    },
    {
      "parameters": {
        "operation": "download",
        "fileId": "={{$json.videoFileId}}"
      },
      "name": "Download Video from Drive",
      "type": "n8n-nodes-base.googleDrive",
      "typeVersion": 3,
      "position": [450, 300],
      "credentials": {
        "googleDriveOAuth2Api": {
          "id": "1",
          "name": "Google Drive account"
        }
      }
    },
    {
      "parameters": {
        "operation": "download",
        "fileId": "={{$json.captionFileId}}"
      },
      "name": "Download Caption JSON",
      "type": "n8n-nodes-base.googleDrive",
      "typeVersion": 3,
      "position": [450, 450],
      "credentials": {
        "googleDriveOAuth2Api": {
          "id": "1",
          "name": "Google Drive account"
        }
      }
    },
    {
      "parameters": {
        "operation": "create",
        "message": "={{JSON.parse($node['Download Caption JSON'].json.data).description}}",
        "additionalFields": {
          "video": "={{$node['Download Video from Drive'].json.data}}"
        }
      },
      "name": "Post to Facebook",
      "type": "n8n-nodes-base.facebook",
      "typeVersion": 1,
      "position": [650, 200],
      "credentials": {
        "facebookGraphApi": {
          "id": "2",
          "name": "Facebook account"
        }
      }
    },
    {
      "parameters": {
        "operation": "upload",
        "title": "={{JSON.parse($node['Download Caption JSON'].json.data).title}}",
        "description": "={{JSON.parse($node['Download Caption JSON'].json.data).description}}",
        "tags": "={{JSON.parse($node['Download Caption JSON'].json.data).hashtags.join(',')}}",
        "video": "={{$node['Download Video from Drive'].json.data}}",
        "categoryId": "25",
        "privacyStatus": "public"
      },
      "name": "Post to YouTube",
      "type": "n8n-nodes-base.youTube",
      "typeVersion": 1,
      "position": [650, 350],
      "credentials": {
        "youTubeOAuth2Api": {
          "id": "3",
          "name": "YouTube account"
        }
      }
    },
    {
      "parameters": {
        "caption": "={{JSON.parse($node['Download Caption JSON'].json.data).description}}",
        "video": "={{$node['Download Video from Drive'].json.data}}"
      },
      "name": "Post to TikTok",
      "type": "n8n-nodes-base.tikTok",
      "typeVersion": 1,
      "position": [650, 500],
      "credentials": {
        "tikTokOAuth2Api": {
          "id": "4",
          "name": "TikTok account"
        }
      }
    }
  ],
  "connections": {
    "Webhook": {
      "main": [
        [
          {
            "node": "Download Video from Drive",
            "type": "main",
            "index": 0
          },
          {
            "node": "Download Caption JSON",
            "type": "main",
            "index": 0
          }
        ]
      ]
    },
    "Download Video from Drive": {
      "main": [
        [
          {
            "node": "Post to Facebook",
            "type": "main",
            "index": 0
          },
          {
            "node": "Post to YouTube",
            "type": "main",
            "index": 0
          },
          {
            "node": "Post to TikTok",
            "type": "main",
            "index": 0
          }
        ]
      ]
    }
  }
}
```

**To Import:**
1. In n8n, click "Workflows" → "Add Workflow"
2. Click "..." menu → "Import from File/URL"
3. Paste the JSON above
4. Update credential IDs to match your setup

---

## Files to Create

### 1. upload_to_drive.py

This script uploads the video and caption to Google Drive after generation:

```python
#!/usr/bin/env python3
"""
Upload generated video and caption to Google Drive
Triggers n8n webhook for automated posting
"""

import os
import json
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import requests

# Configuration
SCOPES = ['https://www.googleapis.com/auth/drive.file']
DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL', 'http://localhost:5678/webhook/news-video-webhook')

def get_drive_service():
    """Get authenticated Google Drive service"""
    # Decode base64 service account JSON
    service_account_json = base64.b64decode(
        os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON_B64')
    ).decode('utf-8')
    
    credentials_dict = json.loads(service_account_json)
    credentials = service_account.Credentials.from_service_account_info(
        credentials_dict,
        scopes=SCOPES
    )
    
    return build('drive', 'v3', credentials=credentials)

def upload_file(service, file_path, mime_type):
    """Upload file to Google Drive"""
    file_metadata = {
        'name': os.path.basename(file_path),
        'parents': [DRIVE_FOLDER_ID]
    }
    
    media = MediaFileUpload(
        file_path,
        mimetype=mime_type,
        resumable=True
    )
    
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    
    print(f"Uploaded {file_path}")
    print(f"File ID: {file.get('id')}")
    print(f"View link: {file.get('webViewLink')}")
    
    return file.get('id')

def trigger_n8n_webhook(video_file_id, caption_file_id):
    """Trigger n8n webhook with file IDs"""
    payload = {
        'videoFileId': video_file_id,
        'captionFileId': caption_file_id,
        'timestamp': os.getenv('GITHUB_RUN_ID', 'manual')
    }
    
    try:
        response = requests.post(N8N_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        print(f"✅ n8n webhook triggered successfully")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"⚠️ Warning: Could not trigger n8n webhook: {e}")
        print("Make sure n8n is running and webhook URL is correct")

def main():
    """Main upload function"""
    print("🔄 Uploading to Google Drive...")
    
    # Get Drive service
    service = get_drive_service()
    
    # Upload video
    video_path = 'generated/news_video.mp4'
    if not os.path.exists(video_path):
        print(f"❌ Error: Video file not found at {video_path}")
        return
    
    video_file_id = upload_file(service, video_path, 'video/mp4')
    
    # Upload caption
    caption_path = 'generated/caption.json'
    if not os.path.exists(caption_path):
        print(f"❌ Error: Caption file not found at {caption_path}")
        return
    
    caption_file_id = upload_file(service, caption_path, 'application/json')
    
    # Trigger n8n webhook
    trigger_n8n_webhook(video_file_id, caption_file_id)
    
    print("✅ Upload complete!")

if __name__ == '__main__':
    main()
```

---

## Setup Checklist

### Local Setup (n8n on your computer)
- [ ] Install Docker Desktop (or npm)
- [ ] Run n8n container
- [ ] Access n8n at http://localhost:5678
- [ ] Create Google Cloud project
- [ ] Enable Google Drive API
- [ ] Create OAuth credentials
- [ ] Add credentials to n8n
- [ ] Import workflow JSON
- [ ] Test webhook manually

### GitHub Actions Setup
- [ ] Create Google Drive folder for videos
- [ ] Get folder ID from URL
- [ ] Add `GOOGLE_DRIVE_FOLDER_ID` to GitHub secrets
- [ ] Add `N8N_WEBHOOK_URL` to GitHub secrets
- [ ] Update workflow YAML with upload step
- [ ] Install `google-api-python-client` in requirements.txt
- [ ] Test workflow run

### Social Media OAuth Setup
- [ ] Connect Facebook account in n8n
- [ ] Connect YouTube account in n8n
- [ ] Connect TikTok account in n8n
- [ ] Test each posting node individually
- [ ] Run complete workflow end-to-end

---

## Running n8n 24/7

### Option 1: Keep n8n Running on Your Mac
```bash
# Start n8n in background
docker start n8n

# n8n will run until you stop it or restart your computer
# Set Docker to start on login in Docker Desktop preferences
```

**Pros:**
- Free
- Full control

**Cons:**
- Mac must stay on
- Uses computer resources

### Option 2: Deploy to Cloud (24/7 for ~$5/month)

#### Railway.app (Easiest Cloud Deploy)
1. Sign up at https://railway.app
2. New Project → Deploy from Docker image
3. Image: `n8nio/n8n`
4. Add environment variables:
   ```
   N8N_BASIC_AUTH_ACTIVE=true
   N8N_BASIC_AUTH_USER=admin
   N8N_BASIC_AUTH_PASSWORD=your_password
   ```
5. Get public URL (e.g., `https://your-app.railway.app`)
6. Update GitHub secret `N8N_WEBHOOK_URL` with Railway URL

#### DigitalOcean Droplet
1. Create $5/month droplet (Ubuntu)
2. SSH into server
3. Install Docker
4. Run n8n container
5. Set up nginx reverse proxy
6. Point domain to droplet (optional)

---

## Testing the Complete Flow

### 1. Test Locally First
```bash
# Start n8n
docker start n8n

# In another terminal, trigger webhook manually
curl -X POST http://localhost:5678/webhook/news-video-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "videoFileId": "test-video-id",
    "captionFileId": "test-caption-id"
  }'
```

### 2. Test with Real Files
1. Manually upload a test video to Google Drive folder
2. Manually upload caption.json to same folder
3. Get file IDs from URLs
4. Trigger webhook with real IDs
5. Verify posts appear on Facebook/YouTube/TikTok

### 3. Test GitHub Actions Integration
1. Push changes to repository
2. Wait for scheduled run
3. Check GitHub Actions logs
4. Verify files uploaded to Drive
5. Check n8n execution log
6. Verify social media posts

---

## Troubleshooting

### n8n won't start
```bash
# Check if port 5678 is in use
lsof -i :5678

# Try different port
docker run -d --name n8n -p 5679:5678 -v ~/.n8n:/home/node/.n8n n8nio/n8n
```

### OAuth credentials not working
- Make sure redirect URI exactly matches: `http://localhost:5678/rest/oauth2-credential/callback`
- For cloud deployment, use your Railway/DigitalOcean URL
- Clear browser cookies and re-authenticate

### Webhook not triggering
- Check n8n is running: `docker ps | grep n8n`
- Check webhook URL in GitHub secrets
- View n8n logs: `docker logs n8n -f`
- Test webhook manually with curl first

### Video upload fails
- Check file size (Facebook limit: 4GB, YouTube: 256GB, TikTok: 287MB)
- Verify video format (MP4 works for all platforms)
- Check OAuth scopes include upload permissions

---

## Cost Comparison

| Solution | Monthly Cost | Setup Time | Bot Detection Risk |
|----------|--------------|------------|-------------------|
| **n8n (self-hosted)** | **$0** | 30-45 min | **None (OAuth)** |
| n8n (Railway cloud) | $5 | 20 min | None (OAuth) |
| Make.com | $9 | 30 min | None (OAuth) |
| Zapier | $20 | 15 min | None (OAuth) |
| Buffer Links | $0 | 5 min | None (manual) |

**Winner: n8n self-hosted** - Same OAuth security as Make.com/Zapier, but completely free!

---

## Next Steps

1. Choose deployment method (local or cloud)
2. Install n8n
3. Set up Google Drive credentials
4. Import workflow
5. Update GitHub Actions with upload script
6. Test complete automation
7. Sit back and enjoy automated posting! 🎉

---

## Resources

- n8n Documentation: https://docs.n8n.io/
- n8n Community Forum: https://community.n8n.io/
- Example Workflows: https://n8n.io/workflows/
- Docker Setup: https://docs.n8n.io/hosting/installation/docker/
- Google Drive API: https://developers.google.com/drive/api/v3/about-sdk

---

## Questions?

Once n8n is running, you'll have:
- ✅ 100% automated video posting
- ✅ No monthly fees (if self-hosted)
- ✅ No bot detection (OAuth integrations)
- ✅ Full control over your data
- ✅ Unlimited executions
- ✅ Easy workflow modifications

Let's get started! 🚀
