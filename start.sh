#!/bin/bash
set -e

# 定义你的订阅仓库地址，此处务必修改为你自己的链接
SUB_REPO="https://github.com/Townwang/ql.git"

# 1. 后台启动青龙主进程
/ql/start.sh &
sleep 25

# 2. 重置登录账号密码：admin / 123456
curl -X PUT "http://127.0.0.1:5700/open/user/init" \
-H "Content-Type: application/json" \
-d '{"username":"hunter","password":"zhen521"}'

# 3. 执行订阅拉取脚本
echo "开始拉取订阅脚本..."
ql repo "${SUB_REPO}" "" "" "" main
echo "订阅拉取完成"

# 保持容器前台运行，防止意外退出
wait
