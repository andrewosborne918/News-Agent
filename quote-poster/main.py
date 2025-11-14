import os
import json
import random
import io
import time
from typing import Optional, Dict, Any, Tuple

import functions_framework
import requests
from PIL import Image

from google.cloud import secretmanager
from google.cloud import aiplatform  # Vertex AI (for Gemini)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

# --- Configuration ---
LOCATION = "us-central1"  # Or your preferred region
GEMINI_MODEL = "gemini-1.5-pro" # Using 1.5 Pro for its strong vision capabilities

# --- Caches for lazy initialization ---
_SECRET_CACHE: Dict[str, str] = {}
_SECRET_CLIENT_CACHE: Optional[secretmanager.SecretManagerServiceClient] = None
_DRIVE_SERVICE_CACHE: Optional[Any] = None
_AI_INITIALIZED = False


def _get_project_id() -> str:
    """Gets the project ID from the environment."""
    project_id = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise EnvironmentError("GCP_PROJECT or GOOGLE_CLOUD_PROJECT env var not set.")
    return project_id

def _get_secret_client() -> secretmanager.SecretManagerServiceClient:
    """Lazily initializes and returns the Secret Manager client."""
    global _SECRET_CLIENT_CACHE
    if _SECRET_CLIENT_CACHE:
        return _SECRET_CLIENT_CACHE
    
    # Initialize client ONCE
    _SECRET_CLIENT_CACHE = secretmanager.SecretManagerServiceClient()
    return _SECRET_CLIENT_CACHE

def _get_secret(secret_id: str) -> str:
    """Fetches a secret from Secret Manager, with caching."""
    if secret_id in _SECRET_CACHE:
        return _SECRET_CACHE[secret_id]

    project_id = _get_project_id() # Get project ID
    client = _get_secret_client() # Get lazy-loaded client
        
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    try:
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8")
        _SECRET_CACHE[secret_id] = payload
        return payload
    except Exception as e:
        print(f"Error fetching secret '{secret_id}': {e}")
        raise

