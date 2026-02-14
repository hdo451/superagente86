#!/bin/bash
# Install launchd schedule for superagente86 newsletter pipeline
# Runs at 08:30 and 13:30 daily (US/Pacific)

set -e

PLIST_NAME="com.superagente86.newsletter"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"
LOG_DIR="${PROJECT_DIR}/logs"
ENV_FILE="${PROJECT_DIR}/.env"

mkdir -p "$LOG_DIR"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Virtual environment not found at ${VENV_PYTHON}"
    echo "Run: python3 -m venv .venv && .venv/bin/pip install -e ."
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found at ${ENV_FILE}"
    echo "Please create .env with GEMINI_API_KEY and other credentials"
    exit 1
fi

# Build environment variables dict from .env file
ENV_VARS=""
while IFS='=' read -r key value; do
    # Skip comments and empty lines
    [[ "$key" =~ ^#.*$ ]] && continue
    [[ -z "$key" ]] && continue
    
    # Remove quotes if present
    value="${value%\"}"
    value="${value#\"}"
    
    ENV_VARS+="        <key>${key}</key>
        <string>${value}</string>
"
done < "$ENV_FILE"

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${VENV_PYTHON}</string>
        <string>-m</string>
        <string>superagente86.cli</string>
        <string>--config</string>
        <string>${PROJECT_DIR}/config.yaml</string>
        <string>--state-file</string>
        <string>${PROJECT_DIR}/data/state.json</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
${ENV_VARS}    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>StartInterval</key>
    <integer>1800</integer>

    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key>
            <integer>8</integer>
            <key>Minute</key>
            <integer>30</integer>
        </dict>
        <dict>
            <key>Hour</key>
            <integer>13</integer>
            <key>Minute</key>
            <integer>30</integer>
        </dict>
    </array>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/newsletter.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/newsletter_error.log</string>
</dict>
</plist>
EOF

# Unload existing if present
launchctl bootout "gui/$(id -u)/${PLIST_NAME}" 2>/dev/null || true

# Load the new plist
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"

echo "✅ Schedule installed!"
echo "   Reports will run at 08:30 and 13:30 daily (US/Pacific)."
echo "   Catch-up enabled: runs at login and every 30 minutes if missed."
echo "   Plist: ${PLIST_PATH}"
echo "   Logs:  ${LOG_DIR}/"
echo ""
echo "To check status: launchctl print gui/$(id -u)/${PLIST_NAME}"
echo "To uninstall: launchctl bootout gui/$(id -u)/${PLIST_NAME}"
