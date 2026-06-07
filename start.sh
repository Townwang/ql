#!/bin/bash

# 后台启动青龙
/ql/start.sh &
sleep 25

# ========== 在这里修改为你的订阅地址 ==========
SUB_URL="https://github.com/Townwang/ql.git"
# ============================================

# 写入青龙订阅配置（重启不丢失，面板订阅管理可见）
ql config repo add "$SUB_URL"

# 拉取订阅脚本
ql repo "$SUB_URL" "" "" "" main

# 前台保持运行
wait
