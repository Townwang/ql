# -*- coding: utf-8 -*-
# ======================================
# 妖火吹牛 - 大额对局多线程监控脚本
# ======================================
import requests
import time
import os
import re
import threading
import signal
import sys
from bs4 import BeautifulSoup

# ======================================
# 配置区
# ======================================
USER_COOKIE = "ASP.NET_SessionId=mxh2axtckib1nss2x2wxx4lf; GUID=07a5a50209183821; __itrace_wid=3500e4e0-a4b5-47b4-97ef-6f1f9fbab3b9; ui_preference=1; hideUseless=0; medalDisplayCount=10; theme_preference=0; font_preference=0; sidyaohuo=0C9F5256EE1FBF0_710_04770_25110_51001-2; _d_id=367131bff1dade92ab09cd746cbe38"

CONFIG = {
    "max_network_errors": 10,
    "request_retries": 3,
    "request_timeout": 15,
    "scan_interval": 1,          # 大厅扫描间隔：1秒
    "query_interval": 3,         # 每个对局查询间隔：3秒
    "min_amount": 10000,         # 最小监控金额：1万妖晶
}

# ======================================
# 路径常量
# ======================================
SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_PATH, "game_results.log")

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
        self.recorded_game_ids = set()
        self.active_threads = {}
        self.thread_lock = threading.Lock()

state = GameState()

# ======================================
# 请求头
# ======================================
REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Cache-Control': 'max-age=0',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Cookie': USER_COOKIE,
    'Origin': BASE_HOST,
    'Referer': HALL_URL,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'
}

# ======================================
# 工具函数
# ======================================
def format_money(num):
    try:
        n = int(num)
        if n >= 10000:
            return f"{n / 10000:.1f}万"
        else:
            return f"{n}"
    except:
        return str(num)

def extract_number(text):
    match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+)', str(text))
    if match:
        return int(match.group(1).replace(',', ''))
    return 0

# ======================================
# 日志系统（全部黑色，只有结束是绿色）
# ======================================
class ZLog:
    @staticmethod
    def log(msg):
        timestamp = time.strftime('%H:%M:%S')
        print(f"[{timestamp}] {msg}")

    @staticmethod
    def success_green(msg):
        timestamp = time.strftime('%H:%M:%S')
        green = "\033[38;2;46;204;113m"
        reset = "\033[0m"
        print(f"[{timestamp}] {green}{msg}{reset}")

# ======================================
# 日志文件
# ======================================
def log_result(game_info):
    try:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        log_line = (
            f"[{timestamp}] "
            f"[{game_info['id']}] "
            f"发起者:{game_info['creator']} | "
            f"金额:{game_info['amount']} | "
            f"应战者:{game_info['acceptor']} | "
            f"获胜者:{game_info['winner']} | "
            f"正确答案:{game_info['correct_answer']}\n"
        )
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        pass

# ======================================
# 网络请求
# ======================================
def request_with_retry(url, method="GET", data=None):
    retry_max = CONFIG["request_retries"]
    timeout = CONFIG["request_timeout"]
    
    for attempt in range(1, retry_max + 1):
        try:
            if method.upper() == "GET":
                resp = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
            else:
                resp = requests.post(url, headers=REQUEST_HEADERS, data=data, timeout=timeout)
            resp.raise_for_status()
            
            if "请先登录" in resp.text or "登录网站" in resp.text:
                ZLog.log("登录已失效，请更新Cookie！")
                return None
            
            state.network_error_count = 0
            return resp
            
        except Exception as e:
            state.network_error_count += 1
            delay_sec = min(state.network_error_count * 10, 60)
            if attempt < retry_max:
                time.sleep(delay_sec)
            continue
    return None

# ======================================
# 从大厅获取对局列表
# ======================================
def get_hall_games():
    game_list = []
    
    resp = request_with_retry(HALL_URL)
    if not resp:
        return game_list
    
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # 查找所有对局项
        items = soup.select("div.challenge-item")
        
        for item in items:
            try:
                # 提取对局ID
                link = item.find("a", href=re.compile(r'doit\.aspx\?id=(\d+)'))
                if not link:
                    continue
                
                id_match = re.search(r'id=(\d+)', link['href'])
                if not id_match:
                    continue
                
                game_id = id_match.group(1)
                
                # 提取金额
                text_span = item.find("span", class_="item-text")
                if not text_span:
                    continue
                
                item_text = text_span.get_text()
                amount = extract_number(item_text)
                
                # 筛选大额对局
                if amount >= CONFIG["min_amount"]:
                    game_list.append({
                        "id": game_id,
                        "amount": amount
                    })
                    
            except Exception as e:
                continue
        
        return game_list
        
    except Exception as e:
        return game_list

