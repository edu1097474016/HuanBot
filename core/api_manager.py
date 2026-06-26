"""API管理器模块"""
import json
import time
import threading
import uuid
from typing import Dict, Any, Optional
import websocket
from core.config import config
from core.logger import logger


class APIManager:
    """API管理器类"""
    
    def __init__(self, base_url: str = "http://localhost:3000", ws_url: str = "ws://localhost:3001"):
        """
        初始化 API 管理器
        :param base_url: HTTP 备用地址（保留用于兼容）
        :param ws_url: WebSocket 地址（端口 3001）
        """
        self.base_url = base_url.rstrip('/')
        self.ws_url = ws_url
        # 如果 URL 没有 token，从 config 读取
        if "?" not in ws_url:
            token = config.get("napcat.token", "")
            if token:
                self.ws_url = f"{ws_url}?token={token}"
        self.ws = None
        self.response_queue: Dict[str, list] = {}
        self.ws_connected = False
        self._connect_websocket()
        
        # 启动后台线程保持连接
        self._keep_alive_thread = threading.Thread(target=self._keep_websocket_alive, daemon=True)
        self._keep_alive_thread.start()

    def _connect_websocket(self):
        """建立 WebSocket 连接"""
        try:
            # 获取 token
            token = config.get("napcat.token", "")
            ws_url = self.ws_url
            if token and "?" not in ws_url:
                ws_url = f"{ws_url}?token={token}"

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
                logger.info("系统", f"WebSocket 连接成功: {self.ws_url}", add_to_memory=False)
            else:
                logger.info("系统", f"WebSocket 连接超时", add_to_memory=False)
        except Exception as e:
            logger.error("系统", f"WebSocket 初始化失败: {e}", add_to_memory=False)

    def _on_ws_open(self, ws):
        self.ws_connected = True
        logger.info("系统", "WebSocket 连接已建立", add_to_memory=False)

    def _on_ws_message(self, ws, message):
        try:
            data = json.loads(message)
            echo = data.get("echo")
            if echo and echo in self.response_queue:
                self.response_queue[echo].append(data)
        except Exception as e:
            logger.error("系统", f"WebSocket 消息解析错误: {e}", add_to_memory=False)

    def _on_ws_error(self, ws, error):
        logger.error("系统", f"WebSocket 错误: {error}", add_to_memory=False)
        self.ws_connected = False

    def _on_ws_close(self, ws, close_status_code, close_msg):
        logger.info("系统", "WebSocket 连接关闭", add_to_memory=False)
        self.ws_connected = False

    def _keep_websocket_alive(self):
        """保持 WebSocket 连接"""
        while True:
            time.sleep(30)
            if not self.ws_connected:
                logger.info("系统", "WebSocket 连接断开，尝试重连...", add_to_memory=False)
                self._connect_websocket()

    def call_api(self, action: str, params: Dict[str, Any] = None, timeout: float = 5.0) -> Dict[str, Any]:
        """
        通过 WebSocket 调用 OneBot API
        :param action: API 动作名称
        :param params: 参数字典
        :param timeout: 超时时间（秒）
        :return: API 响应
        """
        if not self.ws_connected or not self.ws:
            return {"status": "failed", "error": "WebSocket not connected"}

        echo = str(uuid.uuid4())

        request = {
            "action": action,
            "params": params or {},
            "echo": echo
        }

        self.response_queue[echo] = []

        try:
            # 使用utf-8编码确保中文字符能正确发送
            self.ws.send(json.dumps(request, ensure_ascii=False))

            waited = 0.0
            while waited < timeout and not self.response_queue[echo]:
                time.sleep(0.1)
                waited += 0.1

            responses = self.response_queue.pop(echo, [])
            if responses:
                return responses[0]
            else:
                return {"status": "failed", "error": "Request timeout"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    # ==================== 消息发送相关 API ====================
    
    def send_private_msg(self, user_id: int, message: str, auto_escape: bool = False) -> Dict[str, Any]:
        """发送私聊消息"""
        return self.call_api("send_private_msg", {
            "user_id": user_id,
            "message": message,
            "auto_escape": auto_escape
        })

    def send_group_msg(self, group_id: int, message: str, auto_escape: bool = False) -> Dict[str, Any]:
        """发送群消息"""
        return self.call_api("send_group_msg", {
            "group_id": group_id,
            "message": message,
            "auto_escape": auto_escape
        })

    def send_group_image(self, group_id: int, image_path: str) -> Dict[str, Any]:
        """发送群聊图片消息"""
        if not image_path:
            return {"status": "failed", "error": "image_path 为空"}
        
        # 使用最简单的CQ码格式
        message = f"[CQ:image,file={image_path}]"
            
        logger.info("消息发送", f"准备发送图片: {message}")
        return self.send_group_msg(group_id, message)

    def send_group_at(self, group_id: int, user_id: int, text: str) -> Dict[str, Any]:
        """发送群聊@消息"""
        message = f"[CQ:at,qq={user_id}]{text}"
        return self.send_group_msg(group_id, message)

    def send_group_reply(self, group_id: int, message_id: int, text: str) -> Dict[str, Any]:
        """发送群聊回复消息"""
        message = f"[CQ:reply,id={message_id}]{text}"
        return self.send_group_msg(group_id, message)

    def send_private_text(self, user_id: int, text: str, auto_escape: bool = False) -> Dict[str, Any]:
        """发送私聊文本消息"""
        return self.send_private_msg(user_id, text, auto_escape)

    def send_private_image(self, user_id: int, image_path: str) -> Dict[str, Any]:
        """发送私聊图片消息"""
        if not image_path:
            return {"status": "failed", "error": "image_path 为空"}
        message = f"[CQ:image,file={image_path}]"
        return self.send_private_msg(user_id, message)

    def send_msg(self, message_type: str, user_id: int = None, group_id: int = None,
                 message: str = "", auto_escape: bool = False) -> Dict[str, Any]:
        """发送消息（通用）"""
        params = {
            "message_type": message_type,
            "message": message,
            "auto_escape": auto_escape
        }
        if message_type == "private":
            params["user_id"] = user_id
        elif message_type == "group":
            params["group_id"] = group_id
        return self.call_api("send_msg", params)

    def delete_msg(self, message_id: int) -> Dict[str, Any]:
        """撤回消息"""
        return self.call_api("delete_msg", {"message_id": message_id})

    def get_msg(self, message_id: int) -> Dict[str, Any]:
        """获取消息"""
        return self.call_api("get_msg", {"message_id": message_id})

    def get_forward_msg(self, forward_id: str) -> Dict[str, Any]:
        """获取合并转发消息"""
        return self.call_api("get_forward_msg", {"id": forward_id})

    def send_poke(self, user_id: int, group_id: Optional[int] = None) -> Dict[str, Any]:
        """发送戳一戳"""
        params = {"user_id": user_id}
        if group_id:
            params["group_id"] = group_id
        return self.call_api("send_poke", params)

    def recall_message(self, message_id: int) -> Dict[str, Any]:
        """撤回消息"""
        return self.delete_msg(message_id)

    # ==================== 群管理相关 API ====================
    
    def send_group_notice(self, group_id: int, content: str) -> Dict[str, Any]:
        """发送群公告"""
        # 使用NapCat官方文档中的正确参数
        return self.call_api("_send_group_notice", {
            "group_id": group_id,
            "content": content,
            "image": "",
            "pinned": 0,
            "type": 0,
            "confirm_required": 0,
            "is_show_edit_card": 0,
            "tip_window_type": 0
        })

    def get_group_notice(self, group_id: int) -> Dict[str, Any]:
        """获取群公告"""
        return self.call_api("_get_group_notice", {"group_id": group_id})

    def set_group_kick(self, group_id: int, user_id: int, reject_add_request: bool = False) -> Dict[str, Any]:
        """群组踢人"""
        return self.call_api("set_group_kick", {
            "group_id": group_id,
            "user_id": user_id,
            "reject_add_request": reject_add_request
        })

    def batch_group_kick(self, group_id: int, user_ids: list, reject_add_request: bool = False) -> Dict[str, Any]:
        """批量踢出群成员"""
        results = []
        for user_id in user_ids:
            result = self.set_group_kick(group_id, user_id, reject_add_request)
            results.append({
                "user_id": user_id,
                "result": result
            })
        return {"status": "ok", "results": results}

    def set_group_ban(self, group_id: int, user_id: int, duration: int = 1800) -> Dict[str, Any]:
        """群组单人禁言"""
        return self.call_api("set_group_ban", {
            "group_id": group_id,
            "user_id": user_id,
            "duration": duration
        })

    def set_group_anonymous_ban(self, group_id: int, anonymous: Dict = None,
                               anonymous_flag: str = None, duration: int = 1800) -> Dict[str, Any]:
        """群组匿名用户禁言"""
        params = {"group_id": group_id, "duration": duration}
        if anonymous:
            params["anonymous"] = anonymous
        if anonymous_flag:
            params["anonymous_flag"] = anonymous_flag
        return self.call_api("set_group_anonymous_ban", params)

    def set_group_whole_ban(self, group_id: int, enable: bool = True) -> Dict[str, Any]:
        """群组全员禁言"""
        return self.call_api("set_group_whole_ban", {"group_id": group_id, "enable": enable})

    def set_group_admin(self, group_id: int, user_id: int, enable: bool = True) -> Dict[str, Any]:
        """群组设置管理员"""
        return self.call_api("set_group_admin", {
            "group_id": group_id,
            "user_id": user_id,
            "enable": enable
        })

    def set_group_anonymous(self, group_id: int, enable: bool = True) -> Dict[str, Any]:
        """群组匿名"""
        return self.call_api("set_group_anonymous", {"group_id": group_id, "enable": enable})

    def set_group_card(self, group_id: int, user_id: int, card: str = "") -> Dict[str, Any]:
        """设置群名片"""
        return self.call_api("set_group_card", {
            "group_id": group_id,
            "user_id": user_id,
            "card": card
        })

    def set_group_name(self, group_id: int, group_name: str) -> Dict[str, Any]:
        """设置群名"""
        return self.call_api("set_group_name", {"group_id": group_id, "group_name": group_name})

    def set_group_leave(self, group_id: int, is_dismiss: bool = False) -> Dict[str, Any]:
        """退出群组"""
        return self.call_api("set_group_leave", {"group_id": group_id, "is_dismiss": is_dismiss})

    def set_group_special_title(self, group_id: int, user_id: int,
                               special_title: str = "", duration: int = -1) -> Dict[str, Any]:
        """设置群组专属头衔"""
        return self.call_api("set_group_special_title", {
            "group_id": group_id,
            "user_id": user_id,
            "special_title": special_title,
            "duration": duration
        })

    def get_essence_msg_list(self, group_id: int) -> Dict[str, Any]:
        """获取精华消息列表"""
        return self.call_api("get_essence_msg_list", {"group_id": group_id})

    def delete_essence_msg(self, message_id: int) -> Dict[str, Any]:
        """删除精华消息"""
        return self.call_api("delete_essence_msg", {"message_id": message_id})

    # ==================== 请求处理相关 API ====================
    
    def set_friend_add_request(self, flag: str, approve: bool = True, remark: str = "") -> Dict[str, Any]:
        """处理加好友请求"""
        return self.call_api("set_friend_add_request", {
            "flag": flag,
            "approve": approve,
            "remark": remark
        })

    def set_doubt_friends_add_request(self, flag: str, approve: bool = True) -> Dict[str, Any]:
        """处理系统标记的可疑好友申请"""
        return self.call_api("set_doubt_friends_add_request", {
            "flag": flag,
            "approve": approve
        })

    def set_group_add_request(self, flag: str, sub_type: str, approve: bool = True, reason: str = "") -> Dict[str, Any]:
        """处理加群请求/邀请"""
        return self.call_api("set_group_add_request", {
            "flag": flag,
            "sub_type": sub_type,
            "approve": approve,
            "reason": reason
        })

    # ==================== 获取信息相关 API ====================
    
    def get_login_info(self) -> Dict[str, Any]:
        """获取登录号信息"""
        return self.call_api("get_login_info")

    def get_stranger_info(self, user_id: int, no_cache: bool = False) -> Dict[str, Any]:
        """获取陌生人信息"""
        return self.call_api("get_stranger_info", {"user_id": user_id, "no_cache": no_cache})

    def get_friend_list(self) -> Dict[str, Any]:
        """获取好友列表"""
        return self.call_api("get_friend_list")

    def get_group_info(self, group_id: int, no_cache: bool = False) -> Dict[str, Any]:
        """获取群信息"""
        return self.call_api("get_group_info", {"group_id": group_id, "no_cache": no_cache})

    def get_group_list(self) -> Dict[str, Any]:
        """获取群列表"""
        return self.call_api("get_group_list")

    def get_group_member_info(self, group_id: int, user_id: int, no_cache: bool = False) -> Dict[str, Any]:
        """获取群成员信息"""
        return self.call_api("get_group_member_info", {
            "group_id": group_id,
            "user_id": user_id,
            "no_cache": no_cache
        })

    def get_group_member_list(self, group_id: int) -> Dict[str, Any]:
        """获取群成员列表"""
        return self.call_api("get_group_member_list", {"group_id": group_id})

    def get_group_honor_info(self, group_id: int, honor_type: str) -> Dict[str, Any]:
        """获取群荣誉信息"""
        return self.call_api("get_group_honor_info", {"group_id": group_id, "type": honor_type})

    # ==================== 媒体相关 API ====================
    
    def get_cookies(self, domain: str = "") -> Dict[str, Any]:
        """获取 Cookies"""
        return self.call_api("get_cookies", {"domain": domain})

    def get_csrf_token(self) -> Dict[str, Any]:
        """获取 CSRF Token"""
        return self.call_api("get_csrf_token")

    def get_credentials(self, domain: str = "") -> Dict[str, Any]:
        """获取 QQ 相关接口凭证"""
        return self.call_api("get_credentials", {"domain": domain})

    def get_record(self, file: str, out_format: str) -> Dict[str, Any]:
        """获取语音"""
        return self.call_api("get_record", {"file": file, "out_format": out_format})

    def get_image(self, file: str) -> Dict[str, Any]:
        """获取图片"""
        return self.call_api("get_image", {"file": file})

    def can_send_image(self) -> Dict[str, Any]:
        """检查是否可以发送图片"""
        return self.call_api("can_send_image")

    def can_send_record(self) -> Dict[str, Any]:
        """检查是否可以发送语音"""
        return self.call_api("can_send_record")

    def ocr_image(self, image_path: str) -> Dict[str, Any]:
        """OCR 图片识别"""
        return self.call_api("ocr_image", {"image": image_path})

    def upload_group_file(self, group_id: int, file_path: str, name: str = "") -> Dict[str, Any]:
        """上传群文件"""
        params = {"group_id": group_id, "file": file_path}
        if name:
            params["name"] = name
        return self.call_api("upload_group_file", params)

    def download_file(self, url: str, file_path: str) -> Dict[str, Any]:
        """下载文件"""
        return self.call_api("download_file", {
            "url": url,
            "file": file_path
        })

    def delete_group_file(self, group_id: int, file_id: str, busid: int) -> Dict[str, Any]:
        """删除群文件"""
        return self.call_api("delete_group_file", {
            "group_id": group_id,
            "file_id": file_id,
            "busid": busid
        })

    def get_group_file_system_info(self, group_id: int) -> Dict[str, Any]:
        """获取群文件系统信息"""
        return self.call_api("get_group_file_system_info", {"group_id": group_id})

    def get_group_root_files(self, group_id: int) -> Dict[str, Any]:
        """获取群根目录文件列表"""
        return self.call_api("get_group_root_files", {"group_id": group_id})

    def get_group_files_by_folder(self, group_id: int, folder_id: str) -> Dict[str, Any]:
        """获取群子目录文件列表"""
        return self.call_api("get_group_files_by_folder", {"group_id": group_id, "folder_id": folder_id})

    def get_group_file_url(self, group_id: int, file_id: str, busid: int) -> Dict[str, Any]:
        """获取群文件资源链接"""
        return self.call_api("get_group_file_url", {
            "group_id": group_id,
            "file_id": file_id,
            "busid": busid
        })

    def create_group_file_folder(self, group_id: int, name: str) -> Dict[str, Any]:
        """创建群文件文件夹"""
        return self.call_api("create_group_file_folder", {"group_id": group_id, "name": name})

    def delete_group_folder(self, group_id: int, folder_id: str) -> Dict[str, Any]:
        """删除群文件文件夹"""
        return self.call_api("delete_group_folder", {"group_id": group_id, "folder_id": folder_id})

    def get_group_at_all_remain(self, group_id: int) -> Dict[str, Any]:
        """获取群 @全体成员 剩余次数"""
        return self.call_api("get_group_at_all_remain", {"group_id": group_id})

    def send_group_forward_msg(self, group_id: int, messages: list) -> Dict[str, Any]:
        """发送群转发消息"""
        return self.call_api("send_group_forward_msg", {
            "group_id": group_id,
            "messages": messages
        })

    def send_private_forward_msg(self, user_id: int, messages: list) -> Dict[str, Any]:
        """发送私聊转发消息"""
        return self.call_api("send_private_forward_msg", {
            "user_id": user_id,
            "messages": messages
        })

    def get_group_msg_history(self, group_id: int, message_seq: int = 0, count: int = 20) -> Dict[str, Any]:
        """获取群消息历史记录"""
        return self.call_api("get_group_msg_history", {
            "group_id": group_id,
            "message_seq": message_seq,
            "count": count
        })

    def get_recently_sent_group_messages(self, group_id: int, count: int = 20) -> Dict[str, Any]:
        """获取最近发送的群消息"""
        return self.call_api("get_recently_sent_group_messages", {
            "group_id": group_id,
            "count": count
        })

    def get_recently_sent_private_messages(self, user_id: int, count: int = 20) -> Dict[str, Any]:
        """获取最近发送的私聊消息"""
        return self.call_api("get_recently_sent_private_messages", {
            "user_id": user_id,
            "count": count
        })

    def mark_msg_as_read(self, message_id: int) -> Dict[str, Any]:
        """标记消息已读"""
        return self.call_api("mark_msg_as_read", {"message_id": message_id})

    def mark_private_msg_as_read(self, user_id: int) -> Dict[str, Any]:
        """标记私聊消息已读"""
        return self.call_api("mark_private_msg_as_read", {"user_id": user_id})

    def mark_group_msg_as_read(self, group_id: int) -> Dict[str, Any]:
        """标记群消息已读"""
        return self.call_api("mark_group_msg_as_read", {"group_id": group_id})

    def get_online_clients(self, no_cache: bool = False) -> Dict[str, Any]:
        """获取在线客户端列表"""
        return self.call_api("get_online_clients", {"no_cache": no_cache})

    def check_url_safely(self, url: str) -> Dict[str, Any]:
        """检查链接安全性"""
        return self.call_api("check_url_safely", {"url": url})

    def get_model_show(self, model: str) -> Dict[str, Any]:
        """获取模型展示名"""
        return self.call_api("_get_model_show", {"model": model})

    def set_model_show(self, model: str, model_show: str) -> Dict[str, Any]:
        """设置模型展示名"""
        return self.call_api("_set_model_show", {"model": model, "model_show": model_show})

    def get_unidirectional_friend_list(self) -> Dict[str, Any]:
        """获取单向好友列表"""
        return self.call_api("get_unidirectional_friend_list")

    def delete_friend(self, user_id: int) -> Dict[str, Any]:
        """删除好友"""
        return self.call_api("delete_friend", {"user_id": user_id})

    def add_friend(self, user_id: int, remark: str = "") -> Dict[str, Any]:
        """添加好友（主动申请）"""
        return self.call_api("add_friend", {"user_id": user_id, "remark": remark})

    def create_collection(self, content: str, title: str = "") -> Dict[str, Any]:
        """创建收藏"""
        return self.call_api("_create_collection", {
            "content": content,
            "title": title
        })

    def set_profile_signature(self, signature: str) -> Dict[str, Any]:
        """设置个性签名"""
        return self.call_api("_set_profile_signature", {
            "signature": signature
        })

    def set_avatar(self, image_path: str) -> Dict[str, Any]:
        """设置QQ头像"""
        return self.call_api("_set_avatar", {
            "file": image_path
        })

    # ==================== 系统相关 API ====================
    
    def get_status(self) -> Dict[str, Any]:
        """获取运行状态"""
        return self.call_api("get_status")

    def get_version_info(self) -> Dict[str, Any]:
        """获取版本信息"""
        return self.call_api("get_version_info")

    def set_restart(self, delay: int = 0) -> Dict[str, Any]:
        """重启 OneBot 实现"""
        return self.call_api("set_restart", {"delay": delay})

    def clean_cache(self) -> Dict[str, Any]:
        """清理缓存"""
        return self.call_api("clean_cache")

    def get_supported_actions(self) -> Dict[str, Any]:
        """获取支持的动作列表"""
        return self.call_api("get_supported_actions")

    def get_latest_events(self, limit: int = 10, timeout: int = 0) -> Dict[str, Any]:
        """获取最新事件列表"""
        return self.call_api("get_latest_events", {"limit": limit, "timeout": timeout})

    def close(self):
        """关闭客户端"""
        if self.ws:
            self.ws.close()


# 全局API管理器实例
api_manager = None


def get_api_manager():
    """获取API管理器实例（延迟初始化）"""
    global api_manager
    if api_manager is None:
        api_manager = APIManager()
    return api_manager
