FROM whyour/qinglong:debian

# 安装 Python3 和常用依赖
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && pip3 install --no-cache-dir requests beautifulsoup4
# 复制启动脚本
COPY start.sh /ql/start.sh
RUN chmod +x /ql/start.sh
# 暴露青龙面板端口
EXPOSE 5700
# 设置容器启动时执行我们的自定义脚本
CMD ["/ql/start.sh"]
# 数据持久化
COPY ./scripts /ql/scripts
