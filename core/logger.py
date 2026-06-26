"""日志系统模块"""
import time
import os
import re
import sys
from datetime import datetime

# 设置标准输出使用UTF-8编码，避免Windows下的编码错误
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')


# 颜色代码
class Colors:
    """控制台颜色"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'
    WHITE = '\033[97m'
    
    # 特定类型颜色
    USER = '\033[92m'      # 用户消息 - 绿色
    BOT = '\033[94m'       # 机器人 - 蓝色
    SYSTEM = '\033[93m'    # 系统 - 黄色
    ERROR = '\033[91m'     # 错误 - 红色
    BAN = '\033[95m'       # 禁言 - 紫色
    MEMORY = '\033[90m'    # 记忆 - 灰色
    DEBUG = '\033[90m'     # 调试 - 灰色


class Logger:
    """统一的日志记录器"""
    
    def __init__(self, enable_memory=True, log_file="log.txt", max_file_size=1024*1024):
        self.enable_memory = enable_memory
        self.log_file = log_file
        self.max_file_size = max_file_size
        
        # 控制台显示开关
        self.show_debug = True
        self.show_memory_logs = True
        self.show_heartbeat = False

        # 过滤模式
        self.file_filter_patterns = [
            r'"post_type":"meta_event"',
            r'"meta_event_type":"heartbeat"',
            r'"meta_event_type":"lifecycle"',
            r'"status":{"online":true,"good":true}',
            r'"interval":\d+'
        ]
        
        self.console_filter_patterns = [
            r'"post_type":"meta_event"',
            r'"meta_event_type":"heartbeat"',
            r'"meta_event_type":"lifecycle"',
            r'非群消息类型: None',
            r'收到原始消息:.*heartbeat',
            r'DEBUG.*WebSocket',
            r'\[记忆\]'
        ]
        
        # 确保日志文件存在
        self._ensure_log_file()
        
        # 记录启动信息
        self._write_to_file(f"[{self._get_time()}][系统]日志系统初始化完成")
    
    def _get_time(self):
        """获取当前时间字符串（用于控制台和文件）"""
        return time.strftime("%Y-%m-%d %H:%M:%S")
    
    def _get_time_for_memory(self):
        """获取完整的时间格式用于记忆系统"""
        return time.strftime("%Y-%m-%d %H:%M:%S")
    
    def _ensure_log_file(self):
        """确保日志文件存在"""
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", encoding="utf-8") as f:
                f.write(f"=== 日志系统启动于 {self._get_time()} ===\n")
    
    def _check_file_size(self):
        """检查文件大小，如果超过限制则进行轮转"""
        if os.path.exists(self.log_file):
            size = os.path.getsize(self.log_file)
            if size > self.max_file_size:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = f"log_{timestamp}.txt"
                os.rename(self.log_file, backup_file)
                
                with open(self.log_file, "w", encoding="utf-8") as f:
                    f.write(f"=== 日志文件轮转，前一个文件已保存为 {backup_file} ===\n")
    
    def _should_filter_file(self, message):
        """检查是否应该过滤这条消息（不写入文件）"""
        if isinstance(message, str):
            for pattern in self.file_filter_patterns:
                if re.search(pattern, message):
                    return True
        return False
    
    def _should_filter_console(self, message):
        """检查是否应该过滤这条消息（不显示在控制台）"""
        if isinstance(message, str):
            if 'DEBUG' in message and not self.show_debug:
                return True
            if '[记忆]' in message and not self.show_memory_logs:
                return True
            if not self.show_heartbeat:
                for pattern in self.console_filter_patterns:
                    if re.search(pattern, message):
                        return True
        return False
    
    def _print_colored(self, tag, message, color=Colors.WHITE, bold=False):
        """打印彩色日志到控制台"""
        time_str = self._get_time()
        tag_part = f"[{tag}]"
        
        if bold:
            tag_part = f"{Colors.BOLD}{tag_part}{Colors.RESET}"
        
        colored_line = f"{Colors.GRAY}[{time_str}]{Colors.RESET}{color}{tag_part}{message}{Colors.RESET}"
        
        full_message = f"[{time_str}][{tag}]{message}"
        if not self._should_filter_console(full_message):
            print(colored_line)
    
    def _write_to_file(self, log_msg):
        """写入日志到文件"""
        try:
            if self._should_filter_file(log_msg):
                return
            
            self._check_file_size()
            
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_msg + "\n")
        except Exception as e:
            print(f"{Colors.RED}[{self._get_time()}][ERROR]写入日志文件失败: {e}{Colors.RESET}")
    
    def add_to_memory(self, content):
        """手动添加内容到记忆系统"""
        if self.enable_memory:
            try:
                from modules.memory.vector_memory import VectorMemory
                memory = VectorMemory()
                memory.add_memory(content)
            except Exception as e:
                print(f"{Colors.RED}[{self._get_time()}][ERROR]写入记忆失败: {e}{Colors.RESET}")
    
    def user_message(self, user_name, message, add_to_memory=True):
        """记录用户消息 - 绿色（默认加入记忆，带完整时间）"""
        time_str = self._get_time()
        memory_time = self._get_time_for_memory()
        
        log_msg = f"[{time_str}][用户]{user_name}:{message}"
        
        # 控制台显示
        self._print_colored("用户", f"{user_name}:{message}", Colors.USER)
        
        # 写入文件
        self._write_to_file(log_msg)
        
        # 加入记忆
        if add_to_memory and self.enable_memory:
            memory_content = f"{user_name}说:{message}"
            self.add_to_memory(memory_content)
    
    def bot_response(self, response, add_to_memory=True):
        """记录机器人回复 - 蓝色（默认加入记忆，带完整时间）"""
        time_str = self._get_time()
        memory_time = self._get_time_for_memory()
        
        log_msg = f"[{time_str}][机器人]{response}"
        
        # 控制台显示
        self._print_colored("机器人", response, Colors.BOT)
        
        # 写入文件
        self._write_to_file(log_msg)
        
        # 加入记忆
        if add_to_memory and self.enable_memory:
            memory_content = f"你:{response}"
            self.add_to_memory(memory_content)
    
    def ban_action(self, user_name, user_id, reason, seconds, add_to_memory=True):
        """记录禁言操作 - 紫色（默认加入记忆，带完整时间）"""
        time_str = self._get_time()
        memory_time = self._get_time_for_memory()
        minutes = seconds / 60
        
        log_msg = f"[{time_str}][禁言]用户:{user_name}({user_id}) 因 '{reason}' 被禁言 {seconds}秒 ({minutes:.1f}分钟)"
        display_msg = f"用户:{user_name}({user_id}) 因 '{reason}' 被禁言 {seconds}秒"
        
        # 控制台显示
        self._print_colored("禁言", display_msg, Colors.BAN, bold=True)
        
        # 写入文件
        self._write_to_file(log_msg)
        
        # 加入记忆 - 带完整时间
        if add_to_memory and self.enable_memory:
            memory_content = f"[{memory_time}] [禁言] {user_name} 因 '{reason}' 被禁言 {seconds}秒"
            self.add_to_memory(memory_content)
    
    def ban_expired(self, user_name, user_id, add_to_memory=True):
        """记录禁言结束（可选加入记忆，带完整时间）"""
        time_str = self._get_time()
        memory_time = self._get_time_for_memory()
        
        log_msg = f"[{time_str}][禁言]用户:{user_name}({user_id}) 禁言已结束"
        
        self._print_colored("禁言", f"{user_name} 禁言已结束", Colors.BAN)
        self._write_to_file(log_msg)
        
        if add_to_memory and self.enable_memory:
            self.add_to_memory(f"[{memory_time}] [禁言结束] {user_name}")
    
    def conversation(self, user_name, user_message, bot_response, add_to_memory=True):
        """同时记录一段完整的对话（用户+AI）"""
        self.user_message(user_name, user_message, add_to_memory)
        self.bot_response(bot_response, add_to_memory)
    
    def info(self, tag, message, add_to_memory=False):
        """记录普通信息日志（默认不加入记忆）"""
        log_msg = f"[{self._get_time()}][{tag}]{message}"
        self._print_colored(tag, message, Colors.SYSTEM)
        self._write_to_file(log_msg)
        
        if add_to_memory and self.enable_memory:
            memory_time = self._get_time_for_memory()
            self.add_to_memory(f"[{memory_time}] [{tag}]{message}")

    def warning(self, tag, message, add_to_memory=False):
        """记录警告日志（默认不加入记忆）"""
        log_msg = f"[{self._get_time()}][WARNING][{tag}]{message}"
        self._print_colored(f"WARNING.{tag}", message, Colors.YELLOW)
        self._write_to_file(log_msg)
    
        if add_to_memory and self.enable_memory:
            memory_time = self._get_time_for_memory()
            self.add_to_memory(f"[{memory_time}] [WARNING]{message}")
        
    def debug(self, tag, message, add_to_memory=False):
        """记录调试日志（默认不显示、不记忆）"""
        if self.show_debug:
            log_msg = f"[{self._get_time()}][DEBUG][{tag}]{message}"
            self._print_colored(f"DEBUG.{tag}", message, Colors.DEBUG)
            self._write_to_file(log_msg)
    
    def error(self, tag, message, exception=None, add_to_memory=False):
        """记录错误日志（默认不加入记忆）"""
        if exception:
            log_msg = f"[{self._get_time()}][ERROR][{tag}]{message} - {str(exception)}"
            display_msg = f"{message} - {str(exception)}"
        else:
            log_msg = f"[{self._get_time()}][ERROR][{tag}]{message}"
            display_msg = message
        
        self._print_colored(f"ERROR.{tag}", display_msg, Colors.ERROR, bold=True)
        
        try:
            self._check_file_size()
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_msg + "\n")
        except Exception as e:
            print(f"{Colors.RED}[{self._get_time()}][ERROR]写入错误日志失败: {e}{Colors.RESET}")
        
        if add_to_memory and self.enable_memory:
            memory_time = self._get_time_for_memory()
            self.add_to_memory(f"[{memory_time}] [ERROR]{message}")
    
    def separator(self, char="-", length=30, add_to_memory=False):
        """记录分隔符 - 只在控制台显示，不写入文件和记忆"""
        separator = char * length
        self._print_colored("分隔", separator, Colors.GRAY)
    
    def memory_log(self, message, add_to_memory=False):
        """记录记忆系统日志（默认不加入记忆）"""
        log_msg = f"[{self._get_time()}][记忆]{message}"
        
        if self.show_memory_logs:
            self._print_colored("记忆", message, Colors.MEMORY)
        
        self._write_to_file(log_msg)
    
    def system_status(self, status_message, add_to_memory=False):
        """记录系统状态（默认不加入记忆）"""
        log_msg = f"[{self._get_time()}][状态]{status_message}"
        
        self._print_colored("状态", status_message, Colors.SYSTEM, bold=True)
        self._write_to_file(log_msg)
        
        if add_to_memory and self.enable_memory:
            memory_time = self._get_time_for_memory()
            self.add_to_memory(f"[{memory_time}] [状态]{status_message}")
    
    def set_console_filter(self, show_debug=False, show_memory_logs=False, show_heartbeat=False):
        """设置控制台显示过滤"""
        self.show_debug = show_debug
        self.show_memory_logs = show_memory_logs
        self.show_heartbeat = show_heartbeat


# 创建全局日志实例
logger = Logger(log_file="log.txt", max_file_size=5*1024*1024)

# 设置控制台显示
logger.set_console_filter(
    show_debug=False,
    show_memory_logs=False,
    show_heartbeat=False
)
