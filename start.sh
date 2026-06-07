#!/bin/bash
set -e

# 1. 先启动青龙后台
/ql/start.sh &
QL_PID=$!
sleep 25

# 2. 你的订阅配置（在这里改！）
SUB_NAME="我的脚本库"
SUB_URL="https://github.com/Townwang/ql.git"
SUB_BRANCH="main"
SUB_SCHEDULE="0 0 * * *"  # 每天0点自动更新

# 3. 写入订阅数据库（面板直接可见）
cat > /ql/db/subscribe.json <<EOF
[
  {
    "name": "$SUB_NAME",
    "url": "$SUB_URL",
    "branch": "$SUB_BRANCH",
    "schedule": "$SUB_SCHEDULE",
    "whitelist": "",
    "blacklist": "",
    "status": 0,
    "createdAt": "$(date -Iseconds)"
  }
]
EOF

# 4. 拉取脚本（首次同步）
ql repo "$SUB_URL" "" "" "" "$SUB_BRANCH"

# 5. 保持前台运行
wait $QL_PID
