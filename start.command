#!/bin/bash
# 双击手动启动（需先运行过 install.command）
cd "$(dirname "$0")"
exec .venv/bin/python app.py
