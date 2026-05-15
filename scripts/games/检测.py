# -*- coding: utf-8 -*-
# ======================================
# 妖火吹牛 - 大额对局多线程监控脚本
# 已修复：正确答案显示 + 金额解析
# ======================================
import requests
import time
import os
import re
import threading
import signal
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

# ========== 修复：金额解析 ==========
def extract_number(text):
    """
    修复后的金额解析函数
    支持：10000 → 10000, 50000 → 50000, 100,000 → 100000, 1,234,567 → 1234567
    """
    if not text:
        return 0
    match = re.search(r'([\d,]+)', str(text))
    if match:
        num_str = match.group(1).replace(',', '')
        return int(num_str)
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
        items = soup.select("div.challenge-item")
        
        for item in items:
            try:
                link = item.find("a", href=re.compile(r'doit\.aspx\?id=(\d+)'))
                if not link:
                    continue
                
                id_match = re.search(r'id=(\d+)', link['href'])
                if not id_match:
                    continue
                
                game_id = id_match.group(1)
                
                text_span = item.find("span", class_="item-text")
                if not text_span:
                    continue
                
                item_text = text_span.get_text()
                amount = extract_number(item_text)
                
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
# 解析详情页（已修复正确答案+金额）
# ======================================
def parse_game_detail(game_id):
    url = f"{DETAIL_URL}{game_id}"
    resp = request_with_retry(url)
    
    if not resp:
        return None
    
    try:
        html = resp.text
        
        game_info = {
            "id": game_id,
            "creator": "未知",
            "amount": 0,
            "acceptor": "无人应战",
            "winner": "未结束",
            "correct_answer": "未知",
            "status": "进行中"
        }
        
        # 1. 解析发起者
        initiator_match = re.search(r'<span class="detail-label">发起者</span>.*?<span class="detail-value"><a[^>]*>([^<]+)</a></span>', html, re.DOTALL)
        if initiator_match:
            game_info["creator"] = initiator_match.group(1)
        
        # 2. 解析金额（已修复）
        amount_match = re.search(r'<span class="detail-label">赌注金额</span>.*?<span class="detail-value">([^<]+)</span>', html, re.DOTALL)
        if amount_match:
            game_info["amount"] = extract_number(amount_match.group(1))
        
        # 3. 解析应战者
        challenger_match = re.search(r'<span class="status-label">应战者</span>.*?<span class="status-value">([^<]+)</span>', html, re.DOTALL)
        if challenger_match:
            challenger_text = challenger_match.group(1).strip()
            if challenger_text and challenger_text != "-":
                if "|" in challenger_text:
                    game_info["acceptor"] = challenger_text.split("|")[0].strip()
                else:
                    game_info["acceptor"] = challenger_text
        
        # 4. 解析结果/获胜者
        result_match = re.search(r'<span class="status-label">结果</span>.*?<span class="status-value[^>]*>([^<]+)</span>', html, re.DOTALL)
        if result_match:
            result_text = result_match.group(1).strip()
            if result_text and result_text != "-":
                game_info["winner"] = result_text
                game_info["status"] = "已结束"
        
        # ========== 修复：正确答案解析 ==========
        correct_match = re.search(r'<span class="status-label">正确答案</span>.*?<span class="status-value">([^<]+)</span>', html, re.DOTALL)
        if correct_match:
            correct_raw = correct_match.group(1).strip()
            if "答案一" in correct_raw:
                game_info["correct_answer"] = "选项1"
            elif "答案二" in correct_raw:
                game_info["correct_answer"] = "选项2"
        
        # 5. 检查是否结束
        end_time_match = re.search(r'<span class="detail-label">结束时间</span>.*?<span class="detail-value">([^<]+)</span>', html, re.DOTALL)
        if end_time_match and end_time_match.group(1).strip():
            game_info["status"] = "已结束"
        
        return game_info
        
    except Exception as e:
        return None

# ======================================
# 单个对局监控线程
# ======================================
def monitor_game_thread(game_id, init_amount):
    ZLog.log(f"[发现新对局] ID:{game_id} | 金额:{format_money(init_amount)}")
    
    while state.is_running:
        try:
            game_info = parse_game_detail(game_id)
            
            if game_info and game_info["status"] == "已结束":
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
            
            time.sleep(CONFIG["query_interval"])
            
        except Exception as e:
            time.sleep(CONFIG["query_interval"])
            continue
    
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
            games = get_hall_games()
            
            for game in games:
                game_id = game["id"]
                
                with state.thread_lock:
                    if game_id in state.recorded_game_ids:
                        continue
                    if game_id in state.active_threads:
                        continue
                    
                    state.recorded_game_ids.add(game_id)
                    
                    thread = threading.Thread(
                        target=monitor_game_thread,
                        args=(game_id, game["amount"]),
                        daemon=True
                    )
                    state.active_threads[game_id] = thread
                    thread.start()
            
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
