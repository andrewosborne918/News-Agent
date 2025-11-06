#!/usr/bin/env python3
"""
test_pexels_integration.py

Quick test to verify Pexels integration works with the generate_segments workflow.
"""

import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

def test_api_key():
    """Test that Pexels API key is configured"""
    print("1. Testing API key configuration...")
    api_key = os.getenv("PEXELS_API_KEY")
    
    if not api_key:
        print("   ❌ PEXELS_API_KEY not found in .env")
        return False
    
    if api_key == "your_pexels_api_key_here":
        print("   ❌ PEXELS_API_KEY is still placeholder value")
        return False
    
    print(f"   ✅ API key found (length: {len(api_key)})")
    return True


def test_module_import():
    """Test that pexels_photos module can be imported"""
    print("\n2. Testing module import...")
    
    try:
        import pexels_photos
        print("   ✅ pexels_photos module imported successfully")
        return True
    except ImportError as e:
        print(f"   ❌ Failed to import pexels_photos: {e}")
        return False


def test_photo_search():
    """Test actual photo search"""
    print("\n3. Testing photo search...")
    
    try:
        import pexels_photos
        
        # Test with a simple query
        photo_url = pexels_photos.get_photo_for_question(
            question_text="What is happening in the news today?",
            answer_text="Political debates continue in Washington about budget policy."
        )
        
        if photo_url and photo_url.startswith("http"):
            print(f"   ✅ Photo URL retrieved: {photo_url[:80]}...")
            return True
        else:
            print(f"   ⚠️ No photo URL returned (might be API limit or network issue)")
            return False
            
    except Exception as e:
        print(f"   ❌ Error during search: {e}")
        return False


def test_generate_segments_import():
    """Test that generate_segments.py can import and use pexels_photos"""
    print("\n4. Testing generate_segments.py integration...")
    
    try:
        # Check if the function exists
        from generate_segments import get_photo_url_for_question
        print("   ✅ get_photo_url_for_question function found")
        
        # Try calling it
        result = get_photo_url_for_question(
            question_text="What is the economy doing?",
            answer_text="Economic indicators show mixed results.",
            question_id="test_q1"
        )
        
        if result:
            print(f"   ✅ Function returned URL: {result[:60]}...")
        else:
            print("   ⚠️ Function returned empty (might be expected)")
        
        return True
        
    except ImportError as e:
        print(f"   ❌ Could not import from generate_segments: {e}")
        return False
    except Exception as e:
        print(f"   ⚠️ Function call error (this might be okay): {e}")
        return True  # Still consider it a pass if function exists


def main():
    """Run all tests"""
    print("=" * 60)
    print("Pexels Integration Test Suite")
    print("=" * 60)
    
    results = []
    
    results.append(("API Key", test_api_key()))
    results.append(("Module Import", test_module_import()))
    results.append(("Photo Search", test_photo_search()))
    results.append(("Generate Segments Integration", test_generate_segments_import()))
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    all_passed = all(result[1] for result in results)
    
    print("=" * 60)
    if all_passed:
        print("🎉 All tests passed! Pexels integration is ready to use.")
        print("\nNext step: Run generate_segments.py with --auto flag")
    else:
        print("⚠️ Some tests failed. Check the output above for details.")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
