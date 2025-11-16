#!/usr/bin/env python3
"""
image_processor.py

Workflow:
1.  Connects to Google Drive using default application credentials (from gh-actions-uploader).
2.  Picks one image from the SOURCE_DRIVE_FOLDER_ID.
3.  Downloads the image locally.
4.  Sends the image to Gemini (multimodal) to generate a 3-4 paragraph post.
5.  Connects to GCP Secret Manager to get Facebook credentials.
6.  Posts the image and the generated text to a Facebook Page.
7.  If successful, moves the image file in Google Drive to USED_DRIVE_FOLDER_ID.
"""

import os
import sys
import json
import time
import io
from typing import Dict, Optional, Tuple

# --- Google / Gemini ---
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, InternalServerError
from google.cloud import secretmanager
from google.auth import default as google_auth_default
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

# --- Other ---
import requests
from PIL import Image

# --- Constants ---
SOURCE_FOLDER_ID = os.environ.get("SOURCE_DRIVE_FOLDER_ID")
USED_FOLDER_ID = os.environ.get("USED_DRIVE_FOLDER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- UPDATED: Model name from workflow, with a default ---
MODEL_NAME = os.environ.get("MODEL_NAME", "gemini-2.5-flash")
FALLBACK_MODEL_NAME = "gemini-2.5-pro" # Matches your other scripts

# --- Secret Manager Cache ---
_SECRET_CACHE: Dict[str, str] = {}
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")

# ---
# This is your existing fallback function, used by all your scripts
# ---
def generate_with_fallback(prompt, primary_model_name, fallback_model_name):
    """
    Tries to generate content with the primary model.
    - If a rate limit error (429) occurs, it pauses for 61 seconds and retries.
    - If another error (like 500) occurs, it tries the fallback model.
    """
    try:
        # 1. Try the primary model
        model = genai.GenerativeModel(primary_model_name)
        return model.generate_content(prompt)
    
    except ResourceExhausted as e:
        # 2. If rate limited (429), PAUSE and RETRY
        print(f"⚠️  Rate limit on {primary_model_name}. Pausing for 61 seconds... Error: {e}")
        time.sleep(61) # Pause for 61 seconds to be safe
        print(f"⌛ Retrying with {primary_model_name}...")
        try:
            model = genai.GenerativeModel(primary_model_name)
            return model.generate_content(prompt) # Retry the primary model
        except Exception as retry_e:
            print(f"❌ Retry with {primary_model_name} also failed.")
            raise retry_e # Re-raise the error after retry
    
    except (InternalServerError) as e:
        # 3. If it's a server error (500s), try the fallback
        print(f"⚠️  Internal Server Error on {primary_model_name}, trying fallback {fallback_model_name}. Error: {e}")
        try:
            model = genai.GenerativeModel(fallback_model_name)
            return model.generate_content(prompt)
        except Exception as fallback_e:
            print(f"❌ Fallback model {fallback_model_name} also failed.")
            raise fallback_e # Re-raise the fallback error
            
    except Exception as e:
        # 4. Handle other (non-rate-limit) errors by trying fallback
        print(f"❌ Non-rate-limit error on {primary_model_name}, trying fallback {fallback_model_name}. Error: {e}")
        try:
            model = genai.GenerativeModel(fallback_model_name)
            return model.generate_content(prompt)
        except Exception as fallback_e:
            print(f"❌ Fallback model {fallback_model_name} also failed.")
            raise fallback_e # Re-raise the fallback error

def get_gdrive_service():
    """Authenticates using default creds and returns a Google Drive v3 service object."""
    print("🔐 Authenticating to Google Drive using default credentials...")
    SCOPES = ['https://www.googleapis.com/auth/drive']
    
    # Use google.auth.default() which finds the credentials
    # provided by the 'google-github-actions/auth' step
    creds, _ = google_auth_default(scopes=SCOPES)
    
    service = build('drive', 'v3', credentials=creds)
    print("✅ Google Drive service authenticated.")
    return service

def get_first_image_from_drive(service) -> Optional[Dict[str, str]]:
    """Fetches the first file from the source folder."""
    print(f"🔎 Searching for images in folder: {SOURCE_FOLDER_ID}")
    try:
        results = service.files().list(
            q=f"'{SOURCE_FOLDER_ID}' in parents and trashed=false",
            pageSize=1,
            fields="files(id, name, mimeType)"
        ).execute()
        
        items = results.get('files', [])
        
        if not items:
            print("ℹ️  No files found in the source folder.")
            return None
        
        first_item = items[0]
        if 'image' not in first_item['mimeType']:
            print(f"⚠️ First file found ({first_item['name']}) is not an image. Skipping.")
            return None
            
        print(f"✅ Found image: {first_item['name']} (ID: {first_item['id']})")
        return first_item
        
    except HttpError as error:
        print(f"❌ An error occurred listing Drive files: {error}")
        return None

def download_drive_file(service, file_id: str, file_name: str) -> Optional[str]:
    """Downloads a file from Drive to a local temp path."""
    # Save the temp file in the root, not in the social-posts folder
    local_path = f"./temp_{file_name}"
    print(f"📥 Downloading {file_name} to {local_path}...")
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(local_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(f"  -> Download {int(status.progress() * 100)}%.")
            
        print(f"✅ Download complete.")
        return local_path
        
    except HttpError as error:
        print(f"❌ An error occurred downloading the file: {error}")
        if os.path.exists(local_path):
            os.remove(local_path)
        return None
    except Exception as e:
        print(f"❌ A local error occurred: {e}")
        if os.path.exists(local_path):
            os.remove(local_path)
        return None

def generate_post_from_image(image_path: str) -> Optional[str]:
    """Uses Gemini to generate a 3-4 paragraph post about the image."""
    print(f"🤖 Analyzing image with Gemini ({MODEL_NAME})...")
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY not set.")
        return None
        
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        img = Image.open(image_path)
        
        # This prompt is tailored to your 'RightSide Report' voice
        prompt_text = """You are a news analyst for 'RightSide Report,' a conservative news outlet. Your analysis is guided by fiscal responsibility, limited government, and individual liberty.

Based on the attached image, write a 3 to 4 paragraph post about the topic it represents.

RULES:
1.  **Find the Conservative Angle:** Analyze the image and identify the core topic. Frame this topic from a conservative perspective.
2.  **Focus on Core Principles:** Connect the topic to its impact on the economy, taxes, government overreach, border security, or individual freedoms.
3.  **Tone:** Your tone must be direct, analytical, and confident.
4.  **Format:** Write 3-4 full paragraphs. Do not use hashtags or any other formatting. Just the paragraphs.
"""

        # --- UPDATED: Use the standard model names ---
        response = generate_with_fallback(
            [prompt_text, img],
            primary_model_name=MODEL_NAME,
            fallback_model_name=FALLBACK_MODEL_NAME
        )
        
        post_text = response.text.strip()
        
        if not post_text or len(post_text.split()) < 50:
            print("❌ Gemini returned an empty or very short response.")
            return None
            
        print("✅ Gemini generation successful.")
        return post_text
        
    except Exception as e:
        print(f"❌ Error during Gemini generation: {e}")
        return None

def _get_secret(secret_name: str) -> Optional[str]:
    """Fetch a secret from Secret Manager (cached)."""
    global _SECRET_CACHE
    if secret_name in _SECRET_CACHE:
        return _SECRET_CACHE[secret_name]

    if not PROJECT_ID:
        print("❌ GCP_PROJECT_ID environment variable not set. Cannot fetch secrets.")
        return None

    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{PROJECT_ID}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("utf-8").strip()
        
        if not secret_value:
            print(f"⚠️ Secret {secret_name} is empty.")
            return None
            
        _SECRET_CACHE[secret_name] = secret_value
        print(f"✅ Successfully loaded secret: {secret_name}")
        return secret_value
    except Exception as e:
        print(f"❌ Could not load secret {secret_name}: {e}")
        return None

def post_to_facebook(local_image_path: str, post_text: str) -> bool:
    """Uploads an image and a caption to the Facebook Page."""
    print("🌎 Publishing to Facebook...")
    
    # Get secrets from environment variable names, then fetch from Secret Manager
    page_token_secret_name = os.environ.get("FB_PAGE_TOKEN_SECRET")
    page_id_secret_name = os.environ.get("FB_PAGE_ID_SECRET")
    
    page_token = _get_secret(page_token_secret_name)
    page_id = _get_secret(page_id_secret_name)
    
    if not page_token or not page_id:
        print("❌ FATAL: FACEBOOK_PAGE_TOKEN or FB_PAGE_ID secrets are missing or failed to load.")
        return False

    # Use the /photos endpoint for images
    url = f"https://graph.facebook.com/v20.0/{page_id}/photos"
    
    params = {
        "access_token": page_token,
        "caption": post_text,
    }

    try:
        with open(local_image_path, 'rb') as f:
            files = {
                'source': (os.path.basename(local_image_path), f, 'image/jpeg') # Assume jpeg, works for png too
            }
            response = requests.post(url, params=params, files=files, timeout=300) 
            
        response_data = response.json()
        
        if response.status_code == 200 and "id" in response_data:
            print(f"✅ Facebook post successful! Post ID: {response_data['id']}")
            return True
        else:
            print(f"❌ Facebook post failed. Status: {response.status_code}, Response: {response_data}")
            return False

    except Exception as e:
        print(f"❌ Exception during Facebook post: {e}")
        return False

def move_drive_file(service, file_id: str):
    """Moves the file from the source folder to the used folder."""
    print(f"🚚 Moving file {file_id} to 'Used' folder ({USED_FOLDER_ID})...")
    try:
        # Retrieve the existing parents to remove the source folder
        file = service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents'))
        
        # Update the file's parents
        service.files().update(
            fileId=file_id,
            addParents=USED_FOLDER_ID,
            removeParents=SOURCE_FOLDER_ID,
            fields='id, parents'
        ).execute()
        
        print("✅ File moved successfully.")
        
    except HttpError as error:
        print(f"❌ An error occurred moving the file: {error}")
        
def main():
    if not all([SOURCE_FOLDER_ID, USED_FOLDER_ID, GEMINI_API_KEY, PROJECT_ID]):
        print("❌ Missing one or more required environment variables (SOURCE_DRIVE_FOLDER_ID, USED_DRIVE_FOLDER_ID, GEMINI_API_KEY, GCP_PROJECT_ID).")
        sys.exit(1)

    drive_service = get_gdrive_service()
    if not drive_service:
        sys.exit(1)
        
    image_file = get_first_image_from_drive(drive_service)
    if not image_file:
        print("🏁 No new images to process. Exiting.")
        sys.exit(0)
    
    local_path = download_drive_file(drive_service, image_file['id'], image_file['name'])
    if not local_path:
        sys.exit(1)
        
    try:
        post_content = generate_post_from_image(local_path)
        if not post_content:
            print("❌ Halting workflow: Could not generate post content.")
            sys.exit(1)
            
        print("\n--- GENERATED POST ---")
        print(post_content)
        print("----------------------\n")
        
        success = post_to_facebook(local_path, post_content)
        
        if success:
            print("✅ Post was successful, moving file in Drive.")
            move_drive_file(drive_service, image_file['id'])
        else:
            print("⚠️ Post failed. File will NOT be moved, will try again next run.")
            sys.exit(1) # Exit with an error to alert you in GitHub Actions
            
    finally:
        # Clean up the local temp file
        if os.path.exists(local_path):
            print(f"🧹 Cleaning up temp file: {local_path}")
            os.remove(local_path)

if __name__ == "__main__":
    main()