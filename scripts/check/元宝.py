#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 添加任务
"""
name: 元宝bot
tag: 抢注
cron: 55 11 * * *
cron: 55 19 * * *
"""
"""
=============================================================================
元宝派 - 免费 Bot 创建脚本【多线程并发修复增强版】
=============================================================================
定时规则
上午场:    11:55 启动抢 12:00
晚间场: 55 19 * * *   19:55 启动抢 20:00
环境变量
单账号: YUANBAO_COOKIE = 完整Cookie
多账号: YUANBAO_COOKIE 多个Cookie用 换行/& 分隔
=============================================================================
"""

import os
import requests
import time
import re
import threading
from concurrent.futures import ThreadPoolExecutor

# 青龙推送兼容
try:
    from notify import send
    SEND_FLAG = True
except Exception:
    SEND_FLAG = False
    def send(title: str, content: str) -> None:
        print(f"[推送] {title}: {content}")

# ==================== 可配置参数 ====================
ADVANCE_SECONDS = 300       # 提前几秒开始(默认5分钟)
MAX_RETRY_SECONDS = 120     # 整点后继续抢几秒(默认2分钟)
THREAD_COUNT = 20           # 并发线程 10~30 为宜
REQUEST_INTERVAL = 0.05     # 单线程请求间隔
TIMEOUT = 8                 # 请求超时时间

# 全局控制
success_flag = False
request_count = 0
count_lock = threading.Lock()

def get_cookie_value(cookie_str, key):
    """提取Cookie字段"""
    match = re.search(rf'{key}=([^;]+)', cookie_str)
    return match.group(1) if match else None

def send_notify(title, content):
    """统一推送"""
    try:
        send(title, content)
        print("✅ 推送发送成功")
    except Exception as e:
        print(f"❌ 推送失败: {str(e)}")

def grab_bot(cookie):
    """单线程抢购任务"""
    global success_flag, request_count
    url = "https://yuanbao.tencent.com/api/v5/robotLogic/create"

    headers = {
        "Host": "yuanbao.tencent.com",
        "Origin": "https://yuanbao.tencent.com",
        "Referer": "https://yuanbao.tencent.com/e/claw/manage",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/148.0.0.0",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie,
    }
    payload = {"type": 1, "create_type": 1}

    while not success_flag:
        if time.time() > end_ts:
            break

        with count_lock:
            request_count += 1
            curr_cnt = request_count

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            if resp.status_code != 200:
                print(f"[{time.strftime('%H:%M:%S')}] 第{curr_cnt}次 HTTP{resp.status_code}")
                time.sleep(REQUEST_INTERVAL)
                continue

            data = resp.json()
            code = data.get("code", -1)
            msg = data.get("msg", "")

            if code == 0:
                success_flag = True
                print(f"\n[{time.strftime('%H:%M:%S')}] ✅ 抢购成功！总请求: {curr_cnt} | 提示: {msg}")
                return True
            else:
                print(f"[{time.strftime('%H:%M:%S')}] 第{curr_cnt}次 失败 code:{code} {msg}")

        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] 第{curr_cnt}次 异常: {str(e)[:30]}")

        time.sleep(REQUEST_INTERVAL)
    return False

def main():
    global end_ts
    cookie_raw = os.environ.get("YUANBAO_COOKIE", "").strip()
    if not cookie_raw:
        print("❌ 未配置环境变量 YUANBAO_COOKIE")
        return

    # 分割多账号
    cookie_list = [c.strip() for c in cookie_raw.replace("&", "\n").splitlines() if c.strip()]
    print(f"✅ 加载账号数量: {len(cookie_list)}")

    # 校验每个Cookie
    valid_cookies = []
    for idx, ck in enumerate(cookie_list, 1):
        token = get_cookie_value(ck, "hy_token")
        user = get_cookie_value(ck, "hy_user")
        if token and user:
            valid_cookies.append(ck)
            print(f"✅ 账号{idx} 校验通过")
        else:
            print(f"❌ 账号{idx} Cookie无效，跳过")

    if not valid_cookies:
        print("❌ 无有效Cookie，退出")
        return

    # 判定目标场次
    now = time.localtime()
    hour, minute = now.tm_hour, now.tm_min
    target_list = []

    # 匹配12点场
    if (hour == 11 and minute >= 55) or hour == 12:
        target_list.append((12, 0, "12:00 午场"))
    # 匹配20点场
    if (hour == 19 and minute >= 55) or hour == 20:
        target_list.append((20, 0, "20:00 晚场"))

    if not target_list:
        print("⚠️ 当前不在抢购时段，脚本退出")
        return

    target_h, target_m, target_name = target_list[0]
    # 构造目标时间戳
    target_tm = (now.tm_year, now.tm_mon, now.tm_mday, target_h, target_m, 0,
                 now.tm_wday, now.tm_yday, now.tm_isdst)
    target_ts = time.mktime(target_tm)
    start_ts = target_ts - ADVANCE_SECONDS
    end_ts = target_ts + MAX_RETRY_SECONDS
    now_ts = time.time()

    print(f"\n==================== {target_name} 抢购 ====================")
    print(f"开始时间: {time.strftime('%H:%M:%S', time.localtime(start_ts))}")
    print(f"结束时间: {time.strftime('%H:%M:%S', time.localtime(end_ts))}")
    print(f"并发线程: {THREAD_COUNT}")
    print("===========================================================\n")

    # 等待到开始时间
    if now_ts < start_ts:
        wait_sec = start_ts - now_ts
        print(f"⏰ 等待 {int(wait_sec)} 秒后开始...")
        time.sleep(wait_sec)
    elif now_ts > end_ts:
        print("⚠️ 已超过抢购截止时间，退出")
        return

    # 线程池执行
    with ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
        # 循环分配有效账号
        tasks = []
        for i in range(THREAD_COUNT):
            ck = valid_cookies[i % len(valid_cookies)]
            tasks.append(executor.submit(grab_bot, ck))

        # 轮询等待结束
        while not success_flag and time.time() < end_ts:
            time.sleep(0.2)

    # 结果处理
    if success_flag:
        title = f"元宝派 {target_name} 抢购成功"
        content = f"场次: {target_name}\n总请求数: {request_count}\n并发线程: {THREAD_COUNT}"
        send_notify(title, content)
    else:
        print(f"\n⏰ 抢购结束，未抢到名额，总请求: {request_count}")
        send_notify(f"元宝派 {target_name} 抢购失败", f"场次: {target_name}\n总请求数: {request_count}")

if __name__ == "__main__":
    print("========== 元宝派 Bot 多线程抢购脚本 启动 ==========")
    main()
