#!/bin/sh
# 晚星守护启动脚本：崩溃自动拉起（宿主若有 systemd / docker restart 也能接管）
cd /app
while true; do
  echo "[$(date '+%F %T')] 启动 晚星..." >> /app/agent_stdout.log
  python main.py >> /app/agent_stdout.log 2>&1
  echo "[$(date '+%F %T')] 进程退出，5秒后重启" >> /app/agent_stdout.log
  sleep 5
done
