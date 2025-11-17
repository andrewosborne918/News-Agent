#!/usr/bin/env python3
"""
image_processor.py
"""

import os
import sys
import json
import time
import io
from typing import Dict, Optional, Tuple

# --- Google / Gemini ---
import google.generativeai as genai
import google.auth.transport.requests # <-- ADDED
from google.api_core.exceptions import ResourceExhausted, InternalServerError
from google.cloud import storage 
from google.oauth2.credentials import Credentials  # <-- CHANGED
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

# --- Other ---
from PIL import Image

# --- Constants ---
SOURCE_FOLDER_ID = os.environ.get("SOURCE_DRIVE_FOLDER_ID")
USED_FOLDER_ID = os.environ.get("USED_DRIVE_FOLDER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GCS_BUCKET = os.environ.get("GCS_BUCKET") 
MODEL_NAME = os.environ.get("MODEL_NAME", "gemini-2.5-flash")
FALLBACK_MODEL_NAME = os.environ.get("FALLBACK_MODEL_NAME", "gemini-2.0-flash") # <-- KEPT YOUR FALLBACK

PROJECT_ID = os.environ.get("GCP_PROJECT_ID")

# --- OAuth Constants ---
GDRIVE_CLIENT_ID = os.environ.get("GDRIVE_CLIENT_ID")
GDRIVE_CLIENT_SECRET = os.environ.get("GDRIVE_CLIENT_SECRET")
GDRIVE_REFRESH_TOKEN = os.environ.get("GDRIVE_REFRESH_TOKEN")

# ---
# This is your existing fallback function
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
            # If retry also fails, try the fallback
            print(f"❌ Retry with {primary_model_name} also failed. Trying fallback {fallback_model_name}. Error: {retry_e}")
            try:
                model = genai.GenerativeModel(fallback_model_name)
                return model.generate_content(prompt)
            except Exception as fallback_e:
                print(f"❌ Fallback model {fallback_model_name} also failed.")
                raise fallback_e # Re-raise the fallback error
    
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

# ---
# --- COMPLETELY REPLACED FUNCTION ---
# ---
def get_gdrive_service():
    """Authenticates using user OAuth 2.0 credentials."""
    print("🔐 Authenticating to Google Drive using OAuth 2.0 Refresh Token...")
    SCOPES = ['https://www.googleapis.com/auth/drive']
    
    if not all([GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET, GDRIVE_REFRESH_TOKEN]):
        print("❌ Error: Missing one or more GDRIVE OAuth environment variables.")
        sys.exit(1)

    try:
        creds = Credentials(
            None, # No access token, we'll get one with the refresh token
            refresh_token=GDRIVE_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GDRIVE_CLIENT_ID,
            client_secret=GDRIVE_CLIENT_SECRET,
            scopes=SCOPES
        )
        
        # Refresh the token to get a valid access token
        creds.refresh(google.auth.transport.requests.Request())
        
        service = build('drive', 'v3', credentials=creds)
        print("✅ Google Drive service authenticated as user.")
        return service
    except Exception as e:
        print(f"❌ Failed to authenticate with OAuth 2.0: {e}")
        sys.exit(1)

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
        # --- FIX: Only grab images, skip folders ---
        if 'image' not in first_item['mimeType'] or 'folder' in first_item['mimeType']:
            print(f"⚠️ First file found ({first_item['name']}) is not an image. Skipping.")
            return None
            
        print(f"✅ Found image: {first_item['name']} (ID: {first_item['id']})")
        return first_item
        
    except HttpError as error:
        print(f"❌ An error occurred listing Drive files: {error}")
        return None

def download_drive_file(service, file_id: str, file_name: str) -> Optional[str]:
    """Downloads a file from Drive to a local temp path."""
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

def generate_post_from_image(image_path: str) -> Optional[str]:
    """Uses Gemini to generate a 3-4 paragraph post about the image."""
    print(f"🤖 Analyzing image with Gemini ({MODEL_NAME})...")
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY not set.")
        return None
        
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        img = Image.open(image_path)
        
        prompt_text = """You are a news analyst for 'RightSide Report,' a conservative news outlet. Your analysis is guided by fiscal responsibility, limited government, and individual liberty.
Based on the attached image, write a 3 to 4 paragraph post about the topic it represents.
RULES:
1.  **Find the Conservative Angle:** Analyze the image and identify the core topic. Frame this topic from a conservative perspective.
2.  **Focus on Core Principles:** Connect the topic to its impact on the economy, taxes, government overreach, border security, or individual freedoms.
3.  **Tone:** Your tone must be direct, analytical, and confident.
4.  **Format:** Write 3-4 full paragraphs. Do not use hashtags or any other formatting. Just the paragraphs.
"""

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

def upload_to_gcs(local_file_path: str, blob_name: str):
    """Uploads a local file to the GCS bucket."""
    print(f"☁️  Uploading {blob_name} to GCS bucket {GCS_BUCKET}...")
    try:
        # This will use the service account auth from `gcloud-github-actions/auth`
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET)
        blob = bucket.blob(f"incoming/{blob_name}") # Upload to the 'incoming' folder
        
        blob.upload_from_filename(local_file_path)
        print(f"✅ GCS Upload successful: gs://{GCS_BUCKET}/incoming/{blob_name}")
    except Exception as e:
        print(f"❌ GCS Upload failed: {e}")
        raise # Re-raise the exception to fail the workflow

