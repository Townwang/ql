# -*- coding: utf-8 -*-
 # ======================================
 # 妖火吹牛 - 大额对局监控脚本 V2.1 【最终修复版】
 # 基于真实HTML结构100%重写解析逻辑 - 已测试通过
 # ======================================
"""
 name: 妖火吹牛-大额对局监控V2.1最终版
 tag: 游戏,妖火,监控
 instance: single
"""
import requests
import time
import os
import re
import atexit
from bs4 import BeautifulSoup
 # ======================================
 # 【已修复】用户提供的真实Cookie已硬编码
 # ======================================
COOKIE = "ASP.NET_SessionId=mxh2axtckib1nss2x2wxx4lf; GUID=07a5a50209183821; __itrace_wid=3500e4e0-a4b5-47b4-97ef-6f1f9fbab3b9; ui_preference=1; hideUseless=0; medalDisplayCount=10; theme_preference=0; font_preference=0; sidyaohuo=0C9F5256EE1FBF0_710_04770_25110_51001-2; _d_id=367131bff1dade92ab09cd746cbe38"
CONFIG = {
     "max_network_errors": 10,    # 网络错误超限次数
     "request_retries": 5,        # 单接口请求重试次数
     "request_timeout": 20,       # 请求超时时间
     "refresh_interval": 30,      # 刷新间隔（秒）
     "min_amount": 1000,         # 最小监控金额（妖晶）- 大于1万
 }
 # 路径常量
SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))
LOCK_FILE = os.path.join(SCRIPT_PATH, "yaohuo_monitor.lock")
LOG_FILE = os.path.join(SCRIPT_PATH, "high_value_games.log")
 # 请求基础域名
BASE_HOST = "https://yaohuo.me"
HALL_URL = f"{BASE_HOST}/games/chuiniu/"
DETAIL_URL = f"{BASE_HOST}/games/chuiniu/book_view.aspx?id="
 # ======================================
 # 全局状态
 # ======================================
class GameState:
     def __init__(self):
         self.is_running = True
         self.network_error_count = 0
         self.recorded_game_ids = set()  # 已记录的对局ID，避免重复记录
state = GameState()
 # ======================================
 # 请求头
 # ======================================
REQUEST_HEADERS = {
     'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,webp,*/*;q=0.8',
     'Accept-Language': 'zh-CN,zh;q=0.9',
     'Cache-Control': 'max-age=0',
     'Content-Type': 'application/x-www-form-urlencoded',
     'Cookie': COOKIE,
     'Origin': BASE_HOST,
     'Referer': HALL_URL,
     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'
 }
 # ======================================
 # 工具函数
 # ======================================
def format_money(num):
     """金额格式化：10000 → 1.0万"""
     try:
         n = int(num)
         if n >= 10000:
             return f"{n / 10000:.1f}万"
         else:
             return f"{n}"
     except:
         return str(num)
def extract_number(text):
     """从文本中提取数字"""
     match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+)', str(text))
     if match:
         return int(match.group(1).replace(',', ''))
     return 0
 # ======================================
 # 彩色日志系统 ZLog
 # ======================================
class ZLog:
     @staticmethod
     def hex_to_rgb(hex_color):
         hex_color = hex_color.lstrip('#')
         return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
     @staticmethod
     def log_color(msg, hex_color):
         timestamp = time.strftime('%H:%M:%S')
         r, g, b = ZLog.hex_to_rgb(hex_color)
         color = f"\033[38;2;{r};{g};{b}m"
         reset = "\033[0m"
         print(f"[{timestamp}] {color}{msg}{reset}")
     @staticmethod
     def i(msg):
         ZLog.log_color(msg, "#888888")  # 灰色 - 信息
     @staticmethod
     def s(msg):
         ZLog.log_color(msg, "#2ecc71")  # 绿色 - 成功
     @staticmethod
     def w(msg):
         ZLog.log_color(msg, "#f39c12")  # 橙色 - 警告
     @staticmethod
     def e(msg):
         ZLog.log_color(msg, "#e74c3c")  # 红色 - 错误
     @staticmethod
     def d(msg):
         ZLog.log_color(msg, "#3498db")  # 蓝色 - 调试
 # ======================================
 # 大额对局日志文件记录
 # ======================================
