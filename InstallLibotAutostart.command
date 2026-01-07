#!/bin/zsh
set -euo pipefail

# Install a per-user LaunchAgent to start Libot.app at login.
# Usage:
#   ./InstallLibotAutostart.command /Applications/Libot.app
# If not provided, defaults to /Applications/Libot.app

APP_PATH="${1:-/Applications/Libot.app}"

if [[ ! -d "$APP_PATH" ]]; then
  echo "ERROR: 找不到 .app：$APP_PATH"
  echo "请把 Libot.app 放到 /Applications，或把路径作为参数传入。"
  exit 1
fi

# Escape XML special chars.
xml_escape() {
  local s="$1"
  s="${s//&/&amp;}"
  s="${s//</&lt;}"
  s="${s//>/&gt;}"
  s="${s//\"/&quot;}"
  echo "$s"
}

APP_PATH_XML="$(xml_escape "$APP_PATH")"
PLIST="$HOME/Library/LaunchAgents/cn.zju.libot.plist"

mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>cn.zju.libot</string>

  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/open</string>
    <string>-a</string>
    <string>$APP_PATH_XML</string>
  </array>

  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
EOF

# Reload agent
launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"

echo "OK: 已设置开机自启动（当前用户）。"
echo "- LaunchAgent: $PLIST"
echo "- 取消自启动：launchctl unload \"$PLIST\" && rm \"$PLIST\""
