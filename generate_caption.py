#!/usr/bin/env python3
"""
Generate engaging title, description, and hashtags from video content.
Uses Gemini AI (with Groq fallback) to analyze the segments and create
compelling social media captions.

This script analyzes the generated news commentary and creates optimized captions
for social media platforms (Twitter, Instagram, Facebook, LinkedIn).
"""

import os
import sys
import json
import time
from pathlib import Path
import urllib.request

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, InternalServerError


# --------------------------------------------------------------------
# Groq helper + unified Gemini→Groq fallback
# --------------------------------------------------------------------

def _call_groq_chat(prompt: str) -> str | None:
    """Call Groq's chat completions API and return the content string, or None on failure."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("[groq] GROQ_API_KEY not set; skipping Groq fallback.")
        return None

    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write concise, punchy social copy and JSON for short news videos. "
                    "Always respond with a single JSON object if the user asks for JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_completion_tokens": 512,
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
            # If Groq ever returns structured parts, flatten text fields
            return "".join(str(part.get("text", "")) for part in content)
        return str(content)
    except Exception as e:
        print(f"[groq] Groq API call failed: {e}")
        return None


class _SimpleResponse:
    """Tiny wrapper so Groq text looks like a Gemini response (has .text)."""
    def __init__(self, text: str):
        self.text = text


def generate_with_model_fallback(prompt: str, model_list: list[str]):
    """
    Tries to generate content with a list of Gemini models, then falls back to Groq
    if all Gemini models are exhausted (e.g. 429 quota errors).
    """
    if not model_list:
        raise ValueError("Model list cannot be empty.")

    last_error: Exception | None = None

    # First: try Gemini models in order
    for model_name in model_list:
        try:
            print(f"ℹ️  Attempting Gemini generation with: {model_name}")
            model = genai.GenerativeModel(model_name)
            return model.generate_content(prompt)

        except ResourceExhausted as e:
            # 429 / quota
            print(f"⚠️  Quota limit on {model_name}. Trying next Gemini model...")
            last_error = e
            continue

        except InternalServerError as e:
            # 500, backoff + one retry
            print(f"⚠️  Server error on {model_name}. Pausing for 10s and retrying...")
            last_error = e
            time.sleep(10)
            try:
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt)
            except Exception as retry_e:
                print(f"❌ Retry failed for {model_name}. Trying next Gemini model...")
                last_error = retry_e
                continue

        except Exception as e:
            # Safety or other issues – try next Gemini model
            print(f"❌ Non-quota error on {model_name}: {e}. Trying next Gemini model...")
            last_error = e
            continue

    # If we reach here, all Gemini models failed
    print("🔁 All Gemini models failed or are rate-limited. Trying Groq as backup...")
    groq_text = _call_groq_chat(prompt)
    if groq_text:
        print("✅ Groq fallback succeeded.")
        return _SimpleResponse(groq_text)

    print("❌ Groq fallback also failed.")
    if last_error:
        raise last_error
    raise Exception("Failed to generate content after trying Gemini and Groq.")


# --------------------------------------------------------------------
# Existing helpers (unchanged, but now powered by the new fallback)
# --------------------------------------------------------------------

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


def load_run_id(data_dir="generated"):
    """Load the run_id from the generated text file."""
    run_id_file = Path(data_dir) / "run_id.txt"
    if run_id_file.exists():
        with open(run_id_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    print("⚠️  Warning: generated/run_id.txt not found.")
    return None


def generate_caption_with_ai(segments, api_key, article_data=None):
    """Use Gemini (with Groq fallback) to generate a compelling caption."""
    # Configure Gemini if we have a key. If not, we'll still hit Groq later.
    if api_key:
        genai.configure(api_key=api_key)
    else:
        print("⚠️  GEMINI_API_KEY not set; will rely entirely on Groq fallback.")

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
        model_fallbacks = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
        ]
        response = generate_with_model_fallback(prompt, model_fallbacks)
        text = response.text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        caption_data = json.loads(text)
        return caption_data

    except Exception as e:
        print(f"⚠️  AI generation failed (even with Groq fallback): {e}")
        print("📝 Using fallback caption generation...")
        return generate_fallback_caption(segments)


def generate_fallback_caption(segments):
    """Generate a basic caption if AI fails."""
    first_segment = segments[0] if segments else "Breaking news"

    title = first_segment[:60] + "..." if len(first_segment) > 60 else first_segment

    description = (
        "Political commentary on today's biggest story. "
        "Watch to get the full analysis and what it means for the future."
    )

    hashtags = [
        "Politics",
        "News",
        "Breaking",
        "Analysis",
        "CurrentEvents",
        "PoliticalNews",
        "USPolitics",
    ]

    return {
        "title": title,
        "description": description,
        "hashtags": hashtags,
    }


def format_for_social_media(caption_data, platform="twitter"):
    """Format the caption for different social media platforms."""
    title = caption_data["title"]
    description = caption_data["description"]
    hashtags = caption_data["hashtags"]

    hashtag_string = " ".join([f"#{tag}" for tag in hashtags])

    if platform == "twitter":
        full_text = f"{title}\n\n{description}\n\n{hashtag_string}"
        if len(full_text) > 280:
            max_desc_length = 280 - len(title) - len(hashtag_string) - 10
            description = description[:max_desc_length] + "..."
        return f"{title}\n\n{description}\n\n{hashtag_string}"

    if platform in ["instagram", "facebook", "linkedin"]:
        return f"{title}\n\n{description}\n\n{hashtag_string}"

    return f"{title}\n\n{description}\n\n{hashtag_string}"


def save_caption_data(caption_data, output_file="generated/caption.json"):
    """Save the caption data to a file for use by other scripts."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(caption_data, f, indent=2)

    print(f"✅ Caption data saved to {output_file}")


def main():
    # Get API key (optional now – we can run on Groq only if needed)
    api_key = os.getenv("GEMINI_API_KEY")

    # Get data directory
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "generated"

    print("📝 Generating caption from video content...")
    print(f"📂 Reading segments from: {data_dir}")

    segments = load_segments_data(data_dir)
    article_data = load_article_data(data_dir)
    run_id = load_run_id(data_dir)

    if not segments:
        print("❌ No segments found. Make sure video has been generated.")
        sys.exit(1)

    print(f"✅ Loaded {len(segments)} segments")
    if article_data:
        print(f"✅ Loaded article data: {article_data['title']}")
    if run_id:
        print(f"✅ Loaded run_id: {run_id}")

    print("🤖 Generating caption with AI (Gemini→Groq fallback)...")
    caption_data = generate_caption_with_ai(segments, api_key, article_data)

    if run_id:
        caption_data["run_id"] = run_id

    print("\n" + "=" * 60)
    print("📰 GENERATED CAPTION")
    print("=" * 60)
    print(f"\n🎯 TITLE:\n{caption_data['title']}")
    print(f"\n📝 DESCRIPTION:\n{caption_data['description']}")
    print(f"\n🏷️  HASHTAGS:\n{' '.join(['#' + tag for tag in caption_data['hashtags']])}")
    if "run_id" in caption_data:
        print(f"\n🆔 RUN_ID:\n{caption_data['run_id']}")
    print("\n" + "=" * 60)
    print("📱 FORMATTED FOR SOCIAL MEDIA")
    print("=" * 60)

    formatted = format_for_social_media(caption_data, platform="twitter")
    print(f"\n{formatted}")
    print("\n" + "=" * 60)

    save_caption_data(caption_data)
    print("\n✅ Caption generation complete!")


if __name__ == "__main__":
    main()
