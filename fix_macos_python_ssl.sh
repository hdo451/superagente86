#!/bin/bash
# Fix Python SSL certificates on macOS after system update

echo "🔧 Reparando configuración SSL de Python en macOS..."
echo ""

# 1. Verificar versión de Python
echo "1️⃣  Python version:"
python3 --version
echo ""

# 2. Reinstalar certificados SSL de Python
echo "2️⃣  Reinstalando certificados SSL de Python..."
if [ -f "/Applications/Python 3.13/Install Certificates.command" ]; then
    echo "   Ejecutando instalador de certificados de Python 3.13..."
    /Applications/Python\ 3.13/Install\ Certificates.command
elif [ -f "/Applications/Python 3.12/Install Certificates.command" ]; then
    echo "   Ejecutando instalador de certificados de Python 3.12..."
    /Applications/Python\ 3.12/Install\ Certificates.command
elif [ -f "/Applications/Python 3.11/Install Certificates.command" ]; then
    echo "   Ejecutando instalador de certificados de Python 3.11..."
    /Applications/Python\ 3.11/Install\ Certificates.command
else
    echo "   ⚠️  No se encontró el instalador de certificados"
    echo "   Instalando certifi manualmente..."
    pip3 install --upgrade certifi
fi
echo ""

# 3. Actualizar certifi en el entorno virtual
echo "3️⃣  Actualizando certifi en el entorno virtual..."
source .venv/bin/activate
pip install --upgrade certifi requests urllib3
echo ""

# 4. Verificar ubicación de certificados
echo "4️⃣  Ubicación de certificados SSL:"
python3 -c "import ssl; print(ssl.get_default_verify_paths())"
echo ""

# 5. Test de conexión HTTPS con Python
echo "5️⃣  Test de conexión HTTPS con Python:"
python3 << 'EOF'
import ssl
import socket
import requests

# Test 1: Conexión básica con socket
print("   Test 1: Socket SSL a Google...")
try:
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    
    with socket.create_connection(("www.google.com", 443), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname="www.google.com") as ssock:
            print(f"   ✅ Conexión SSL OK - Protocolo: {ssock.version()}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 2: Requests a Gmail API
print("\n   Test 2: Requests a Gmail API...")
try:
    r = requests.get("https://www.googleapis.com/gmail/v1/users/me/labels", timeout=10)
    print(f"   ✅ Requests OK - Status: {r.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")
EOF

echo ""
echo "6️⃣  Configuraciones de red de macOS..."
echo "   Proxy HTTP:"
networksetup -getwebproxy Wi-Fi 2>/dev/null || echo "   No configurado"
echo "   Proxy HTTPS:"
networksetup -getsecurewebproxy Wi-Fi 2>/dev/null || echo "   No configurado"
echo ""

echo "✅ Diagnóstico completo"