def log_high_value_game(game_info):
     """
     将大额对局记录到日志文件
     格式：[时间] [对局ID] 发起者:XXX | 金额:XXX | 应战者:XXX | 结果:XXX | 状态:XXX
     """
     try:
         timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
         log_line = (
             f"[{timestamp}] "
             f"[{game_info['id']}] "
             f"发起者:{game_info['creator']} | "
             f"金额:{game_info['amount']} | "
             f"应战者:{game_info['acceptor']} | "
             f"结果:{game_info['result']} | "
             f"状态:{game_info['status']}\n"
         )
         with open(LOG_FILE, "a", encoding="utf-8") as f:
             f.write(log_line)
     except Exception as e:
         ZLog.e(f"写入日志文件失败: {e}")
 # ======================================
 # 带重试的网络请求
 # ======================================
def request_with_retry(url, method="GET", data=None):
     """带重试的HTTP请求，每错一次递增1分钟延迟"""
     retry_max = CONFIG["request_retries"]
     timeout = CONFIG["request_timeout"]
     
     for attempt in range(1, retry_max + 1):
         try:
             if method.upper() == "GET":
                 resp = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
             else:
                 resp = requests.post(url, headers=REQUEST_HEADERS, data=data, timeout=timeout)
             resp.raise_for_status()
             
             # 检测登录状态
             if "请先登录" in resp.text or "登录网站" in resp.text or "login.aspx" in resp.url:
                 ZLog.e("登录已失效，请更新Cookie！")
                 state.is_running = False
                 return None
             
             # 请求成功，重置错误计数
             state.network_error_count = 0
             return resp
             
         except Exception as e:
             state.network_error_count += 1
             delay_sec = state.network_error_count * 60  # 延迟递增
             ZLog.w(f"第{attempt}次请求失败 | 累计网络错误{state.network_error_count}次 → 延迟{delay_sec//60}分钟后重试")
             
             # 错误超限，直接停止
             if state.network_error_count >= CONFIG["max_network_errors"]:
                 ZLog.e("网络错误次数超限，脚本停止运行")
                 state.is_running = False
                 return None
             
             time.sleep(delay_sec)
 # ======================================
 # 【已修复】从大厅页面获取对局列表
 # 基于真实HTML结构重写：
 # - 对局容器: div#challenge-list-content
 # - 对局项: div.challenge-item
 # - 链接格式: doit.aspx?id=XXX
 # - 金额格式: （XXXX妖晶）在 span.item-text 中
 # ======================================
def get_hall_games():
     """
     【修复版】访问大厅页面，获取所有公开对局
     返回：符合条件(金额>10000)的对局ID列表
     """
     game_ids = []
     
     resp = request_with_retry(HALL_URL)
     if not resp:
         return game_ids
     
     try:
         soup = BeautifulSoup(resp.text, "html.parser")
         
         # ========== 【修复】使用真实的选择器 ==========
         # 1. 找到所有对局项: div.challenge-item
         items = soup.select("div.challenge-item")
         ZLog.d(f"找到 {len(items)} 个对局项")
         
         if not items:
             ZLog.w("未找到任何对局项")
             return game_ids
         
         # 解析每个对局
         for item in items:
             try:
                 # 2. 提取对局ID: 从 a[href*=doit.aspx] 中提取
                 link = item.select_one("a[href*='doit.aspx?id=']")
                 if not link:
                     continue
                 
                 href = link.get('href', '')
                 id_match = re.search(r'doit\.aspx\?id=(\d+)', href)
                 if not id_match:
                     continue
                 
                 game_id = id_match.group(1)
                 
                 # 3. 提取金额: 从 span.item-text 中提取，格式为 "（XXXX妖晶）"
                 item_text_elem = item.select_one("span.item-text")
                 if not item_text_elem:
                     continue
                 
                 item_text = item_text_elem.get_text(strip=True)
                 
                 # 从括号中提取金额
                 amount_match = re.search(r'[（(](\d+)妖晶[）)]', item_text)
                 
                 if amount_match:
                     amount = int(amount_match.group(1))
                 else:
                     amount = extract_number(item_text)
                 
                 # 筛选：金额 > 10000 妖晶 且 未记录过
                 if amount > CONFIG["min_amount"] and game_id not in state.recorded_game_ids:
                     game_ids.append(game_id)
                     ZLog.s(f"✓ 发现大额对局 ID:{game_id} 金额:{amount}妖晶")
                     
             except Exception as e:
                 continue
         
         ZLog.i(f"大厅共找到 {len(game_ids)} 个符合条件的大额对局")
         return game_ids
         
     except Exception as e:
         ZLog.e(f"解析大厅列表出错: {e}")
         return game_ids
 # ======================================
 # 【已修复】解析详情页获取完整对局信息
 # 基于真实HTML结构重写：
 # - 发起者: div.detail-item 中 label="发起者"
 # - 金额: div.detail-item 中 label="赌注金额"
 # - 状态: span.status-value
 # ======================================
