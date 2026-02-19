#!/usr/bin/env python3
"""
Diagnóstico de conectividad a Gmail
Ayuda a identificar si el problema es de red, credenciales, o de Gmail API
"""

import sys
import socket
import time
from pathlib import Path

def test_internet():
    """Test basic internet connectivity"""
    print("🔍 Probando conexión a internet...")
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        print("✅ Internet: OK")
        return True
    except (socket.timeout, socket.error) as e:
        print(f"❌ Internet: FALLA - {e}")
        return False

def test_gmail_dns():
    """Test if Gmail API is reachable via DNS"""
    print("🔍 Probando DNS de Gmail API...")
    try:
        ip = socket.gethostbyname("www.googleapis.com")
        print(f"✅ Gmail API DNS: OK (IP: {ip})")
        return True
    except socket.error as e:
        print(f"❌ Gmail API DNS: FALLA - {e}")
        return False

def test_gmail_connection():
    """Test if we can connect to Gmail API endpoint"""
    print("🔍 Probando conexión al endpoint de Gmail...")
    try:
        sock = socket.create_connection(("www.googleapis.com", 443), timeout=10)
        sock.close()
        print("✅ Conexión a Gmail API: OK")
        return True
    except (socket.timeout, socket.error) as e:
        print(f"❌ Conexión a Gmail: TIMEOUT/FALLA - {e}")
        print("   Posibles causas:")
        print("   - WiFi lento o inestable")
        print("   - VPN/Proxy bloqueando conexión")
        print("   - Firewall del ISP")
        return False

def test_credentials():
    """Check if credentials and token files exist"""
    print("🔍 Verificando credenciales...")
    creds_ok = Path("credentials.json").exists()
    token_ok = Path("token.json").exists()
    
    if creds_ok:
        print("✅ credentials.json: Presente")
    else:
        print("❌ credentials.json: FALTA")
    
    if token_ok:
        print("✅ token.json: Presente")
    else:
        print("⚠️  token.json: No encontrado (se regenerará)")
    
    return creds_ok

def test_gmail_api():
    """Test actual Gmail API call"""
    print("🔍 Probando llamada a Gmail API...")
    try:
        from src.superagente86.gmail_agent import GmailAgent
        import datetime as dt
        
        gmail = GmailAgent(
            credentials_path='credentials.json',
            token_path='token.json',
            scopes=['https://www.googleapis.com/auth/gmail.readonly']
        )
        
        print("   Intentando fetch con timeout de 30 segundos...")
        start = time.time()
        messages = gmail.fetch_messages(
            label='newsletters',
            max_results=1,
            after_ts=dt.datetime(2026, 2, 16, tzinfo=dt.timezone.utc),
            before_ts=dt.datetime(2026, 2, 18, tzinfo=dt.timezone.utc)
        )
        elapsed = time.time() - start
        print(f"✅ Gmail API: OK ({len(messages)} mensajes, {elapsed:.1f}s)")
        return True
    except TimeoutError:
        print("❌ Gmail API: TIMEOUT")
        return False
    except Exception as e:
        print(f"❌ Gmail API: {type(e).__name__}: {e}")
        return False

def main():
    print("=" * 60)
    print("DIAGNÓSTICO DE GMAIL - Superagente86")
    print("=" * 60)
    print()
    
    results = {}
    
    # 1. Internet
    results['internet'] = test_internet()
    print()
    
    if not results['internet']:
        print("❌ Sin internet. Soluciona tu conexión y reintenta.")
        sys.exit(1)
    
    # 2. DNS
    results['dns'] = test_gmail_dns()
    print()
    
    if not results['dns']:
        print("❌ No se puede resolver Gmail API. Verifica tu DNS o firewall.")
        sys.exit(1)
    
    # 3. Conexión
    results['connection'] = test_gmail_connection()
    print()
    
    if not results['connection']:
        print("❌ No se puede conectar a Gmail API.")
        print("   Opciones:")
        print("   1. Cambia de red WiFi")
        print("   2. Desactiva VPN si la tienes")
        print("   3. Prueba desde una red diferente")
        sys.exit(1)
    
    # 4. Credenciales
    results['credentials'] = test_credentials()
    print()
    
    if not results['credentials']:
        print("❌ Falta credentials.json. Ve a Google Cloud Console & descárgalo")
        sys.exit(1)
    
    # 5. Gmail API call
    print("-" * 60)
    print("PRUEBA FINAL: Llamada a Gmail API")
    print("-" * 60)
    print()
    results['gmail_api'] = test_gmail_api()
    print()
    
    # Summary
    print("=" * 60)
    print("RESUMEN")
    print("=" * 60)
    for key, value in results.items():
        status = "✅" if value else "❌"
        print(f"{status} {key.upper()}")
    print()
    
    if all(results.values()):
        print("🎉 TODO OK! El pipeline debería funcionar.")
        sys.exit(0)
    else:
        print("❌ Hay problemas que necesitan solucionarse.")
        sys.exit(1)

if __name__ == "__main__":
    main()