def create_and_upload_json(post_text: str, base_filename: str):
    """Creates a companion JSON file and uploads it to GCS."""
    local_json_path = f"./temp_{base_filename}.json"
    
    metadata = {
        "text": post_text,
        "post_type": "image",
        "original_filename": base_filename
    }
    
    try:
        with open(local_json_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
            
        upload_to_gcs(local_json_path, f"{base_filename}.json")
        
    finally:
        if os.path.exists(local_json_path):
            os.remove(local_json_path)

def move_drive_file(service, file_id: str):
    """Moves the file from the source folder to the used folder."""
    print(f"🚚 Moving file {file_id} to 'Used' folder ({USED_FOLDER_ID})...")
    try:
        file = service.files().get(fileId=file_id, fields='parents').execute()
        
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
    if not all([SOURCE_FOLDER_ID, USED_FOLDER_ID, GEMINI_API_KEY, PROJECT_ID, GCS_BUCKET]):
        print("❌ Missing one or more required environment variables.")
        sys.exit(1)

    drive_service = get_gdrive_service()
    if not drive_service:
        sys.exit(1)
        
    image_file = get_first_image_from_drive(drive_service)
    if not image_file:
        print("🏁 No new images to process. Exiting.")
        sys.exit(0)
    
    base_filename = image_file['id']
    original_file_extension = os.path.splitext(image_file['name'])[1]
    
    local_image_path = download_drive_file(drive_service, image_file['id'], image_file['name'])
    if not local_image_path:
        sys.exit(1)
        
    try:
        post_content = generate_post_from_image(local_image_path)
        if not post_content:
            print("❌ Halting workflow: Could not generate post content.")
            sys.exit(1)
            
        print("\n--- GENERATED POST ---")
        print(post_content)
        print("----------------------\n")
        
        print("🚀 Starting GCS upload process...")
        
        image_blob_name = f"{base_filename}{original_file_extension}"
        upload_to_gcs(local_image_path, image_blob_name)
        
        create_and_upload_json(post_content, base_filename)
        
        print("✅ GCS upload complete. Cloud Function will post to Facebook.")
        
        move_drive_file(drive_service, image_file['id'])
            
    finally:
        if os.path.exists(local_image_path):
            print(f"🧹 Cleaning up temp file: {local_image_path}")
            os.remove(local_image_path)

if __name__ == "__main__":
    main()