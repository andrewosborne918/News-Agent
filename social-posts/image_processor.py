#!/usr/bin/env python3
"""
image_processor.py

Workflow:
1.  Connects to Google Drive.
2.  Picks one image from the SOURCE_DRIVE_FOLDER_ID.
3.  Downloads the image locally.
4.  Sends the image to Gemini to generate a 3-4 paragraph post.
5.  Uploads the image and a companion .json file to GCS.
6.  Moves the image file in Google Drive to USED_DRIVE_FOLDER_ID.
"""

import os
import sys  # <-- ADDED
import json
import time
import io
from typing import Dict, Optional, Tuple

# --- Google / Gemini ---
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, InternalServerError
from google.cloud import storage # <-- ADDED
from google.oauth2 import service_account  # <-- ADDED
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

# --- Other ---
from PIL import Image

# --- Constants ---
SOURCE_FOLDER_ID = os.environ.get("SOURCE_DRIVE_FOLDER_ID")
USED_FOLDER_ID = os.environ.get("USED_DRIVE_FOLDER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GCS_BUCKET = os.environ.get("GCS_BUCKET") # <-- ADDED
MODEL_NAME = os.environ.get("MODEL_NAME", "gemini-2.5-flash")
FALLBACK_MODEL_NAME = "gemini-2.5-pro"

PROJECT_ID = os.environ.get("GCP_PROJECT_ID")

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

# ---
# --- REPLACED FUNCTION ---
# ---
def get_gdrive_service():
    """Authenticates using the JSON key path and returns a Google Drive v3 service object."""
    print("🔐 Authenticating to Google Drive using Service Account JSON...")
    SCOPES = ['https://www.googleapis.com/auth/drive']
    JSON_PATH = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_PATH")
    
    if not JSON_PATH:
        print("❌ Error: GOOGLE_SERVICE_ACCOUNT_JSON_PATH environment variable not set.")
        sys.exit(1)
        
    if not os.path.exists(JSON_PATH):
        print(f"❌ Error: Service account file not found at: {JSON_PATH}")
        sys.exit(1)

    try:
        creds = service_account.Credentials.from_service_account_file(
            JSON_PATH, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
        print("✅ Google Drive service authenticated.")
        return service
    except Exception as e:
        print(f"❌ Failed to authenticate with service account JSON: {e}")
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

# --- NEW FUNCTION ---
def upload_to_gcs(local_file_path: str, blob_name: str):
    """Uploads a local file to the GCS bucket."""
    print(f"☁️  Uploading {blob_name} to GCS bucket {GCS_BUCKET}...")
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET)
        blob = bucket.blob(f"incoming/{blob_name}") # Upload to the 'incoming' folder
        
        blob.upload_from_filename(local_file_path)
        print(f"✅ GCS Upload successful: gs://{GGCS_BUCKET}/incoming/{blob_name}")
    except Exception as e:
        print(f"❌ GCS Upload failed: {e}")
        raise # Re-raise the exception to fail the workflow

# --- NEW FUNCTION ---
def create_and_upload_json(post_text: str, base_filename: str):
    """Creates a companion JSON file and uploads it to GCS."""
    local_json_path = f"./temp_{base_filename}.json"
    
    # This is the metadata your Cloud Function will read
    metadata = {
        "text": post_text, # The full 3-4 paragraphs
        "post_type": "image", # Tells the Cloud Function this is an image
        "original_filename": base_filename
    }
    
    try:
        with open(local_json_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
            
        upload_to_gcs(local_json_path, f"{base_filename}.json")
        
    finally:
        if os.path.exists(local_json_path):
            os.remove(local_json_path) # Clean up local JSON

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
    
    # Use the file ID as the unique base name
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
        
        # --- REPLACED FACEBOOK POST WITH GCS UPLOAD ---
        print("🚀 Starting GCS upload process...")
        
        # 1. Upload the image file (e.g., 12345.png)
        image_blob_name = f"{base_filename}{original_file_extension}"
        upload_to_gcs(local_image_path, image_blob_name)
        
        # 2. Create and upload the JSON file (e.g., 12345.json)
        create_and_upload_json(post_content, base_filename)
        
        print("✅ GCS upload complete. Cloud Function will post to Facebook.")
        
        # 3. Move the file in Google Drive
        move_drive_file(drive_service, image_file['id'])
            
    finally:
        # Clean up the local temp image file
        if os.path.exists(local_image_path):
            print(f"🧹 Cleaning up temp file: {local_image_path}")
            os.remove(local_image_path)

if __name__ == "__main__":
    main()