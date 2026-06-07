#!/bin/bash

# 定义一个函数来添加青龙订阅
add_ql_repo() {
    echo "开始添加青龙订阅..."
    
    # 这里添加你的第一个订阅仓库
    # 格式: ql repo <仓库URL> <白名单> <黑名单> <依赖文件> <分支>
    # 示例：ql repo https://github.com/你的账号/qinglong-render.git "" "" "" main
    ql repo https://github.com/Townwang/ql.git
    
    # 如果需要添加多个仓库，可以在这里继续添加
    # ql repo https://github.com/其他作者/其他仓库.git "" "" "" main
    
    echo "订阅添加完成"
}

# 执行订阅添加函数
add_ql_repo

# 启动青龙面板主程序
echo "启动青龙面板..."
exec ./start.sh