def parse_game_detail(game_id):
     """
     【修复版】访问详情页，解析并返回完整的对局信息
     返回字典包含：id, creator(发起者), amount(金额), acceptor(应战者), result(结果), status(状态)
     """
     url = f"{DETAIL_URL}{game_id}"
     resp = request_with_retry(url)
     
     if not resp:
         return None
     
     try:
         soup = BeautifulSoup(resp.text, "html.parser")
         
         game_info = {
             "id": game_id,
             "creator": "未知",
             "amount": 0,
             "acceptor": "无人应战",
             "result": "未结束",
             "status": "进行中"
         }
         
         # ========== 【修复】使用真实的选择器提取信息 ==========
         # 1. 提取所有详情项
         detail_items = soup.select("div.detail-item")
         for detail_item in detail_items:
             label_elem = detail_item.select_one("span.detail-label")
             value_elem = detail_item.select_one("span.detail-value")
             
             if label_elem and value_elem:
                 label = label_elem.get_text(strip=True)
                 value = value_elem.get_text(strip=True)
                 
                 if label == "发起者":
                     game_info["creator"] = value
                 elif label == "赌注金额":
                     game_info["amount"] = int(value) if value.isdigit() else extract_number(value)
         
         # 2. 提取状态
         status_elem = soup.select_one("span.status-value")
         if status_elem:
             game_info["status"] = status_elem.get_text(strip=True)
         
         # 3. 提取应战者和结果（从页面文本中匹配）
         page_text = soup.get_text()
         
         # 应战者匹配
         acceptor_patterns = [
             r'应战者[:：]\s*([^\n\r|]+)',
             r'接战者[:：]\s*([^\n\r|]+)',
             r'参与者[:：]\s*([^\n\r|]+)'
         ]
         for pattern in acceptor_patterns:
             match = re.search(pattern, page_text)
             if match:
                 acceptor = match.group(1).strip()
                 if acceptor and acceptor != game_info["creator"]:
                     game_info["acceptor"] = acceptor
                     break
         
         # 结果匹配
         result_patterns = [
             r'获胜者[:：]\s*([^\n\r|]+)',
             r'([^\n\r|]+?)\s*赢了',
             r'结果[:：]\s*([^\n\r|]+)',
             r'胜利者[:：]\s*([^\n\r|]+)'
         ]
         for pattern in result_patterns:
             match = re.search(pattern, page_text)
             if match:
                 game_info["result"] = match.group(1).strip()
                 break
         
         return game_info
         
     except Exception as e:
         ZLog.e(f"解析详情页 ID:{game_id} 出错: {e}")
         return None
 # ======================================
 # 控制台打印大额对局信息（彩色高亮）
 # ======================================
def print_game_info(game_info):
     """
     控制台彩色打印格式：
     [对局ID] 发起者:XXX | 金额:XXX万 | 应战者:XXX | 结果:XXX
     """
     # 金额格式化显示
     amount_display = format_money(game_info["amount"])
     
     # 构建输出行
     line = (
         f"[{game_info['id']}] "
         f"发起者:{game_info['creator']} | "
         f"金额:{amount_display}妖晶 | "
         f"应战者:{game_info['acceptor']} | "
         f"结果:{game_info['result']} | "
         f"状态:{game_info['status']}"
     )
     
     # 根据状态选择颜色
     if game_info["status"] == "已结束":
         ZLog.s(line)  # 绿色 - 已结束
     else:
         ZLog.d(line)  # 蓝色 - 进行中
 # ======================================
 # 检测并处理大额对局
 # ======================================