# ======================================
# 解析详情页
# ======================================
def parse_game_detail(game_id):
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
            "winner": "未结束",
            "correct_answer": "未知",
            "status": "进行中"
        }
        
        # 1. 解析 detail-item 区域
        detail_items = soup.select("div.detail-item")
        for item in detail_items:
            label_span = item.find("span", class_="detail-label")
            value_span = item.find("span", class_="detail-value")
            if not label_span or not value_span:
                continue
            
            label_text = label_span.get_text().strip()
            value_text = value_span.get_text().strip()
            
            if "发起者" in label_text:
                game_info["creator"] = value_text
            elif "赌注金额" in label_text:
                game_info["amount"] = extract_number(value_text)
            elif "结束时间" in label_text and value_text:
                game_info["status"] = "已结束"
        
        # 2. 解析 status-line 区域
        status_lines = soup.select("div.status-line")
        for line in status_lines:
            label_span = line.find("span", class_="status-label")
            value_span = line.find("span", class_="status-value")
            if not label_span or not value_span:
                continue
            
            label_text = label_span.get_text().strip()
            value_text = value_span.get_text().strip()
            
            if "应战者" in label_text and value_text and value_text != "-":
                game_info["acceptor"] = value_text
            elif "结果" in label_text and value_text and value_text != "-":
                game_info["winner"] = value_text
                game_info["status"] = "已结束"
        
        # 3. 解析正确答案（选项1/选项2）
        # 查找获胜的选项（通常有特殊标记或颜色）
        answer_divs = soup.select("div.answer-item, div.option-item, .answer")
        for i, div in enumerate(answer_divs, 1):
            div_text = div.get_text().strip()
            # 检查是否有获胜标记（如绿色、对勾、win等）
            div_class = div.get("class", [])
            div_str = str(div).lower()
            
            if any(x in div_class for x in ["win", "correct", "winner"]) or \
               "win" in div_str or "正确" in div_str or "获胜" in div_str:
                game_info["correct_answer"] = f"选项{i}"
                break
        
        # 4. 兜底方案：从文本中查找
        if game_info["correct_answer"] == "未知":
            page_text = soup.get_text().lower()
            if "选项1" in page_text and ("赢" in page_text or "胜" in page_text or "正确" in page_text):
                # 更精确的匹配
                pass
        
        return game_info
        
    except Exception as e:
        return None

# ======================================
# 单个对局监控线程
# ======================================
def monitor_game_thread(game_id, init_amount):
    """单个对局的监控线程，每3秒查询一次直到结束"""
    ZLog.log(f"[发现新对局] ID:{game_id} | 金额:{format_money(init_amount)}")
    
    while state.is_running:
        try:
            game_info = parse_game_detail(game_id)
            
            if game_info and game_info["status"] == "已结束":
                # 对局结束，绿色高亮输出结果
                line = (
                    f"[对局结束] ID:{game_id} | "
                    f"发起者:{game_info['creator']} | "
                    f"金额:{format_money(game_info['amount'])} | "
                    f"应战者:{game_info['acceptor']} | "
                    f"获胜者:{game_info['winner']} | "
                    f"正确答案:{game_info['correct_answer']}"
                )
                ZLog.success_green(line)
                log_result(game_info)
                break
            
            # 继续等待
            time.sleep(CONFIG["query_interval"])
            
        except Exception as e:
            time.sleep(CONFIG["query_interval"])
            continue
    
    # 线程结束，从活跃线程中移除
    with state.thread_lock:
        if game_id in state.active_threads:
            del state.active_threads[game_id]

# ======================================
# 主线程：扫描大厅
# ======================================
def scan_hall_loop():
    ZLog.log("=" * 60)
    ZLog.log("妖火吹牛 - 大额对局多线程监控")
    ZLog.log("=" * 60)
    ZLog.log(f"监控阈值: >= {CONFIG['min_amount']} 妖晶")
    ZLog.log(f"大厅扫描: {CONFIG['scan_interval']}秒/次")
    ZLog.log(f"对局查询: {CONFIG['query_interval']}秒/次")
    ZLog.log(f"日志文件: {LOG_FILE}")
    ZLog.log("=" * 60)
    
    while state.is_running:
        try:
            # 扫描大厅
            games = get_hall_games()
            
            for game in games:
                game_id = game["id"]
                
                # 检查是否已记录或已有线程在监控
                with state.thread_lock:
                    if game_id in state.recorded_game_ids:
                        continue
                    if game_id in state.active_threads:
                        continue
                    
                    # 标记为已记录
                    state.recorded_game_ids.add(game_id)
                    
                    # 创建新线程
                    thread = threading.Thread(
                        target=monitor_game_thread,
                        args=(game_id, game["amount"]),
                        daemon=True
                    )
                    state.active_threads[game_id] = thread
                    thread.start()
            
            # 等待下一次扫描
            time.sleep(CONFIG["scan_interval"])
            
        except Exception as e:
            time.sleep(CONFIG["scan_interval"])

# ======================================
# 信号处理
# ======================================
def signal_handler(signum, frame):
    ZLog.log("收到停止信号，正在退出...")
    state.is_running = False

# ======================================
# 主入口
# ======================================
def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        scan_hall_loop()
    except KeyboardInterrupt:
        pass
    finally:
        state.is_running = False
        ZLog.log("=" * 60)
        ZLog.log(f"监控结束，共记录 {len(state.recorded_game_ids)} 个对局")
        ZLog.log(f"日志已保存至: {LOG_FILE}")
        ZLog.log("=" * 60)

if __name__ == "__main__":
    main()
