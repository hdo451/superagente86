"""
Monkey patch for httplib2 to work around macOS update blocking connections.
This increases socket timeout and disables SSL verification for Google API calls.
"""
import ssl
import socket as socketmodule
import httplib2

# Increase default socket timeout globally
socketmodule.setdefaulttimeout(120)

# Save original connect method
_original_connect = httplib2.HTTPSConnectionWithTimeout.connect

def patched_connect(self):
    """Connect with increased timeout and fallback to no SSL verification."""
    # First try: normal connection with long timeout
    try:
        self.timeout = 120  # 120 seconds
        return _original_connect(self)
    except (TimeoutError, OSError, ConnectionRefusedError) as e:
        # Fallback: create socket manually with no SSL verification
        print(f"⚠️  Normal connection failed ({e}), trying without SSL verification...")
        try:
            # Create SSL context with disabled verification
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            # Create and connect socket
            sock = socketmodule.socket(socketmodule.AF_INET, socketmodule.SOCK_STREAM)
            sock.settimeout(120)
            sock.connect((self.host, self.port))
            
            # Wrap with SSL
            self.sock = ctx.wrap_socket(sock, server_hostname=self.host)
            return self.sock
        except Exception as fallback_error:
            print(f"❌ Fallback also failed: {fallback_error}")
            raise

# Apply patch
httplib2.HTTPSConnectionWithTimeout.connect = patched_connect
print("✅ httplib2 patched for macOS compatibility (120s timeout, SSL fallback)")

