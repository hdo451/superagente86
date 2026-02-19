#!/usr/bin/env python3
"""Test Python HTTPS connectivity after macOS update"""

import socket
import sys

# Force IPv4 to avoid IPv6 issues
socket.setdefaulttimeout(10)

print("Testing Python network connectivity...")
print(f"Python version: {sys.version}")
print()

# Test 1: Basic socket connection
print("1) Testing raw socket connection to Google...")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(("8.8.8.8", 443))
    print("   ✅ Socket connection OK")
    sock.close()
except Exception as e:
    print(f"   ❌ Socket connection failed: {e}")
    sys.exit(1)

# Test 2: DNS resolution
print("\n2) Testing DNS resolution...")
try:
    ip = socket.gethostbyname("www.google.com")
    print(f"   ✅ DNS OK - www.google.com = {ip}")
except Exception as e:
    print(f"   ❌ DNS failed: {e}")
    sys.exit(1)

# Test 3: Connection to Gmail API
print("\n3) Testing connection to Gmail API...")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    # Get IP of googleapis.com
    ip = socket.gethostbyname("www.googleapis.com")
    print(f"   Connecting to {ip}:443...")
    sock.connect((ip, 443))
    print("   ✅ Connection to Gmail API OK")
    sock.close()
except Exception as e:
    print(f"   ❌ Connection failed: {e}")
    sys.exit(1)

print("\n4) Testing HTTPS with urllib...")
try:
    import urllib.request
    # Set short timeout
    req = urllib.request.Request("https://www.google.com")
    response = urllib.request.urlopen(req, timeout=10)
    print(f"   ✅ HTTPS OK - Status: {response.status}")
except Exception as e:
    print(f"   ❌ HTTPS failed: {e}")
    print("\n🔍 This suggests macOS is blocking Python's HTTPS connections.")
    print("   Possible causes:")
    print("   - macOS Firewall blocking Python")
    print("   - macOS System Integrity Protection (SIP) blocking network access")
    print("   - SSL/TLS certificate trust issues")
    print("   - VPN or proxy configuration")
    sys.exit(1)

print("\n✅ All tests passed! Python network access is working.")
sys.exit(0)
