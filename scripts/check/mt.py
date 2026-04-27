#!/usr/bin/env python3
# ======================================
# name: MT签到-Cookie修复版
# cron: 1 9 * * *
# instance: single
# ======================================

import requests
import re
import os
import time
import random
from datetime import datetime

class MTBBS:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 15; RMX3852 Build/UKQ1.231108.001) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.7339.208 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Referer': 'https://bbs.binmt.cc/forum.php',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
            'Sec-Fetch-Dest': 'document',
        }
        
        # 从环境变量读取Cookie，格式完整的Cookie字符串
        self.cookie_str = os.getenv("MT_COOKIE", "").strip()
        if self.cookie_str:
            self.headers['Cookie'] = self.cookie_str

    def safe_request(self, url, method='GET', data=None, retry=3):
        """安全请求函数，增加重试次数和延迟"""
        for attempt in range(retry):
            try:
                headers = self.headers.copy()
                # 每次请求随机加一点延迟，降低风控概率
                time.sleep(random.uniform(0.5, 2))
                if method.upper() == 'GET':
                    response = self.session.get(url, headers=headers, timeout=20)
                else:
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                    response = self.session.post(url, data=data, headers=headers, timeout=20)
                
                if response.status_code in (200, 302):
                    return response
                else:
                    print(f"请求失败，状态码: {response.status_code}")
            except Exception as e:
                print(f"请求异常: {str(e)}")
            
            if attempt < retry - 1:
                time.sleep(random.uniform(3, 6))
        
        return None

    def check_login(self):
        """校验Cookie是否有效"""
        print("正在校验Cookie登录状态...")
        check_url = "https://bbs.binmt.cc/forum.php"
        resp = self.safe_request(check_url)
        if not resp:
            return False, "访问论坛首页失败"
        
        # 判断是否已登录：页面不含登录按钮、含有用户名特征
        if "登录" not in resp.text or "个人中心" in resp.text:
            return True, "Cookie有效，已登录"
        else:
            return False, "Cookie失效，请重新获取"

    def sign_in(self):
        """签到功能"""
        print("正在签到...")
        
        # 访问签到页面
        sign_url = "https://bbs.binmt.cc/k_misign-sign.html"
        sign_resp = self.safe_request(sign_url)
        if not sign_resp:
            return "签到页面访问失败"
        
        # 打印页面前200字符，方便调试风控情况
        print("签到页面响应片段:", sign_resp.text[:200])
        
        # 提取formhash
        formhash_match = re.search(r'formhash=([a-f0-9]+)', sign_resp.text)
        if not formhash_match:
            return "formhash提取失败，可能触发了安全验证"
        
        formhash = formhash_match.group(1)
        
        # 执行签到
        sign_post_url = f"https://bbs.binmt.cc/plugin.php?id=k_misign:sign&operation=qiandao&format=text&formhash={formhash}"
        sign_result = self.safe_request(sign_post_url)
        
        if not sign_result:
            return "签到请求失败"
        
        result_text = sign_result.text.strip()
        
        if "今日已签" in result_text:
            return "今日已完成签到"
        elif "签到成功" in result_text:
            reward_match = re.search(r'获得奖励\s*(\S+)', result_text)
            reward = reward_match.group(1) if reward_match else "未知奖励"
            return f"签到成功！获得：{reward}"
        else:
            return f"签到异常：{result_text[:30]}"

    def get_credit(self):
        """获取积分信息"""
        credit_url = "https://bbs.binmt.cc/home.php?mod=spacecp&ac=credit"
        credit_resp = self.safe_request(credit_url)
        
        if not credit_resp:
            return "积分信息获取失败"
        
        info = []
        patterns = [
            (r'金币:\s*</span>(\d+)\s*&nbsp;', '金币'),
            (r'威望:\s*</span>(\d+)', '威望'),
            (r'热心:\s*</span>(\d+)', '热心'),
        ]
        
        for pattern, name in patterns:
            match = re.search(pattern, credit_resp.text)
            if match:
                info.append(f"{name}:{match.group(1)}")
        
        return " | ".join(info) if info else "积分数据提取失败"

    def run(self):
        """主运行流程"""
        print("=" * 30)
        print("MT论坛Cookie版签到开始")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 30)
        
        # 随机延迟
        time.sleep(random.uniform(2, 5))
        
        # 先校验Cookie
        if not self.cookie_str:
            result = "❌ 未配置MT_COOKIE环境变量"
            print(result)
            return result
        
        login_ok, login_msg = self.check_login()
        if not login_ok:
            result = f"❌ Cookie校验失败: {login_msg}"
            print(result)
            return result
        
        print("✅ Cookie有效，登录成功")
        time.sleep(random.uniform(1, 3))
        
        # 签到
        sign_msg = self.sign_in()
        print(f"签到结果: {sign_msg}")
        
        # 获取积分
        credit_info = self.get_credit()
        print(f"账户信息: {credit_info}")
        
        # 构造结果
        result = (
            f"【MT论坛Cookie签到结果】\n"
            f"签到: {sign_msg}\n"
            f"账户: {credit_info}\n"
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        return result

if __name__ == "__main__":
    try:
        mt = MTBBS()
        result = mt.run()
        
        print("\n" + "=" * 30)
        print("最终结果:")
        print(result)
        print("=" * 30)
        
    except Exception as e:
        error_msg = f"MT论坛签到异常: {str(e)}"
        print(error_msg)
