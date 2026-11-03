#!/bin/bash
# 双击运行：安装依赖 + 设置开机自启 + 启动插件
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"

if ! command -v python3 >/dev/null; then
  echo "没有找到 python3，请先安装：https://www.python.org/downloads/macos/"
  read -p "按回车退出"; exit 1
fi

echo "==> 创建虚拟环境"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
echo "==> 安装依赖"
pip install -r requirements.txt -q
echo "==> 下载浏览器内核（第一次需要几分钟）"
python -m playwright install chromium

echo "==> 设置登录时自动启动"
PLIST="$HOME/Library/LaunchAgents/com.parcelwidget.app.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.parcelwidget.app</string>
  <key>ProgramArguments</key><array>
    <string>$DIR/.venv/bin/python</string><string>$DIR/app.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>StandardOutPath</key><string>/tmp/parcelwidget.out</string>
  <key>StandardErrorPath</key><string>/tmp/parcelwidget.err</string>
</dict></plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "==> 完成！插件已启动，以后登录 Mac 会自动打开。"
