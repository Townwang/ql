# 订阅
> 青龙 → 订阅管理 → 编辑你的订阅 → 高级设置 → 执行前脚本

## Python依赖after安装
```shell
if [ -f "/ql/data/repo/Townwang_ql_main/requirements.txt" ]; then
  pip install -r /ql/data/repo/Townwang_ql_main/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
fi
```

## node js依赖安装
```shell
cd /ql/data/scripts && npm install --registry=https://registry.npmmirror.com
```
