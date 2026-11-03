#!/bin/bash
# 取消开机自启
PLIST="$HOME/Library/LaunchAgents/com.parcelwidget.app.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "已取消开机自启。数据保存在 ~/Library/Application Support/ParcelWidget"
