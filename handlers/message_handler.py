"""消息处理器模块"""
import re
import os
import json
import time
from typing import Dict, Any, List
from core.config import config
from core.logger import logger
from core.api_manager import get_api_manager
from modules.memory.vector_memory import VectorMemory
from modules.llm.llm_client import call_llm, get_llm_model
from modules.tools.emoji_manager import get_emoji_manager


class MessageHandler:
    """消息处理器类"""
    
    def __init__(self):
        """初始化消息处理器"""
        self.BOT_QQ = config.require("bot.qq")
        self.ADMIN_QQ = config.require("bot.admin_qq")
        self.GROUP_ID = config.require("bot.group_id")
        self.ACTIVE_THRESHOLD = config.require("bot.active_threshold")
        self.ACTIVE_CHECK_INTERVAL = config.require("bot.active_check_interval")
        self.memory = None
        self.emoji_manager = None
        
        # 加载个性和行为提示词
        self.personality = config.get("bot.personality", "")
        self.behavior = config.get("bot.behavior", "")
        self.tools = self._load_tools()
        
        # 提前加载记忆模块
        self.get_memory()
        
    def _load_tools(self) -> str:
        """加载工具描述"""
        tools_desc = '''你只能输出一类内容：
JSON 工具调用：{"action":[...]}。

你必须严格按照下面的格式输出：
{"action":[{"action":"action_name","params":{"key":"value"}}]}

可用工具列表：

=== 基础消息操作 ===
send_private_msg(user_id, message, auto_escape=false)
- 功能：发送私聊消息
- 场景：与用户私聊沟通
- 参数：user_id(用户QQ), message(消息内容), auto_escape(是否作为纯文本发送)
- 示例：{"action":[{"action":"send_private_msg","params":{"user_id":670735494,"message":"你好！"}}]}

send_group_msg(group_id, message, auto_escape=false)
- 功能：发送群消息
- 场景：在群里发送消息
- 参数：group_id(群号), message(消息内容), auto_escape(是否作为纯文本发送)
- 示例：{"action":[{"action":"send_group_msg","params":{"group_id":1087824597,"message":"大家好！"}}]}

send_msg(message_type, user_id, group_id, message, auto_escape=false)
- 功能：发送消息（通用）
- 场景：发送私聊或群消息
- 参数：message_type(private/group), user_id(私聊时需要), group_id(群聊时需要), message(消息内容)
- 示例：{"action":[{"action":"send_msg","params":{"message_type":"group","group_id":1087824597,"message":"测试消息"}}]}

delete_msg(message_id)
- 功能：撤回消息
- 场景：撤回已发送的消息
- 参数：message_id(消息ID)
- 示例：{"action":[{"action":"delete_msg","params":{"message_id":123456789}}]}

get_msg(message_id)
- 功能：获取消息
- 场景：查看特定消息内容
- 参数：message_id(消息ID)
- 示例：{"action":[{"action":"get_msg","params":{"message_id":123456789}}]}

get_forward_msg(id)
- 功能：获取合并转发消息
- 场景：查看合并转发的内容
- 参数：id(合并转发ID)
- 示例：{"action":[{"action":"get_forward_msg","params":{"id":"forward_id"}}]}

send_like(user_id, times=1)
- 功能：发送好友赞
- 场景：给好友点赞
- 参数：user_id(用户QQ), times(点赞次数)
- 示例：{"action":[{"action":"send_like","params":{"user_id":670735494,"times":5}}]}

=== 群管理操作 ===
set_group_kick(group_id, user_id, reject_add_request=false)
- 功能：群组踢人
- 场景：将成员移出群聊
- 参数：group_id(群号), user_id(用户QQ), reject_add_request(是否拒绝加群请求)
- 示例：{"action":[{"action":"set_group_kick","params":{"group_id":1087824597,"user_id":670735494}}]}

set_group_ban(group_id, user_id, duration=1800)
- 功能：群组单人禁言
- 场景：禁言群成员
- 参数：group_id(群号), user_id(用户QQ), duration(禁言时长，秒)
- 示例：{"action":[{"action":"set_group_ban","params":{"group_id":1087824597,"user_id":670735494,"duration":3600}}]}

set_group_whole_ban(group_id, enable=true)
- 功能：群组全员禁言
- 场景：全员禁言或取消禁言
- 参数：group_id(群号), enable(是否禁言)
- 示例：{"action":[{"action":"set_group_whole_ban","params":{"group_id":1087824597,"enable":true}}]}

set_group_admin(group_id, user_id, enable=true)
- 功能：群组设置管理员
- 场景：设置或取消管理员
- 参数：group_id(群号), user_id(用户QQ), enable(是否设置)
- 示例：{"action":[{"action":"set_group_admin","params":{"group_id":1087824597,"user_id":670735494,"enable":true}}]}

set_group_card(group_id, user_id, card="")
- 功能：设置群名片（群备注）
- 场景：修改群成员的群名片
- 参数：group_id(群号), user_id(用户QQ), card(群名片内容)
- 示例：{"action":[{"action":"set_group_card","params":{"group_id":1087824597,"user_id":670735494,"card":"测试用户"}}]}

set_group_name(group_id, group_name)
- 功能：设置群名
- 场景：修改群名称
- 参数：group_id(群号), group_name(新群名)
- 示例：{"action":[{"action":"set_group_name","params":{"group_id":1087824597,"group_name":"新群名"}}]}

set_group_leave(group_id, is_dismiss=false)
- 功能：退出群组
- 场景：退出群聊或解散群聊
- 参数：group_id(群号), is_dismiss(是否解散群聊)
- 示例：{"action":[{"action":"set_group_leave","params":{"group_id":1087824597,"is_dismiss":false}}]}

send_group_notice(group_id, content)
- 功能：发送群公告
- 场景：发布群公告
- 参数：group_id(群号), content(公告内容)
- 示例：{"action":[{"action":"send_group_notice","params":{"group_id":1087824597,"content":"群公告内容"}}]}

=== 请求处理 ===
set_friend_add_request(flag, approve=true, remark="")
- 功能：处理加好友请求
- 场景：同意或拒绝好友请求
- 参数：flag(请求标识), approve(是否同意), remark(好友备注)
- 示例：{"action":[{"action":"set_friend_add_request","params":{"flag":"request_flag","approve":true,"remark":"好友备注"}}]}

set_group_add_request(flag, sub_type, approve=true, reason="")
- 功能：处理加群请求/邀请
- 场景：同意或拒绝加群请求
- 参数：flag(请求标识), sub_type(add/invite), approve(是否同意), reason(拒绝理由)
- 示例：{"action":[{"action":"set_group_add_request","params":{"flag":"request_flag","sub_type":"add","approve":true}}]}

=== 信息查询 ===
get_login_info()
- 功能：获取登录号信息
- 场景：查看机器人自身信息
- 参数：无
- 示例：{"action":[{"action":"get_login_info","params":{}}]}

get_stranger_info(user_id, no_cache=false)
- 功能：获取陌生人信息
- 场景：查看陌生人的基本信息
- 参数：user_id(用户QQ), no_cache(是否不使用缓存)
- 示例：{"action":[{"action":"get_stranger_info","params":{"user_id":670735494}}]}

get_friend_list()
- 功能：获取好友列表
- 场景：查看好友列表
- 参数：无
- 示例：{"action":[{"action":"get_friend_list","params":{}}]}

get_group_info(group_id, no_cache=false)
- 功能：获取群信息
- 场景：查看群的基本信息
- 参数：group_id(群号), no_cache(是否不使用缓存)
- 示例：{"action":[{"action":"get_group_info","params":{"group_id":1087824597}}]}

get_group_list()
- 功能：获取群列表
- 场景：查看加入的群列表
- 参数：无
- 示例：{"action":[{"action":"get_group_list","params":{}}]}

get_group_member_info(group_id, user_id, no_cache=false)
- 功能：获取群成员信息
- 场景：查看群成员详情
- 参数：group_id(群号), user_id(用户QQ), no_cache(是否不使用缓存)
- 示例：{"action":[{"action":"get_group_member_info","params":{"group_id":1087824597,"user_id":670735494}}]}

get_group_member_list(group_id)
- 功能：获取群成员列表
- 场景：查看群成员列表
- 参数：group_id(群号)
- 示例：{"action":[{"action":"get_group_member_list","params":{"group_id":1087824597}}]}

get_group_honor_info(group_id, type)
- 功能：获取群荣誉信息
- 场景：查看群荣誉（龙王、群聊之火等）
- 参数：group_id(群号), type(荣誉类型)
- 示例：{"action":[{"action":"get_group_honor_info","params":{"group_id":1087824597,"type":"talkative"}}]}

get_group_at_all_remain(group_id)
- 功能：获取@全体成员剩余次数
- 场景：检查@全体权限
- 参数：group_id(群号)
- 示例：{"action":[{"action":"get_group_at_all_remain","params":{"group_id":1087824597}}]}

=== 媒体操作 ===
get_record(file, out_format)
- 功能：获取语音
- 场景：转换语音文件格式
- 参数：file(语音文件名), out_format(输出格式)
- 示例：{"action":[{"action":"get_record","params":{"file":"voice.amr","out_format":"mp3"}}]}

get_image(file)
- 功能：获取图片
- 场景：下载图片文件
- 参数：file(图片文件名)
- 示例：{"action":[{"action":"get_image","params":{"file":"image.jpg"}}]}

can_send_image()
- 功能：检查是否可以发送图片
- 场景：确认图片发送权限
- 参数：无
- 示例：{"action":[{"action":"can_send_image","params":{}}]}

can_send_record()
- 功能：检查是否可以发送语音
- 场景：确认语音发送权限
- 参数：无
- 示例：{"action":[{"action":"can_send_record","params":{}}]}

upload_group_file(group_id, file_path, name="")
- 功能：上传群文件
- 场景：上传文件到群文件
- 参数：group_id(群号), file_path(文件路径), name(文件名称)
- 示例：{"action":[{"action":"upload_group_file","params":{"group_id":1087824597,"file_path":"test.txt","name":"测试文件.txt"}}]}

download_file(url, file_path)
- 功能：下载文件
- 场景：下载网络文件
- 参数：url(文件URL), file_path(保存路径)
- 示例：{"action":[{"action":"download_file","params":{"url":"https://example.com/file.jpg","file_path":"downloaded.jpg"}}]}

=== 转发消息 ===
send_group_forward_msg(group_id, messages)
- 功能：发送群转发消息
- 场景：转发多条消息到群聊
- 参数：group_id(群号), messages(消息数组)
- 示例：{"action":[{"action":"send_group_forward_msg","params":{"group_id":1087824597,"messages":[{"type":"text","data":{"text":"消息1"}}]}}]}

send_private_forward_msg(user_id, messages)
- 功能：发送私聊转发消息
- 场景：转发多条消息到私聊
- 参数：user_id(用户QQ), messages(消息数组)
- 示例：{"action":[{"action":"send_private_forward_msg","params":{"user_id":670735494,"messages":[{"type":"text","data":{"text":"消息1"}}]}}]}

=== 扩展功能 ===
get_cookies(domain="")
- 功能：获取Cookies
- 场景：获取特定域名的Cookies
- 参数：domain(域名)
- 示例：{"action":[{"action":"get_cookies","params":{"domain":"example.com"}}]}

get_csrf_token()
- 功能：获取CSRF Token
- 场景：获取CSRF令牌
- 参数：无
- 示例：{"action":[{"action":"get_csrf_token","params":{}}]}

get_credentials(domain="")
- 功能：获取QQ相关接口凭证
- 场景：获取Cookies和CSRF Token
- 参数：domain(域名)
- 示例：{"action":[{"action":"get_credentials","params":{"domain":"example.com"}}]}

get_status()
- 功能：获取运行状态
- 场景：检查机器人运行状态
- 参数：无
- 示例：{"action":[{"action":"get_status","params":{}}]}

get_version_info()
- 功能：获取版本信息
- 场景：查看版本信息
- 参数：无
- 示例：{"action":[{"action":"get_version_info","params":{}}]}

set_restart(delay=0)
- 功能：重启OneBot实现
- 场景：重启机器人
- 参数：delay(延迟毫秒数)
- 示例：{"action":[{"action":"set_restart","params":{"delay":1000}}]}

clean_cache()
- 功能：清理缓存
- 场景：清理机器人缓存
- 参数：无
- 示例：{"action":[{"action":"clean_cache","params":{}}]}

batch_group_kick(group_id, user_ids, reject_add_request=false)
- 功能：批量踢出群成员
- 场景：需要一次性踢出多个群成员时使用
- 参数：group_id(群号), user_ids(用户ID列表), reject_add_request(是否拒绝加群请求)
- 示例：{"action":[{"action":"batch_group_kick","params":{"group_id":1087824597,"user_ids":[12345678,87654321]}}]}

create_collection(content, title="")
- 功能：创建收藏
- 场景：需要收藏重要消息或内容时使用
- 参数：content(收藏内容), title(收藏标题)
- 示例：{"action":[{"action":"create_collection","params":{"content":"重要信息","title":"会议记录"}}]}

set_profile_signature(signature)
- 功能：设置个性签名
- 场景：需要更新QQ个性签名时使用
- 参数：signature(个性签名内容)
- 示例：{"action":[{"action":"set_profile_signature","params":{"signature":"今天天气真好！"}}]}

set_avatar(image_path)
- 功能：设置QQ头像
- 场景：需要更新QQ头像时使用
- 参数：image_path(图片文件路径)
- 示例：{"action":[{"action":"set_avatar","params":{"image_path":"data/emoji/avatar.jpg"}}]}

=== 自定义功能 ===
get_user_id_by_name(group_id, name)
- 功能：根据昵称或群名片查找用户的真实QQ号
- 场景：当你只知道用户昵称但不知道QQ号时，可以使用此功能获取真实ID
- 参数：group_id(群号), name(用户昵称或群名片)
- 示例：{"action":[{"action":"get_user_id_by_name","params":{"group_id":1087824597,"name":"阿白"}}]}

emergency_call(location, details, user_name=None, phone_number=None, extra_info=None)
- 功能：发起紧急呼救，自动拨打紧急电话并播放求救语音
- 场景：用户遇到紧急情况需要帮助时，如果对方已处在呼救状态下的同时如果获取到对方位置信息，就立即发起呼救，并在群内不断发消息求助。
- 参数：
  - location: 必填，求助者位置（如：北京市朝阳区XX街道XX号）
  - details: 必填，求助者详细情况（如：突发心脏病，需要急救）
  - user_name: 可选，求助者姓名
  - phone_number: 可选，紧急联系电话（默认使用配置中的号码）
  - extra_info: 可选，额外信息（如：病史、过敏史等）
- 示例：{"action":[{"action":"emergency_call","params":{"location":"北京市朝阳区医院","details":"突发心脏病，需要急救","user_name":"张三"}}]}

weather_query(city)
- 功能：查询指定城市的天气信息
- 场景：用户询问天气情况时使用
- 参数：city(城市名称)
- 示例：{"action":[{"action":"weather_query","params":{"city":"杭州"}}]}
- 返回：包含温度、天气状况、风力、湿度等信息的天气报告

web_query(url)
- 功能：提取网页内容并总结
- 场景：用户提供网页链接，需要获取页面内容并让LLM进行总结回复时使用
- 参数：url(网页URL链接)
- 示例：{"action":[{"action":"web_query","params":{"query":"https://www.example.com"}}]}
- 返回：网页内容摘要，包含标题和主要内容
- 安全说明：所有URL都会经过安全审查，确保访问安全
- 注意：只支持HTTP/HTTPS协议的网页链接

update_album()
- 功能：手动更新相册，爬取新的风景照片
- 场景：用户要求立即更新相册或需要获取最新照片时使用
- 参数：无
- 示例：{"action":[{"action":"update_album","params":{}}]}
- 返回：更新后的照片数量和状态信息

get_album_photos()
- 功能：获取相册中的所有照片
- 场景：用户需要查看相册内容或获取照片列表时使用
- 参数：无
- 示例：{"action":[{"action":"get_album_photos","params":{}}]}
- 返回：相册中的照片文件路径列表'''
        return tools_desc
    
    def get_memory(self):
        """获取记忆模块实例"""
        if self.memory is None:
            try:
                self.memory = VectorMemory()
            except Exception as e:
                logger.error("记忆系统", f"初始化失败: {e}")
                # 创建一个空的对象作为备用
                class DummyMemory:
                    def get_recent_memories(self, lines):
                        return []
                    def search_similar(self, query, top_k):
                        return []
                    def add_memory(self, content):
                        pass
                self.memory = DummyMemory()
        return self.memory
    
    def get_emoji_manager(self):
        """获取表情包管理器实例"""
        if self.emoji_manager is None:
            self.emoji_manager = get_emoji_manager()
        return self.emoji_manager
    
    def generate_behavior_plan(self, user_question: str, memory_text: str, 
                              image_hint: str, user_id: int = None, message_type: str = "group") -> str:
        """生成行为计划"""
        planner_model = get_llm_model("planner")
        system_content = (
            f"{self.personality}{self.behavior}\n"
            "你是行为规划器，只负责判断用户意图和后续步骤。不要直接调用工具，也不要输出 JSON。"
            "你必须判断是否需要：继续追问、发送消息、禁言、天气查询、发起紧急呼救或其他 NapCat 操作。"
            "把最终判断和建议写成简洁的行为计划。"
        )
        user_content = (
            f"消息类型: {message_type}\n"
            f"用户: {user_question}\n"
            f"记忆: {memory_text}\n"
            f"可用图片: {image_hint}\n"
        )
        if user_id:
            user_content += f"当前用户ID: {user_id}\n"
        user_content += "请给出一个简洁的行为计划。"
        
        response = call_llm([
            {'role': 'system', 'content': system_content},
            {'role': 'user', 'content': user_content}
        ], model_name=planner_model, stream=False)
        
        try:
            if response and hasattr(response, 'choices') and response.choices:
                if response.choices[0].message and response.choices[0].message.content:
                    return response.choices[0].message.content.strip()
            logger.warning("规划器", "规划器返回空结果")
            return "发送消息：规划器内容为空，请稍后再试"
        except Exception as e:
            logger.error("规划器", f"生成行为计划失败: {e}")
            return "发送消息：规划器错误，请稍后再试"
    
    def generate_tool_response(self, plan: str, user_question: str, memory_text: str, 
                             image_hint: str, user_id: int = None, message_type: str = "group") -> str:
        """生成工具调用响应"""
        executor_model = get_llm_model("executor")
        system_content = (
            f"{self.personality}{self.behavior}{self.tools}\n"
            "你是工具调用者。根据行为计划把输出严格转换为 JSON action。"
            "如果需要继续问问题或者要调用工具，输出完整的 JSON action。"
            f"重要：当前消息类型是 {message_type}，当前群号是 {self.GROUP_ID}，所有 send_group_xxx 操作的 group_id 参数都必须使用这个值，不要使用示例中的假数字！"
            "重要：发送图片时，请使用完整的文件路径（如 data/emoji/emoji_123.jpg），不要只使用文件名！"
            "重要：发送包含CQ码的消息时，请使用send_group_msg，并在message参数中包含CQ码，例如：[CQ:image,file=data/emoji/emoji_123.jpg]，系统会自动处理图片发送"
        )
        if user_id:
            system_content += f"重要：当前用户ID是 {user_id}，所有 send_private_xxx 操作的 user_id 参数都必须使用这个值，不要使用示例中的假数字！"
        system_content += f"重要：如果当前是私聊消息（message_type=private），你可以选择继续私聊回复用户，或者根据情况发送群消息。"
        
        user_content = (
            f"消息类型: {message_type}\n"
            f"用户: {user_question}\n"
            f"行为计划: {plan}\n"
            f"记忆: {memory_text}\n"
            f"可用图片: {image_hint}\n"
        )
        if user_id:
            user_content += f"当前用户ID: {user_id}\n"
        user_content += "请生成最终回复。"
        
        response = call_llm([
            {'role': 'system', 'content': system_content},
            {'role': 'user', 'content': user_content}
        ], model_name=executor_model, stream=True)
        
        full_response = ""
        for chunk in response:
            if hasattr(chunk, 'choices') and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                    full_response += delta.content
        
        return full_response
    
    def process_message(self, user_question: str, user_id: int, user_name: str, message_id: int, message_type: str = "group", group_id: int = None):
        """处理用户消息"""
        logger.info("AI处理", f"开始处理用户 {user_name} 的消息")
        
        try:
            # 检查并保存图片消息
            self._save_image_message(user_question, user_name)
            
            # 检测URL并提取内容（无需经过LLM）
            import re
            url_pattern = r'https?://[^\s]+'
            
            # 提取消息中的文本内容
            message_text = ""
            if isinstance(user_question, list):
                # 处理列表格式的消息
                logger.info("URL检测", f"消息类型为列表，长度: {len(user_question)}")
                for i, msg_part in enumerate(user_question):
                    logger.info("URL检测", f"消息部分[{i}]: {msg_part}")
                    if isinstance(msg_part, dict) and msg_part.get('type') == 'text':
                        text_content = msg_part.get('data', {}).get('text', '')
                        message_text += text_content
                        logger.info("URL检测", f"提取到文本: {text_content}")
            elif isinstance(user_question, str):
                message_text = user_question
                logger.info("URL检测", f"消息类型为字符串: {message_text}")
            
            # 检测URL
            urls = re.findall(url_pattern, message_text)
            logger.info("URL检测", f"消息文本: {message_text}")
            logger.info("URL检测", f"检测到URL列表: {urls}")
            
            if urls:
                logger.info("URL检测", f"检测到URL: {urls[0]}，开始提取内容")
                from modules.tools.web_search import extract_content_from_url
                content = extract_content_from_url(urls[0])
                logger.info("URL检测", f"提取的内容长度: {len(content)}")
                # 直接发送提取的内容
                api_manager = get_api_manager()
                if message_type == "group" and group_id:
                    api_manager.send_group_msg(group_id, content)
                else:
                    api_manager.send_private_msg(user_id, content)
                # 将提取的内容添加到用户问题中，供LLM后续处理
                if isinstance(user_question, str):
                    user_question += f"\n\n【网页内容】\n{content}"
                else:
                    # 如果是列表格式，添加文本部分
                    user_question.append({
                        'type': 'text',
                        'data': {'text': f"\n\n【网页内容】\n{content}"}
                    })
            
            # 获取记忆
            memory_text = self._get_relevant_memories(user_question)
            
            # 获取图片提示
            image_hint = self._get_image_hint()
            
            # 生成行为计划
            plan = self.generate_behavior_plan(user_question, memory_text, image_hint, user_id, message_type)
            logger.info("规划器", "行为规划完成")
            logger.info("规划器", f"行为计划:\n{plan}")
            
            # 生成工具调用响应
            response = self.generate_tool_response(plan, user_question, memory_text, image_hint, user_id, message_type)
            logger.bot_response(response, add_to_memory=False)
            
            # 解析并执行JSON动作
            from handlers.action_executor import parse_json_actions, execute_json_actions
            json_actions, cq_mapping = parse_json_actions(response)
            if json_actions:
                # 传递上下文信息
                context = {}
                if group_id:
                    context['group_id'] = group_id
                execute_json_actions(json_actions, context, cq_mapping)
            
        except Exception as e:
            error_detail = str(e)[:200]
            logger.error("AI处理", f"处理消息时出错: {error_detail}", e)
            self._send_error_notification("AI处理错误", error_detail)
    
    def _save_image_message(self, message: str, user_name: str):
        """保存图片消息到表情包库"""
        try:
            import re
            import json
            import requests
            import os
            
            # 检查消息格式
            if isinstance(message, list):
                # 处理列表格式的消息
                for msg_part in message:
                    if isinstance(msg_part, dict) and msg_part.get('type') == 'image':
                        data = msg_part.get('data', {})
                        url = data.get('url')
                        if url:
                            # 下载图片
                            self._download_and_save_image(url, user_name)
            else:
                # 处理字符串格式的消息
                # 尝试解析消息中的图片URL
                image_url_pattern = r"'url':\s*'([^']+\.(jpg|jpeg|png|gif))'"
                matches = re.findall(image_url_pattern, str(message))
                
                if matches:
                    emoji_manager = self.get_emoji_manager()
                    
                    for url, ext in matches:
                        try:
                            # 下载图片
                            response = requests.get(url, timeout=10)
                            if response.status_code == 200:
                                # 创建临时文件
                                temp_filename = f"temp_{user_name}_{int(time.time())}.{ext}"
                                temp_path = os.path.join(os.getcwd(), temp_filename)
                                
                                with open(temp_path, 'wb') as f:
                                    f.write(response.content)
                                
                                # 添加到表情包库
                                emoji_manager.add_emoji(temp_path)
                                
                                # 删除临时文件
                                os.remove(temp_path)
                                logger.info("表情包管理", f"已保存用户 {user_name} 发送的图片")
                        except Exception as e:
                            logger.error("表情包管理", f"保存图片失败: {e}")
        except Exception as e:
            logger.error("表情包管理", f"处理图片消息失败: {e}")
    
    def _download_and_save_image(self, url: str, user_name: str):
        """下载并保存图片"""
        try:
            import requests
            import os
            import shutil
            from urllib.parse import urlparse
            
            # 获取文件扩展名
            parsed_url = urlparse(url)
            ext = os.path.splitext(parsed_url.path)[1][1:]  # 去掉点号
            if not ext:
                ext = 'jpg'
            
            # 下载图片
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                # 创建临时文件
                temp_filename = f"temp_{user_name}_{int(time.time())}.{ext}"
                temp_path = os.path.join(os.getcwd(), temp_filename)
                
                # 写入文件
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                
                # 添加到表情包库
                emoji_manager = self.get_emoji_manager()
                emoji_manager.add_emoji(temp_path)
                
                # 确保文件关闭后再删除
                time.sleep(0.1)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                logger.info("表情包管理", f"已保存用户 {user_name} 发送的图片")
        except Exception as e:
            logger.error("表情包管理", f"下载图片失败: {e}")
    
    def _get_relevant_memories(self, query: str) -> str:
        """获取相关记忆"""
        memory = self.get_memory()
        recent_memories = memory.get_recent_memories(10)
        similar_memories = memory.search_similar(query, 5)
        
        memory_text = ""
        if recent_memories:
            memory_text += "最近记忆:\n" + "\n".join(recent_memories[:5]) + "\n\n"
        if similar_memories:
            memory_text += "相关记忆:\n" + "\n".join(similar_memories[:3])
        
        return memory_text
    
    def _get_image_hint(self) -> str:
        """获取图片提示"""
        emoji_manager = self.get_emoji_manager()
        recent_emojis = emoji_manager.get_recent_emojis(20)
        return "、".join(recent_emojis) if recent_emojis else "无"
    
    def _send_error_notification(self, error_type: str, error_detail: str):
        """发送错误通知"""
        try:
            api_manager = get_api_manager()
            message = f"@全体人员 能否有人告诉阿白我的ai出了点问题 {error_type}: {error_detail}"
            result = api_manager.send_group_msg(self.GROUP_ID, message)
            if result.get("status") == "ok":
                logger.info("消息发送", f"目标群: {self.GROUP_ID}, 消息内容: {message}")
                logger.info("消息发送", f"API返回结果: {result}")
                logger.info("消息发送", "消息发送成功")
                logger.info("错误通知", f"已发送错误通知到群: {error_type}")
            else:
                logger.error("消息发送", f"发送失败: {result}")
        except Exception as e:
            logger.error("错误通知", f"发送错误通知失败: {e}")
