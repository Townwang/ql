#!/bin/bash
set -e

# 1. 先启动青龙后台，让它初始化完成
/ql/start.sh &
QL_PID=$!

# 2. 等待青龙初始化（关键！不然 ql repo 找不到命令/目录）
echo "⏳ 等待青龙初始化..."
sleep 20

# 3. 配置 git（避免首次提交报错）
git config --global user.name "render"
git config --global user.email "render@example.com"

# 4. 执行订阅（这里写你自己的仓库！）
echo "📦 开始添加订阅..."
ql repo https://github.com/Townwang/ql.git "" "" "" main

# 多仓库示例（取消注释用）
# ql repo https://github.com/xxx/xxx.git "jd_|jx_" "backUp" "^jd[^_]|USER" main

echo "✅ 订阅执行完毕"

# 5. 保持前台运行，防止容器退出
wait $QL_PID
