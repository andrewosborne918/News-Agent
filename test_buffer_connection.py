#!/usr/bin/env python3
"""
Test Buffer connection and verify connected social accounts.
"""

import os
import sys
import requests

BUFFER_API_URL = "https://api.bufferapp.com/1"


def test_buffer_connection():
    """Test Buffer API connection and show connected profiles."""
    
    access_token = os.getenv("BUFFER_ACCESS_TOKEN")
    if not access_token:
        print("❌ Error: BUFFER_ACCESS_TOKEN environment variable not set")
        print("\nTo test:")
        print("  export BUFFER_ACCESS_TOKEN='your_token_here'")
        print("  python test_buffer_connection.py")
        sys.exit(1)
    
    print("🔍 Testing Buffer API connection...\n")
    
    try:
        # Test authentication
        url = f"{BUFFER_API_URL}/user.json"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        user = response.json()
        print("✅ Authentication successful!")
        print(f"👤 User: {user.get('name', 'N/A')}")
        print(f"📧 Email: {user.get('email', 'N/A')}")
        print()
        
        # Get connected profiles
        url = f"{BUFFER_API_URL}/profiles.json"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        profiles = response.json()
        
        if not profiles:
            print("⚠️  No social media accounts connected to Buffer")
            print("\nPlease connect accounts at: https://buffer.com")
            return False
        
        print(f"✅ Found {len(profiles)} connected account(s):\n")
        
        for i, profile in enumerate(profiles, 1):
            service = profile.get('service', 'unknown').upper()
            username = profile.get('formatted_username', 'N/A')
            profile_id = profile['_id']
            
            # Get service-specific info
            service_name = profile.get('service_username', username)
            
            print(f"  {i}. {service}")
            print(f"     Username: @{username}")
            print(f"     Profile ID: {profile_id}")
            print(f"     Can schedule: {'Yes' if profile.get('schedules') else 'No'}")
            print()
        
        # Show supported services
        services = [p.get('service') for p in profiles]
        print("📱 Connected platforms:")
        if 'facebook' in services:
            print("   ✅ Facebook")
        if 'youtube' in services:
            print("   ✅ YouTube")
        if 'tiktok' in services:
            print("   ✅ TikTok")
        if 'instagram' in services:
            print("   ✅ Instagram")
        if 'twitter' in services:
            print("   ✅ Twitter/X")
        if 'linkedin' in services:
            print("   ✅ LinkedIn")
        
        print("\n" + "="*60)
        print("✅ Buffer is ready to use!")
        print("="*60)
        print("\nNext steps:")
        print("1. Add BUFFER_ACCESS_TOKEN to GitHub Secrets")
        print("2. Videos will auto-post 5x daily (6am-6pm EST)")
        print("3. Check Buffer queue at: https://buffer.com")
        
        return True
        
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        if e.response is not None:
            print(f"Response: {e.response.text}")
        print("\nPossible issues:")
        print("- Invalid access token")
        print("- Token expired")
        print("- No accounts connected to Buffer")
        return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    success = test_buffer_connection()
    sys.exit(0 if success else 1)