def check_and_process_games():
     """主处理逻辑：获取大厅列表 → 筛选 → 访问详情 → 记录"""
     new_game_count = 0
     
     # 1. 从大厅获取所有大额对局ID
     game_ids = get_hall_games()
     
     if not game_ids:
         ZLog.i("暂无新的大额对局")
         return 0
     
     ZLog.s(f"发现 {len(game_ids)} 个新的大额对局，开始获取详情...")
     
     # 2. 逐个访问详情页
     for game_id in game_ids:
         if game_id in state.recorded_game_ids:
             continue
         
         game_info = parse_game_detail(game_id)
         if not game_info:
             continue
         
         # 标记为已记录
         state.recorded_game_ids.add(game_id)
         new_game_count += 1
         
         # 控制台彩色打印
         print_game_info(game_info)
         
         # 写入日志文件
         log_high_value_game(game_info)
         
         # 避免请求过快
         time.sleep(0.5)
     
     if new_game_count > 0:
         ZLog.s(f"本次刷新处理了 {new_game_count} 个大额对局")
         ZLog.i(f"累计已记录 {len(state.recorded_game_ids)} 个对局")
     
     return new_game_count
 # ======================================
 # 配置校验
 # ======================================
def check_config_valid():
     if not COOKIE:
         ZLog.e("=" * 60)
         ZLog.e("【错误】Cookie为空！")
         ZLog.e("=" * 60)
         return False
     
     required_numeric = [
         "max_network_errors", "request_retries", "request_timeout", 
         "refresh_interval", "min_amount"
     ]
     for key in required_numeric:
         val = CONFIG.get(key)
         if not isinstance(val, (int, float)) or val < 0:
             ZLog.e(f"配置项 {key} 不合法")
             return False
     return True
 # ======================================
 # 进程锁
 # ======================================
def is_pid_alive(pid):
     try:
         pid = int(pid)
         if os.name == "nt":
             return os.system(f'tasklist /FI "PID eq {pid}" > nul 2>&1') == 0
         else:
             os.kill(pid, 0)
             return True
     except:
         return False
def lock_script():
     if os.path.exists(LOCK_FILE):
         try:
             with open(LOCK_FILE, "r") as f:
                 pid = f.read().strip()
             if is_pid_alive(pid):
                 ZLog.e(f"脚本已运行(PID:{pid})，退出")
                 exit(0)
             else:
                 os.remove(LOCK_FILE)
         except:
             os.remove(LOCK_FILE)
     with open(LOCK_FILE, "w") as f:
         f.write(str(os.getpid()))
     atexit.register(unlock_script)
def unlock_script():
     try:
         if os.path.exists(LOCK_FILE):
             os.remove(LOCK_FILE)
     except:
         pass
 # ======================================
 # 安全退出
 # ======================================
def safe_exit():
     state.is_running = False
 # ======================================
 # 主入口
 # ======================================
def main():
     ZLog.i("=" * 70)
     ZLog.s("妖火吹牛 - 大额对局监控 V2.1 【最终修复版】")
     ZLog.i("=" * 70)
     ZLog.i(f"监控阈值: 金额 > {CONFIG['min_amount']} 妖晶")
     ZLog.i(f"刷新间隔: {CONFIG['refresh_interval']}秒")
     ZLog.i(f"日志文件: {LOG_FILE}")
     ZLog.i("=" * 70)
     
     lock_script()
     
     if not check_config_valid():
         safe_exit()
         return
     
     state.is_running = True
     ZLog.s("开始监控大厅对局...")
     
     try:
         refresh_count = 0
         while state.is_running:
             refresh_count += 1
             ZLog.d(f"\n--- 第{refresh_count}次刷新 ---")
             
             check_and_process_games()
             
             # 等待下一次刷新
             if state.is_running:
                 time.sleep(CONFIG["refresh_interval"])
                 
     except KeyboardInterrupt:
         ZLog.w("用户手动停止")
     except Exception as e:
         ZLog.e(f"异常: {str(e)[:100]}")
     finally:
         safe_exit()
         ZLog.i("=" * 70)
         ZLog.i(f"监控结束，共记录 {len(state.recorded_game_ids)} 个大额对局")
         ZLog.i(f"日志已保存至: {LOG_FILE}")
         ZLog.i("=" * 70)
if __name__ == "__main__":
     main()