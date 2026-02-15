#!/bin/bash
# Install launchd schedule for superagente86 newsletter pipeline
# Runs at 08:30 and 13:30 daily (local time)

set -e

PLIST_NAME="com.superagente86.newsletter"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNNER="${PROJECT_DIR}/run_pipeline.sh"
LOG_DIR="${PROJECT_DIR}/logs"

mkdir -p "$LOG_DIR"

if [ ! -f "$RUNNER" ]; then
    echo "Error: Runner script not found at ${RUNNER}"
    echo "Expected run_pipeline.sh at project root"
    exit 1
fi

chmod +x "$RUNNER"

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
        <string>${RUNNER}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

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
echo "   Reports will run at 08:30 and 13:30 daily (local time)."
echo "   Catch-up enabled: runs at login and every 30 minutes if missed."
echo "   Plist: ${PLIST_PATH}"
echo "   Logs:  ${LOG_DIR}/"
echo ""
echo "To check status: launchctl print gui/$(id -u)/${PLIST_NAME}"
echo "To uninstall: launchctl bootout gui/$(id -u)/${PLIST_NAME}"