def _get_drive_service() -> Any:
    """Builds and returns an authenticated Google Drive service client."""
    global _DRIVE_SERVICE_CACHE
    if _DRIVE_SERVICE_CACHE:
        return _DRIVE_SERVICE_CACHE
    
    try:
        # Get the service account JSON from Secret Manager
        sa_json_str = _get_secret("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON")
        sa_creds = json.loads(sa_json_str)
        
        credentials = service_account.Credentials.from_service_account_info(
            sa_creds,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        drive_service = build('drive', 'v3', credentials=credentials)
        _DRIVE_SERVICE_CACHE = drive_service # Cache it
        return drive_service
    except Exception as e:
        print(f"Error building Drive service: {e}")
        return None

def _get_random_image(drive_service: Any, folder_id: str) -> Optional[Dict]:
    """Picks one random image file from the specified Drive folder."""
    try:
        query = f"'{folder_id}' in parents and mimeType contains 'image/'"
        response = drive_service.files().list(
            q=query,
            pageSize=100,  # Grab up to 100 files
            fields="files(id, name, webContentLink)"
        ).execute()
        
        files = response.get('files', [])
        if not files:
            print("No images found in the source folder.")
            return None
            
        # Pick one at random
        chosen_file = random.choice(files)
        print(f"Selected image: {chosen_file.get('name')} (ID: {chosen_file.get('id')})")
        return chosen_file
    except HttpError as e:
        print(f"Error listing Drive files: {e}")
        return None

def _download_image_bytes(drive_service: Any, file_id: str) -> Optional[bytes]:
    """Downloads the content of a Drive file by its ID."""
    try:
        request = drive_service.files().get_media(fileId=file_id)
        file_bytes = io.BytesIO()
        request.execute(target=file_bytes)
        return file_bytes.getvalue()
    except HttpError as e:
        print(f"Error downloading image: {e}")
        return None

def _get_ai_caption(image_bytes: bytes) -> str:
    """Uses Gemini Vision to read the image text and write a conservative post."""
    
    global _AI_INITIALIZED
    # LAZILY INITIALIZE VERTEX AI HERE
    if not _AI_INITIALIZED:
        try:
            project_id = _get_project_id()
            aiplatform.init(project=project_id, location=LOCATION)
            _AI_INITIALIZED = True
            print("Vertex AI initialized.")
        except Exception as e:
            print(f"Error initializing Vertex AI: {e}")
            raise
    
    # This prompt is the core of your request
    prompt_text = """
    You are an AI assistant for a conservative news and commentary page.
    Your task is to analyze an image containing a quote and write a short,
    insightful blog post (2-3 paragraphs) that expands on that quote from a
    conservative perspective.

    Your perspective is guided by:
    - Fiscal responsibility
    - Limited government
    - Individual liberty
    - The importance of humility, faith, and personal responsibility

    **Task:**
    1.  First, analyze the image and identify the quote written on it.
    2.  Write a 2-3 paragraph reflection on this quote.
    3.  Connect the quote's message to current-day issues, the nation, or conservative principles.
    4.  Maintain a tone that is thoughtful, firm, and inspiring.
    5.  DO NOT use hashtags.
    6.  Start the post by stating the quote, like this: "Today's post shares a powerful piece of wisdom: '[The Quote]'"
    """
    
    try:
        # Initialize the Vertex AI model
        model = aiplatform.gapic.GenerativeModel(GEMINI_MODEL)

        # Prepare the image part
        image_part = {"mime_type": "image/jpeg", "data": image_bytes}
        
        # Prepare the text part
        text_part = {"text": prompt_text}

        # Send the multimodal request
        response = model.generate_content([text_part, image_part])
        
        caption = response.candidates[0].content.parts[0].text
        print("Successfully generated AI caption.")
        return caption
    except Exception as e:
        print(f"Error generating caption with Gemini: {e}")
        # Fallback in case AI fails
        return "A quote to reflect on. What does this mean to you in the context of our nation today?"


def _post_to_facebook(image_bytes: bytes, caption: str) -> bool:
    """Posts an image and caption to the Facebook Page."""
    try:
        page_id = _get_secret("FB_PAGE_ID")
        page_token = _get_secret("FACEBOOK_PAGE_TOKEN")
        
        url = f"https://graph.facebook.com/{page_id}/photos"
        
        files = {'source': ('image.jpg', image_bytes, 'image/jpeg')}
        params = {
            'caption': caption,
            'access_token': page_token
        }
        
        response = requests.post(url, files=files, params=params)
        response.raise_for_status()  # Raise an error for bad responses
        
        print(f"Successfully posted to Facebook: {response.json()}")
        return True
    except Exception as e:
        print(f"Error posting to Facebook: {e}")
        return False

def _move_file(drive_service: Any, file_id: str, to_folder_id: str, from_folder_id: str) -> bool:
    """Moves a file from the source folder to the used folder."""
    try:
        drive_service.files().update(
            fileId=file_id,
            addParents=to_folder_id,
            removeParents=from_folder_id,
            fields='id, parents'
        ).execute()
        print(f"Successfully moved file {file_id} to folder {to_folder_id}")
        return True
    except HttpError as e:
        print(f"Error moving Drive file: {e}")
        return False

# This is the main function triggered by Cloud Scheduler
@functions_framework.cloud_event
def quote_poster_main(cloud_event: Any) -> Tuple[str, int]:
    """
    Main function triggered by Pub/Sub (from Cloud Scheduler).
    """
    print("--- Quote-Poster Workflow Started ---")
    
    try:
        # 1. Get secrets
        source_folder_id = _get_secret("QUOTE_SOURCE_FOLDER_ID")
        used_folder_id = _get_secret("QUOTE_USED_FOLDER_ID")
        
        # 2. Get Drive service
        drive_service = _get_drive_service()
        if not drive_service:
            raise Exception("Failed to authenticate with Google Drive.")
        
        # 3. Pick a random image
        image_file = _get_random_image(drive_service, source_folder_id)
        if not image_file:
            print("No images found to post. Exiting.")
            return ("No images", 200)
            
        file_id = image_file["id"]
        
        # 4. Download the image
        image_bytes = _download_image_bytes(drive_service, file_id)
        if not image_bytes:
            raise Exception(f"Failed to download image {file_id}")
            
        # 5. Generate AI caption
        print("Generating AI caption...")
        # Add a short delay to ensure Vertex API is ready
        time.sleep(2) 
        caption = _get_ai_caption(image_bytes)
        
        # 6. Post to Facebook
        print("Posting to Facebook...")
        if not _post_to_facebook(image_bytes, caption):
            raise Exception("Failed to post to Facebook.")
            
        # 7. Move the file
        print("Moving file to 'Used' folder...")
        if not _move_file(drive_service, file_id, used_folder_id, source_folder_id):
            print("Warning: Post was successful, but file move failed.")
            
        print("--- Quote-Poster Workflow Succeeded ---")
        return ("Success", 200)
        
    except Exception as e:
        print(f"--- Quote-Poster Workflow FAILED ---")
        print(f"Error: {e}")
        # Return 200 to prevent Pub/Sub from retrying a failed post
        return (f"Error: {e}", 200)