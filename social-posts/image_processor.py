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
import urllib.request

# --- Google / Gemini ---
import google.generativeai as genai
import google.auth.transport.requests # <-- ADDED
from google.api_core.exceptions import ResourceExhausted, InternalServerError
from google.cloud import storage 
import google.auth
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
MODEL_NAME = os.environ.get("MODEL_NAME", "gemini-2.5-flash-lite")
FALLBACK_MODEL_NAME = os.environ.get("FALLBACK_MODEL_NAME", "gemini-2.0-flash")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

PROJECT_ID = os.environ.get("GCP_PROJECT_ID")


# --------------------------------------------------------------------
# Groq helper (text-only fallback)
# --------------------------------------------------------------------

def _call_groq_chat(prompt: str) -> Optional[str]:
    """Call Groq's chat completions API.

    Note: this is text-only (no image upload). We'll use it as a last-resort
    fallback if Gemini fails.
    """
    api_key = GROQ_API_KEY
    if not api_key:
        print("[groq] GROQ_API_KEY not set; skipping Groq fallback.")
        return None

    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a conservative commentator for 'RightSide Report.' "
                    "Write 3-4 paragraphs, conversational and witty, with a conservative viewpoint. "
                    "Never mention that you are an AI."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
        "max_completion_tokens": 700,
    }

    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode("utf-8")
        parsed = json.loads(payload)
        choices = parsed.get("choices") or []
        if not choices:
            print("[groq] No choices in response.")
            return None
        msg = choices[0].get("message", {})
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(part.get("text", "")) for part in content)
        return str(content)
    except Exception as e:
        print(f"[groq] Groq API call failed: {e}")
        return None


class _SimpleResponse:
    """Tiny wrapper so Groq text looks like a Gemini response (has .text)."""

    def __init__(self, text: str):
        self.text = text


def _describe_image_for_text_fallback(image_path: str) -> str:
    """Produce minimal, safe image metadata for text-only fallbacks.

    We intentionally avoid any vision/ML here. This is just enough context to help
    the model avoid wildly mismatched assumptions (portrait vs landscape, etc.).
    """
    try:
        img = Image.open(image_path)
        w, h = img.size
        fmt = (img.format or "").upper()
        mode = img.mode
        orientation = "portrait" if h >= w else "landscape"
        return f"Image metadata: format={fmt}, mode={mode}, size={w}x{h}, orientation={orientation}."
    except Exception:
        return ""

