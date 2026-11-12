#!/bin/bash
LOG_FILE="/home/ztl/rk-agent/watchdog.log"
NET_FAIL_FILE="/tmp/watchdog_net_fail"
BOT_FAIL_FILE="/tmp/watchdog_bot_fail"
TS_FAIL_FILE="/tmp/watchdog_ts_fail"

# 初始化计数器
[ ! -f "$NET_FAIL_FILE" ] && echo 0 > "$NET_FAIL_FILE"
[ ! -f "$BOT_FAIL_FILE" ] && echo 0 > "$BOT_FAIL_FILE"
[ ! -f "$TS_FAIL_FILE" ] && echo 0 > "$TS_FAIL_FILE"

# ==================== 1. 监测外网 ====================
ping -c 2 -W 2 223.5.5.5 > /dev/null 2>&1
if [ $? -ne 0 ]; then
    count=$(cat "$NET_FAIL_FILE")
    if [ "$count" -lt 5 ]; then
        echo "$(date) - 🚨 外网断开，重启 NetworkManager (尝试 $((count+1))/5)" >> "$LOG_FILE"
        systemctl restart NetworkManager
        echo $((count+1)) > "$NET_FAIL_FILE"
    fi
else
    echo 0 > "$NET_FAIL_FILE" # 网络通了，计数清零
fi

# ==================== 2. 监测 Tailscale ====================
if ! tailscale status 2>/dev/null | grep -q "100." || tailscale status 2>&1 | grep -q "unreachable"; then
    count=$(cat "$TS_FAIL_FILE")
    if [ "$count" -lt 5 ]; then
        echo "$(date) - 🚨 Tailscale 掉线，重启 tailscaled (尝试 $((count+1))/5)" >> "$LOG_FILE"
        systemctl restart tailscaled
        echo $((count+1)) > "$TS_FAIL_FILE"
    fi
else
    echo 0 > "$TS_FAIL_FILE"
fi

# ==================== 3. 监测晚星主程序 ====================
if ! pgrep -f "python main.py" > /dev/null; then
    count=$(cat "$BOT_FAIL_FILE")
    if [ "$count" -lt 5 ]; then
        echo "$(date) - 🚨 晚星进程死亡，尝试拉起 (尝试 $((count+1))/5)" >> "$LOG_FILE"
        cd /home/ztl/rk-agent
        source /home/ztl/venv/bin/activate
        # 使用 nohup 在后台静默拉起
        nohup python main.py > bot.log 2>&1 &
        echo $((count+1)) > "$BOT_FAIL_FILE"
    fi
else
    echo 0 > "$BOT_FAIL_FILE"
fi
