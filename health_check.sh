#!/bin/bash
# Health check for superagente86 newsletter pipeline
# Shows status of scheduling, last run, and any errors

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_FILE="${PROJECT_DIR}/data/state.json"
LOG_FILE="${PROJECT_DIR}/logs/newsletter.log"
ERROR_LOG="${PROJECT_DIR}/logs/newsletter_error.log"
PLIST_NAME="com.superagente86.newsletter"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "🔍 Health Check for Superagente86 Newsletter Pipeline"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check 1: Is launchd installed?
echo "1️⃣  LAUNCHD SCHEDULER STATUS"
if [ -f "$PLIST_PATH" ]; then
    echo "   ✅ Plist file exists: $PLIST_PATH"
    
    # Check if it's loaded
    if launchctl print "gui/$(id -u)/${PLIST_NAME}" &>/dev/null; then
        echo "   ✅ Scheduler is ACTIVE and loaded"
        
        # Show next run times
        echo ""
        echo "   📅 Scheduled times:"
        echo "      - 08:30 AM (Pacific Time)"
        echo "      - 01:30 PM (Pacific Time)"
        echo ""
        
        # Try to get more details
        launchctl print "gui/$(id -u)/${PLIST_NAME}" | grep -E "state|pid|exit" || true
    else
        echo "   ⚠️  Scheduler is NOT loaded/active"
        echo "   To activate: launchctl bootstrap gui/\$(id -u) $PLIST_PATH"
    fi
else
    echo "   ❌ Plist not found. Schedule not installed."
    echo "   To install: ./install_schedule.sh"
fi
echo ""

# Check 2: State file
echo "2️⃣  LAST RUN STATE"
if [ -f "$STATE_FILE" ]; then
    echo "   State file: $STATE_FILE"
    echo ""
    
    # Extract key info
    last_run=$(grep -o '"last_run": "[^"]*"' "$STATE_FILE" | cut -d'"' -f4 || echo "unknown")
    last_count=$(grep -o '"last_count": [0-9]*' "$STATE_FILE" | cut -d' ' -f2 || echo "0")
    last_doc=$(grep -o '"last_doc_id": "[^"]*"' "$STATE_FILE" | cut -d'"' -f4 || echo "none")
    
    echo "   Last Run:     $last_run"
    echo "   Items Found:  $last_count"
    echo "   Doc Created:  ${last_doc:0:30}..."
    echo ""
    
    # Check if review had issues
    if grep -q '"is_good": false' "$STATE_FILE"; then
        echo "   ⚠️  LAST REVIEW FAILED"
        echo ""
        grep -o '"summary": "[^"]*"' "$STATE_FILE" | cut -d'"' -f4 || true
        echo ""
        echo "   Issues found:"
        grep -o '"issues": \[' -A 100 "$STATE_FILE" | grep '"\|' | head -5
        echo ""
    elif grep -q '"is_good": true' "$STATE_FILE"; then
        echo "   ✅ Last review passed"
        echo ""
    fi
else
    echo "   ❌ State file not found: $STATE_FILE"
    echo "   (Will be created after first run)"
fi
echo ""

# Check 3: Log files
echo "3️⃣  RECENT LOGS"
if [ -f "$LOG_FILE" ]; then
    echo "   Log file: $LOG_FILE"
    echo ""
    echo "   📄 Last 10 lines:"
    tail -10 "$LOG_FILE" | sed 's/^/      /'
    echo ""
else
    echo "   ℹ️  No log file yet (will be created on first run)"
fi

if [ -f "$ERROR_LOG" ]; then
    echo ""
    echo "   ⚠️  Recent errors detected:"
    tail -5 "$ERROR_LOG" | sed 's/^/      /'
    echo ""
fi
echo ""

# Check 4: Common errors
echo "4️⃣  COMMON ISSUES TO CHECK"
echo ""
echo "   ❌ Rate Limit (429 error):"
if grep -q "429" "$LOG_FILE" "$ERROR_LOG" 2>/dev/null; then
    echo "      → YES, quota exceeded for Gemini API"
    echo "      → Free tier limited to 20 requests/day"
    echo "      → Will resume tomorrow"
else
    echo "      ✅ No rate limit errors found"
fi
echo ""

echo "   ❌ Authentication Errors:"
if grep -q "authentication\|unauthorized\|401\|403" "$LOG_FILE" "$ERROR_LOG" 2>/dev/null; then
    echo "      → YES, auth error detected"
    echo "      → Check Google API credentials"
else
    echo "      ✅ No auth errors found"
fi
echo ""

echo "   ❌ Gmail Errors:"
if grep -q "gmail\|email" "$ERROR_LOG" 2>/dev/null; then
    echo "      → Check logs for details"
else
    echo "      ✅ No Gmail errors found"
fi
echo ""

# Check 5: Virtual environment
echo "5️⃣  ENVIRONMENT CHECK"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"
if [ -f "$VENV_PYTHON" ]; then
    echo "   ✅ Virtual environment found"
    python_version=$($VENV_PYTHON --version 2>&1)
    echo "      $python_version"
else
    echo "   ❌ Virtual environment NOT found at $VENV_PYTHON"
    echo "      Run: python3 -m venv .venv && .venv/bin/pip install -e ."
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 SUMMARY & NEXT STEPS:"
echo ""

if [[ $last_run == *"T"* ]]; then
    echo "   ✅ System is working"
    echo "      → If no doc: review may have failed or rate limited"
    echo "      → Check logs above for details"
else
    echo "   ⚠️  No recent runs detected"
    echo "      → Check if scheduler is loaded (item 1)"
    echo "      → Check if logs directory is writable"
fi
echo ""
echo "🔧 MANUAL RUN:"
echo "   source .venv/bin/activate"
echo "   python -m superagente86.cli --state-file data/state.json"
echo ""
echo "📞 SUPPORT:"
echo "   Check logs at: $LOG_FILE"
echo "   Unload scheduler: launchctl bootout gui/\$(id -u)/${PLIST_NAME}"
echo "   Reload scheduler: ./install_schedule.sh"
echo ""
