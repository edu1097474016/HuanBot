"""HuanBot 主程序"""
import os
import re
import time
import json
import threading
import traceback
import websocket
import signal
import sys
from core.config import config
from core.logger import logger
from core.api_manager import get_api_manager
from handlers.message_handler import MessageHandler
from modules.llm.llm_client import call_llm, get_llm_model
from handlers.action_executor import parse_json_actions, execute_json_actions

# 配置参数
BOT_QQ = config.require("bot.qq")
ADMIN_QQ = config.require("bot.admin_qq")
GROUP_ID = config.require("bot.group_id")
ACTIVE_THRESHOLD = config.require("bot.active_threshold")
ACTIVE_CHECK_INTERVAL = config.require("bot.active_check_interval")

# 时尚小垃圾
art = """\
+-----------------------------------------+
|#   # #   #  ###  #   # ####   ###  #####|
|#   # #   # #   # ##  # #   # #   #   #  |
|#   # #   # #   # # # # #   # #   #   #  |
|#   # #   # #   # #  ## #   # #   #   #  |
|#   # #   # #   # #   # #   # #   #   #  |
| # #   # #   ###  #   # ####   ###    #  |
+-----------------------------------------+"""


class HuanBot:
    """HuanBot主类"""
    
    def __init__(self):
        """初始化机器人"""
        self.message_handler = MessageHandler()
        self.last_message_time = time.time()
        self.ws = None
        self.ws_connected = False
        self.running = True
        self.active_thread = None
        
    def start(self):
        """启动机器人"""
        print(art)
        logger.info("系统", "HuanBot 启动中...")
        
        # 初始化API管理器
        get_api_manager()
        
        # 启动WebSocket连接
        self._connect_websocket()
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # 启动主动发送线程
        self.active_thread = threading.Thread(target=self._active_send_loop, daemon=True)
        self.active_thread.start()
        
        logger.info("系统", "HuanBot 启动完成，等待消息...")
        
        # 保持主线程运行
        while self.running:
            time.sleep(1)
    
    def _connect_websocket(self):
        """建立WebSocket连接"""
        ws_url = config.get("napcat.ws_url", "ws://localhost:3001")
        token = config.get("napcat.token", "")
        if token and "?" not in ws_url:
            ws_url = f"{ws_url}?token={token}"
        
        try:
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_open=self._on_ws_open,
                on_message=self._on_ws_message,
                on_error=self._on_ws_error,
                on_close=self._on_ws_close
            )
            wst = threading.Thread(target=self.ws.run_forever, daemon=True)
            wst.start()
            
            # 等待连接建立
            timeout = 5
            while not self.ws_connected and timeout > 0:
                time.sleep(0.1)
                timeout -= 0.1
                
            if self.ws_connected:
                logger.info("消息接收", "连接成功，监听消息...")
            else:
                logger.info("消息接收", "WebSocket连接超时")
                
        except Exception as e:
            logger.error("系统", f"WebSocket初始化失败: {e}")
    
    def _on_ws_open(self, ws):
        """WebSocket连接打开"""
        self.ws_connected = True
        logger.info("系统", "WebSocket连接已建立")
    
    def _on_ws_message(self, ws, message):
        """处理WebSocket消息"""
        try:
            data = json.loads(message)
            if data.get("post_type") == "message":
                if data.get("message_type") == "group":
                    self._handle_group_message(data)
                elif data.get("message_type") == "private":
                    self._handle_private_message(data)
        except Exception as e:
            logger.error("消息处理", f"解析消息失败: {e}")
    
    def _on_ws_error(self, ws, error):
        """WebSocket错误"""
        logger.error("系统", f"WebSocket错误: {error}")
        self.ws_connected = False
    
    def _on_ws_close(self, ws, close_status_code, close_msg):
        """WebSocket连接关闭"""
        logger.info("系统", "WebSocket连接关闭")
        self.ws_connected = False
    
    def _handle_group_message(self, data):
        """处理群消息"""
        group_id = data.get("group_id")
        if group_id != GROUP_ID:
            return
        
        user_id = data.get("user_id")
        user_name = data.get("sender", {}).get("nickname", "未知用户")
        message = data.get("message", "")
        message_id = data.get("message_id")
        
        # 更新最后消息时间
        self.last_message_time = time.time()
        
        # 忽略机器人自己的消息
        if user_id == BOT_QQ:
            return
        
        # 记录用户消息
        logger.user_message(user_name, message)
        
        # 处理消息
        self.message_handler.process_message(message, user_id, user_name, message_id, message_type="group", group_id=group_id)
    
    def _handle_private_message(self, data):
        """处理私聊消息"""
        user_id = data.get("user_id")
        user_name = data.get("sender", {}).get("nickname", "未知用户")
        message = data.get("message", "")
        message_id = data.get("message_id")
        
        # 更新最后消息时间
        self.last_message_time = time.time()
        
        # 忽略机器人自己的消息
        if user_id == BOT_QQ:
            return
        
        # 记录用户消息
        logger.user_message(user_name, message)
        
        # 处理私聊消息
        self.message_handler.process_message(message, user_id, user_name, message_id, message_type="private")
    
    def _active_send_loop(self):
        """主动发送消息循环"""
        last_album_update_day = -1
        
        while self.running:
            time.sleep(ACTIVE_CHECK_INTERVAL)
            if not self.running:
                break
                
            # 检查相册更新时间
            now = time.localtime()
            current_hour = now.tm_hour
            current_minute = now.tm_min
            current_day = now.tm_mday
            
            # 获取配置的更新时间
            update_time_str = config.get("album", {}).get("update_time", "20:00")
            update_hour, update_minute = map(int, update_time_str.split(":"))
            
            # 如果到达更新时间且当天未更新过
            if (current_hour == update_hour and current_minute == update_minute and 
                current_day != last_album_update_day):
                logger.info("相册更新", "到达更新时间，开始更新相册")
                self._update_album()
                last_album_update_day = current_day
            
            # 检查活跃消息
            current_time = time.time()
            if current_time - self.last_message_time > ACTIVE_THRESHOLD:
                logger.info("主动发送", "检测到长时间无人说话，准备发送活跃消息")
                self._active_send()
    
    def _signal_handler(self, signum, frame):
        """信号处理"""
        logger.info("系统", "收到退出信号，开始清理...")
        self.running = False
        
        # 关闭WebSocket连接
        if self.ws:
            self.ws.close()
        
        # 等待线程退出
        if self.active_thread and self.active_thread.is_alive():
            self.active_thread.join(timeout=5)
        
        logger.info("系统", "HuanBot 已停止")
        sys.exit(0)
    
    def _active_send(self):
        """发送活跃消息"""
        try:
            # 获取表情包列表
            from modules.tools.emoji_manager import get_emoji_manager
            emoji_manager = get_emoji_manager()
            recent_emojis = emoji_manager.get_recent_emojis(20)
            image_hint = "、".join(recent_emojis) if recent_emojis else "无"
            
            # 生成活跃消息
            executor_model = get_llm_model("executor")
            system_content = (
                f"{self.message_handler.personality}{self.message_handler.behavior}{self.message_handler.tools}\n"
                "你是工具调用者。群里长时间没人说话，请生成一条活跃气氛的消息。"
                f"重要：当前群号是 {GROUP_ID}，所有 send_group_xxx 操作的 group_id 参数都必须使用这个值！"
            )
            user_content = (
                f"群里现在很安静，请发送一条有趣的消息活跃气氛。\n"
                f"可用图片: {image_hint}\n"
                "请生成最终回复。"
            )
            
            response = call_llm([
                {'role': 'system', 'content': system_content},
                {'role': 'user', 'content': user_content}
            ], model_name=executor_model, stream=False)
            
            full_response = response.choices[0].message.content
            logger.bot_response(full_response, add_to_memory=False)
            
            # 解析JSON动作
            json_actions, cq_mapping = parse_json_actions(full_response)
            if json_actions:
                execute_json_actions(json_actions, cq_mapping=cq_mapping)
                logger.info("主动发送", "已发送活跃消息", add_to_memory=True)
                
        except Exception as e:
            error_detail = str(e)[:200]
            logger.error("主动发送", f"发送失败: {error_detail}", e, add_to_memory=True)
            self._send_error_notification("主动发送错误", error_detail)
    
    def _send_error_notification(self, error_type: str, error_detail: str):
        """发送错误通知"""
        try:
            api_manager = get_api_manager()
            message = f"@全体人员 能否有人告诉阿白我的ai出了点问题 {error_type}: {error_detail}"
            result = api_manager.send_group_msg(GROUP_ID, message)
            if result.get("status") == "ok":
                logger.info("消息发送", f"目标群: {GROUP_ID}, 消息内容: {message}")
                logger.info("消息发送", f"API返回结果: {result}")
                logger.info("消息发送", "消息发送成功")
                logger.info("错误通知", f"已发送错误通知到群: {error_type}")
            else:
                logger.error("消息发送", f"发送失败: {result}")
        except Exception as e:
            logger.error("错误通知", f"发送错误通知失败: {e}")

    def _update_album(self):
        """更新相册并发送消息"""
        try:
            from modules.tools.photo_crawler import update_album, get_album_photos
            
            # 更新相册
            new_photos = update_album()
            
            if new_photos:
                logger.info("相册更新", f"成功更新 {len(new_photos)} 张照片")
                
                # 获取相册中的所有照片
                album_photos = get_album_photos()
                
                # 发送更新通知
                api_manager = get_api_manager()
                message = f"📸 相册更新啦！\n\n今天的风景照已更新，共 {len(album_photos)} 张照片。\n\n快来欣赏美丽的风景吧～"
                result = api_manager.send_group_msg(GROUP_ID, message)
                
                if result.get("status") == "ok":
                    logger.info("相册更新", "已发送相册更新通知")
                else:
                    logger.error("相册更新", f"发送通知失败: {result}")
            else:
                logger.warning("相册更新", "未能更新照片，使用表情包替代")
                
        except Exception as e:
            error_detail = str(e)[:200]
            logger.error("相册更新", f"更新失败: {error_detail}", e)
            self._send_error_notification("相册更新错误", error_detail)


if __name__ == "__main__":
    bot = HuanBot()
    bot.start()
