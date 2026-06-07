FROM whyour/qinglong:debian

# 安装基础依赖：git、curl、python 环境
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget ca-certificates \
    python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# 安装常用 Python 依赖
RUN pip3 install --no-cache-dir requests beautifulsoup4

# 拷贝自定义启动脚本并授权
COPY start.sh /ql/start.sh
RUN chmod +x /ql/start.sh

# 预设时区，解决证书/时间异常
ENV TZ=Asia/Shanghai
# 暴露青龙面板端口
EXPOSE 5700
CMD ["/ql/start.sh"]

# 数据持久化
COPY ./scripts /ql/scripts