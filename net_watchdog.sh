#!/bin/bash
LOG_FILE="/home/ztl/rk-agent/watchdog.log"
NET_FAIL_FILE="/tmp/watchdog_net_fail"
BOT_FAIL_FILE="/tmp/watchdog_bot_fail"

[ ! -f "$NET_FAIL_FILE" ] && echo 0 > "$NET_FAIL_FILE"
[ ! -f "$BOT_FAIL_FILE" ] && echo 0 > "$BOT_FAIL_FILE"

# ==================== 1. 核心守护：确保 eth1 有 IP ====================
if ! ip -4 addr show eth1 | grep -q "inet "; then
    echo "$(date) - 🚨 eth1 缺失 IP，尝试重新拉起静态网络..." >> "$LOG_FILE"
    nmcli connection up "eth1-static" >> "$LOG_FILE" 2>&1
fi

# ==================== 2. 监测外网 ====================
ping -c 2 -W 2 223.5.5.5 > /dev/null 2>&1
if [ $? -ne 0 ]; then
    count=$(cat "$NET_FAIL_FILE")
    if [ "$count" -lt 5 ]; then
        echo "$(date) - 🚨 外网断开，重启 NetworkManager (尝试 $((count+1))/5)" >> "$LOG_FILE"
        systemctl restart NetworkManager
        echo $((count+1)) > "$NET_FAIL_FILE"
    fi
else
    echo 0 > "$NET_FAIL_FILE"
fi

# ==================== 3. 监测晚星主程序 ====================
if ! pgrep -f "python main.py" > /dev/null; then
    count=$(cat "$BOT_FAIL_FILE")
    if [ "$count" -lt 5 ]; then
        echo "$(date) - 🚨 晚星进程死亡，尝试拉起 (尝试 $((count+1))/5)" >> "$LOG_FILE"
        cd /home/ztl/rk-agent
        source /home/ztl/venv/bin/activate
        nohup python main.py > bot.log 2>&1 &
        echo $((count+1)) > "$BOT_FAIL_FILE"
    fi
else
    echo 0 > "$BOT_FAIL_FILE"
fi
