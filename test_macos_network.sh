#!/bin/bash
# Test de conectividad post-actualización de macOS
# Identifica si el firewall/red está bloqueando Gmail API

echo "=================================================="
echo "DIAGNÓSTICO DE RED - Post-actualización de macOS"
echo "=================================================="
echo ""

# 1. Test básico de internet
echo "1️⃣  Test de internet básico..."
if ping -c 2 8.8.8.8 > /dev/null 2>&1; then
    echo "✅ Internet funcionando (ping a 8.8.8.8)"
else
    echo "❌ Sin internet - verifica tu WiFi"
    exit 1
fi
echo ""

# 2. DNS de Gmail API
echo "2️⃣  Test DNS de Gmail API..."
if host www.googleapis.com > /dev/null 2>&1; then
    IP=$(host www.googleapis.com | grep "has address" | head -1 | awk '{print $4}')
    echo "✅ DNS OK - www.googleapis.com = $IP"
else
    echo "❌ DNS fallando - problema con resolución de nombres"
fi
echo ""

# 3. Conexión HTTPS con curl (timeout 10s)
echo "3️⃣  Test de conexión HTTPS a Gmail API..."
echo "   (timeout: 10 segundos)"
if curl -v -m 10 https://www.googleapis.com > /dev/null 2>&1; then
    echo "✅ Conexión HTTPS OK"
else
    echo "❌ Conexión HTTPS FALLA - este es probablemente el problema"
    echo "   Causas posibles:"
    echo "   - Firewall de macOS bloqueando"
    echo "   - Proxy configurado"
    echo "   - VPN interfiriendo"
fi
echo ""

# 4. Check firewall status
echo "4️⃣  Estado del Firewall de macOS..."
if [[ $(sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate 2>/dev/null | grep -i "enabled") ]]; then
    echo "⚠️  Firewall ACTIVADO"
    echo "   Ve a: System Settings > Network > Firewall"
    echo "   Verifica que Terminal/Python puedan hacer conexiones"
else
    echo "✅ Firewall desactivado o no bloqueando"
fi
echo ""

# 5. Check proxy settings
echo "5️⃣  Configuración de Proxy..."
WEB_PROXY=$(networksetup -getwebproxy Wi-Fi 2>/dev/null | grep "Enabled: Yes")
SECURE_PROXY=$(networksetup -getsecurewebproxy Wi-Fi 2>/dev/null | grep "Enabled: Yes")

if [[ -n "$WEB_PROXY" ]] || [[ -n "$SECURE_PROXY" ]]; then
    echo "⚠️  HAY PROXY CONFIGURADO"
    echo "   Esto puede estar causando el problema"
    echo ""
    networksetup -getwebproxy Wi-Fi
    networksetup -getsecurewebproxy Wi-Fi
else
    echo "✅ Sin proxy configurado"
fi
echo ""

# 6. Test específico de Gmail API con timeout corto
echo "6️⃣  Test directo a Gmail API endpoint..."
echo "   (Probando: https://gmail.googleapis.com)"
START=$(date +%s)
if curl -m 5 https://gmail.googleapis.com > /dev/null 2>&1; then
    END=$(date +%s)
    ELAPSED=$((END - START))
    echo "✅ Gmail API accesible en ${ELAPSED}s"
else
    echo "❌ Gmail API NO ACCESIBLE (timeout después de 5s)"
    echo ""
    echo "   🔥 PROBLEMA CONFIRMADO: macOS está bloqueando Gmail API"
fi
echo ""

# 7. Recommendations
echo "=================================================="
echo "RECOMENDACIONES"
echo "=================================================="
echo ""
echo "Si viste ❌ en los tests 3 o 6, prueba esto:"
echo ""
echo "1. REINICIAR TU MAC"
echo "   → Muchas veces resuelve problemas post-actualización"
echo ""
echo "2. DESACTIVAR FIREWALL TEMPORALMENTE"
echo "   System Settings > Network > Firewall > Turn Off"
echo "   Luego prueba el pipeline de nuevo"
echo ""
echo "3. VERIFICAR PERMISOS DE RED"
echo "   System Settings > Privacy & Security > Network"
echo "   Asegúrate que Terminal tenga permiso"
echo ""
echo "4. CAMBIAR DE RED WiFi"
echo "   Conéctate a otra red y prueba"
echo ""
echo "5. SI NADA FUNCIONA: Usar VPN diferente"
echo "   O conectar por hotspot desde tu teléfono"
echo ""