# ---
# This is your existing fallback function
# ---
def generate_with_fallback(prompt, primary_model_name, fallback_model_name):
    """
    Tries to generate content with Gemini, then falls back to Groq.

    Order:
    1) Gemini primary model
    2) (On 429) pause and retry primary once
    3) Gemini fallback model
    4) Groq text-only fallback
    """

    def _groq_prompt_from_prompt_obj(p) -> str:
        """Convert `[prompt_text, PIL.Image]` style prompt into a text-only prompt."""
        if isinstance(p, str):
            return p
        if isinstance(p, (list, tuple)):
            parts = []
            for item in p:
                if isinstance(item, str):
                    parts.append(item)
            base = "\n\n".join([x.strip() for x in parts if x and x.strip()])
            # We can’t send the image to Groq here, so we ask for a post without
            # referencing the image itself.
            return (
                f"{base}\n\n"
                "IMPORTANT: You can't see the image. "
                "Write a strong, conservative-leaning post that would fit a typical "
                "political/news image, without mentioning the image. "
                "Keep it specific and current-events flavored, but do not invent quotes."
            )
        return str(p)

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
            # If retry also fails, try the fallback Gemini model
            print(f"❌ Retry with {primary_model_name} also failed. Trying fallback {fallback_model_name}. Error: {retry_e}")
            try:
                model = genai.GenerativeModel(fallback_model_name)
                return model.generate_content(prompt)
            except Exception as fallback_e:
                print(f"❌ Fallback model {fallback_model_name} also failed. Trying Groq...")
                groq_text = _call_groq_chat(_groq_prompt_from_prompt_obj(prompt))
                if groq_text:
                    print("✅ Groq fallback succeeded.")
                    return _SimpleResponse(groq_text)
                print("❌ Groq fallback also failed.")
                raise fallback_e # Re-raise the fallback error
    
    except (InternalServerError) as e:
        # 3. If it's a server error (500s), try the fallback
        print(f"⚠️  Internal Server Error on {primary_model_name}, trying fallback {fallback_model_name}. Error: {e}")
        try:
            model = genai.GenerativeModel(fallback_model_name)
            return model.generate_content(prompt)
        except Exception as fallback_e:
            print(f"❌ Fallback model {fallback_model_name} also failed. Trying Groq...")
            groq_text = _call_groq_chat(_groq_prompt_from_prompt_obj(prompt))
            if groq_text:
                print("✅ Groq fallback succeeded.")
                return _SimpleResponse(groq_text)
            print("❌ Groq fallback also failed.")
            raise fallback_e # Re-raise the fallback error
            
    except Exception as e:
        # 4. Handle other (non-rate-limit) errors by trying fallback
        print(f"❌ Non-rate-limit error on {primary_model_name}, trying fallback {fallback_model_name}. Error: {e}")
        try:
            model = genai.GenerativeModel(fallback_model_name)
            return model.generate_content(prompt)
        except Exception as fallback_e:
            print(f"❌ Fallback model {fallback_model_name} also failed. Trying Groq...")
            groq_text = _call_groq_chat(_groq_prompt_from_prompt_obj(prompt))
            if groq_text:
                print("✅ Groq fallback succeeded.")
                return _SimpleResponse(groq_text)
            print("❌ Groq fallback also failed.")
            raise fallback_e # Re-raise the fallback error

# ---
# --- This is the working OAuth function ---
# ---
def get_gdrive_service():
    """Authenticates to Google Drive using the GitHub Action's service account (ADC)."""
    print("🔐 Authenticating to Google Drive using service account (ADC)...")
    SCOPES = ["https://www.googleapis.com/auth/drive"]

    try:
        # Uses credentials from google-github-actions/auth
        creds, project = google.auth.default(scopes=SCOPES)

        service = build("drive", "v3", credentials=creds)
        print(f"✅ Google Drive service authenticated as service account (project={project}).")
        return service
    except Exception as e:
        print(f"❌ Failed to authenticate with service account credentials: {e}")
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
        
        # --- MODIFIED ---
        prompt_text = """You are a conservative commentator for 'RightSide Report.'
Your tone is conversational, casual, and witty, similar to Michael Knowles. You break down complex topics with a clear, conservative viewpoint and a touch of dry humor.

Based on the attached image, write a 3 to 4 paragraph post about the topic it represents.

RULES:
1.  **Find the Conservative Angle:** Analyze the image and identify the core topic. Frame this topic from a conservative perspective.
2.  **Focus on Core Principles:** Connect the topic to its impact on the economy, taxes, government overreach, border security, or individual freedoms.
3.  **Tone:** Be conversational and casual. Be articulate and witty, like a podcast host chatting with your audience. Don't be stiff or overly formal. A bit of dry humor is welcome.
4.  **Format:** Write 3-4 full paragraphs. Don't reference the image itself. Just discuss the ideaDo not use hashtags or any other formatting. Just the paragraphs.
"""
        # --- END MODIFICATION ---

        # For Groq fallback (text-only), we can optionally provide minimal
        # metadata about the image without referencing it in the final post.
        meta = _describe_image_for_text_fallback(image_path)
        composite_prompt = prompt_text
        if meta:
            composite_prompt = f"{prompt_text}\n\n{meta}"

        response = generate_with_fallback(
            [composite_prompt, img],
            primary_model_name=MODEL_NAME,
            fallback_model_name=FALLBACK_MODEL_NAME,
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