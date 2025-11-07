# Fix Cloud Function to Debug Metadata Loading

## Problem
The AI-generated titles and descriptions aren't being used, and Facebook uploads are failing.

## Solution
Add better logging to see what's in the companion JSON file.

## Steps

### 1. Open the Cloud Function file in Cloud Shell Editor
```bash
cd ~/cloud-function
cloudshell edit main.py
```

### 2. Find the `_maybe_download_companion_metadata` function (around line 35-54)

Replace it with this version that has better logging:

```python
def _maybe_download_companion_metadata(bucket: str, blob_name: str) -> dict | None:
    """If a companion JSON file exists (same base name with .json) download and parse it."""
    if not blob_name.endswith(".mp4"):
        return None
    base_no_ext = os.path.splitext(blob_name)[0]
    meta_blob_name = base_no_ext + ".json"
    client = storage.Client()
    bucket_obj = client.bucket(bucket)
    meta_blob = bucket_obj.blob(meta_blob_name)
    
    print(f"Looking for companion metadata: {meta_blob_name}")
    
    if not meta_blob.exists():
        print(f"No companion JSON found, using defaults")
        return None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        meta_blob.download_to_filename(tmp)
        data = json.loads(Path(tmp).read_text(encoding="utf-8"))
        os.remove(tmp)
        if isinstance(data, dict):
            print(f"Found companion metadata JSON: {meta_blob_name}")
            print(f"  Title: {data.get('title', 'N/A')}")
            print(f"  Description: {data.get('description', 'N/A')[:100]}...")
            print(f"  Tags: {data.get('tags', [])}")
            return data
        else:
            print(f"Companion JSON is not a dict, ignoring")
            return None
    except Exception as e:
        print(f"Failed to read companion metadata: {e}")
        return None
```

### 3. Save the file (Ctrl+S)

### 4. Redeploy
```bash
gcloud functions deploy gcs_to_social --gen2 --runtime=python311 --region=us-central1 --source=. --entry-point=gcs_to_social --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" --trigger-event-filters="bucket=news-videos-1762459809" --memory=512MB --timeout=540s --set-env-vars=GCP_PROJECT=news-automation-477419
```

### 5. Test with a new video
Trigger the workflow to generate a new video and watch the logs to see what metadata is being found.

## What This Will Show
The enhanced logging will tell us:
- Is the JSON file being found?
- What's actually in the JSON file?
- Are the title/description being extracted properly?

This will help us figure out if the problem is:
1. JSON file not being created
2. JSON file not being uploaded
3. JSON file malformed
4. Cloud Function not reading it correctly
