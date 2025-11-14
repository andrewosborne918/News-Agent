#!/usr/bin/env python3
"""
Generate engaging title, description, and hashtags from video content.
Uses Gemini AI to analyze the segments and create compelling social media captions.

This script analyzes the generated news commentary and creates optimized captions
for social media platforms (Twitter, Instagram, Facebook, LinkedIn).
"""

import os
import sys
import json
import time # <-- ADDED THIS IMPORT
from pathlib import Path
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, InternalServerError

# --- THIS IS THE CORRECTED, SINGLE FUNCTION ---
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


def load_article_data(data_dir="generated"):
    """Load the article data from the generated JSON file."""
    article_file = Path(data_dir) / "article.json"
    if article_file.exists():
        with open(article_file, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return None
    return None


def load_segments_data(data_dir="generated"):
    """Load the text segments from the generated video."""
    data_dir = Path(data_dir)
    segments = []
    
    # Read all .txt files in order
    for txt_file in sorted(data_dir.glob("*.txt")):
        with open(txt_file, 'r', encoding='utf-8') as f:
            text = f.read().strip()
            if text:
                segments.append(text)
    
    return segments

# --- ADDED: FUNCTION TO READ RUN_ID ---
def load_run_id(data_dir="generated"):
    """Load the run_id from the generated text file."""
    run_id_file = Path(data_dir) / "run_id.txt"
    if run_id_file.exists():
        with open(run_id_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    print("⚠️  Warning: generated/run_id.txt not found.")
    return None
# --------------------------------------

def generate_caption_with_ai(segments, api_key, article_data=None):
    """Use Gemini to generate a compelling caption from the video segments."""
    
    genai.configure(api_key=api_key)
    # model = genai.GenerativeModel('gemini-2.5-flash') # <-- This line is no longer needed
    
    # Combine segments into a summary
    content = "\n".join(segments)
    
    # Add article context to the prompt if available
    article_title = ""
    if article_data and "title" in article_data:
        article_title = article_data["title"]
        prompt_context = f"The news commentary is about an article titled: '{article_title}'"
    else:
        prompt_context = "The news commentary is about a recent political event."

    prompt = f"""Analyze this political news commentary and create engaging social media content.

{prompt_context}

COMMENTARY:
{content}

Generate the following (be concise and punchy for social media):

1. TITLE: A catchy, attention-grabbing headline (under 60 characters) based on the commentary.
2. DESCRIPTION: A compelling 2-3 sentence description that summarizes the key points and makes people want to watch.
3. HASHTAGS: 5-8 relevant, trending hashtags (mix of general and specific to the topic).

Format your response as JSON:
{{
    "title": "your title here",
    "description": "your description here",
    "hashtags": ["hashtag1", "hashtag2", "hashtag3", ...]
}}

Rules:
- Title should be urgent and engaging.
- Description should hint at controversy or important developments.
- Include both trending political hashtags and evergreen news hashtags.
- No hashtag should have spaces (use camelCase if needed).
- Make it shareable and clickable."""

    try:
        response = generate_with_fallback(
            prompt,
            primary_model_name='gemini-1.5-flash', # <-- Corrected primary model
            fallback_model_name='gemini-pro' # <-- FIXED FALLBACK
        )
        text = response.text.strip()
        
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        
        caption_data = json.loads(text)
        return caption_data
        
    except Exception as e:
        print(f"⚠️  AI generation failed: {e}")
        print("📝 Using fallback caption generation...")
        return generate_fallback_caption(segments)


def generate_fallback_caption(segments):
    """Generate a basic caption if AI fails."""
    # Extract key phrases from first and last segments
    first_segment = segments[0] if segments else "Breaking news"
    
    # Create a simple title from the first segment
    title = first_segment[:60] + "..." if len(first_segment) > 60 else first_segment
    
    description = "Political commentary on today's biggest story. Watch to get the full analysis and what it means for the future."
    
    hashtags = [
        "Politics",
        "News",
        "Breaking",
        "Analysis",
        "CurrentEvents",
        "PoliticalNews",
        "USPolitics"
    ]
    
    return {
        "title": title,
        "description": description,
        "hashtags": hashtags
    }


def format_for_social_media(caption_data, platform="twitter"):
    """Format the caption for different social media platforms."""
    
    title = caption_data["title"]
    description = caption_data["description"]
    hashtags = caption_data["hashtags"]
    
    # Format hashtags
    hashtag_string = " ".join([f"#{tag}" for tag in hashtags])
    
    # Twitter/X format (280 character limit)
    if platform == "twitter":
        # Try to fit everything, truncate description if needed
        full_text = f"{title}\n\n{description}\n\n{hashtag_string}"
        if len(full_text) > 280:
            # Truncate description to fit
            max_desc_length = 280 - len(title) - len(hashtag_string) - 10  # Buffer for newlines
            description = description[:max_desc_length] + "..."
        
        return f"{title}\n\n{description}\n\n{hashtag_string}"
    
    # Instagram/Facebook format (longer allowed)
    elif platform in ["instagram", "facebook"]:
        return f"{title}\n\n{description}\n\n{hashtag_string}"
    
    # LinkedIn format (professional tone)
    elif platform == "linkedin":
        return f"{title}\n\n{description}\n\n{hashtag_string}"
    
    # Default format
    else:
        return f"{title}\n\n{description}\n\n{hashtag_string}"


def save_caption_data(caption_data, output_file="generated/caption.json"):
    """Save the caption data to a file for use by other scripts."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(caption_data, f, indent=2)
    
    print(f"✅ Caption data saved to {output_file}")


def main():
    # Get API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY environment variable not set")
        sys.exit(1)
    
    # Get data directory
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "generated"
    
    print("📝 Generating caption from video content...")
    print(f"📂 Reading segments from: {data_dir}")
    
    # Load segments and article data
    segments = load_segments_data(data_dir)
    article_data = load_article_data(data_dir)
    run_id = load_run_id(data_dir) # <-- ADDED
    
    if not segments:
        print("❌ No segments found. Make sure video has been generated.")
        sys.exit(1)
    
    print(f"✅ Loaded {len(segments)} segments")
    if article_data:
        print(f"✅ Loaded article data: {article_data['title']}")
    if run_id:
        print(f"✅ Loaded run_id: {run_id}") # <-- ADDED
    
    # Generate caption with AI
    print("🤖 Generating caption with AI...")
    caption_data = generate_caption_with_ai(segments, api_key, article_data)
    
    # --- ADDED: INJECT THE RUN_ID ---
    if run_id:
        caption_data["run_id"] = run_id
    # ---------------------------------
    
    # Display results
    print("\n" + "="*60)
    print("📰 GENERATED CAPTION")
    print("="*60)
    print(f"\n🎯 TITLE:\n{caption_data['title']}")
    print(f"\n📝 DESCRIPTION:\n{caption_data['description']}")
    print(f"\n🏷️  HASHTAGS:\n{' '.join(['#' + tag for tag in caption_data['hashtags']])}")
    if "run_id" in caption_data: # <-- ADDED
        print(f"\n🆔 RUN_ID:\n{caption_data['run_id']}") # <-- ADDED
    print("\n" + "="*60)
    print("📱 FORMATTED FOR SOCIAL MEDIA")
    print("="*60)
    
    # Format for different platforms
    formatted = format_for_social_media(caption_data, platform="twitter")
    print(f"\n{formatted}")
    
    # --- THIS IS THE CORRECTED LINE ---
    print("\n" + "="*60)
    # ----------------------------------
    
    # Save caption data
    save_caption_data(caption_data)
    
    print("\n✅ Caption generation complete!")


if __name__ == "__main__":
    main()