#!/usr/bin/env python3
"""Test which HTTP library works after macOS update"""

import sys

print("Testing httplib2 vs requests...")
print()

# Test 1: httplib2
print("1) Testing httplib2...")
try:
    import httplib2
    import socket
    
    socket.setdefaulttimeout(10)
    http = httplib2.Http(timeout=10)
    
    print("   Attempting connection to www.googleapis.com...")
    response, content = http.request("https://www.googleapis.com/")
    print(f"   ✅ httplib2 works - Status: {response.status}")
except Exception as e:
    print(f"   ❌ httplib2 FAILED: {type(e).__name__}: {e}")
    print()

# Test 2: requests
print("\n2) Testing requests...")
try:
    import requests
    
    print("   Attempting connection to www.googleapis.com...")
    response = requests.get("https://www.googleapis.com/", timeout=10)
    print(f"   ✅ requests works - Status: {response.status_code}")
except Exception as e:
    print(f"   ❌ requests FAILED: {type(e).__name__}: {e}")
    print()

# Test 3: urllib
print("\n3) Testing urllib...")
try:
    import urllib.request
    
    print("   Attempting connection to www.googleapis.com...")
    response = urllib.request.urlopen("https://www.googleapis.com/", timeout=10)
    print(f"   ✅ urllib works - Status: {response.status}")
except Exception as e:
    print(f"   ❌ urllib FAILED: {type(e).__name__}: {e}")
    print()

print("\n" + "="*60)
print("CONCLUSION:")
print("After macOS update, we need to switch from httplib2 to")
print("requests for Google API calls.")
print("="*60)
