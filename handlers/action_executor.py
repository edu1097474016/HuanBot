"""动作执行器模块"""
import re
import json
import os
import ast
from typing import List, Dict, Any
from core.logger import logger
from core.api_manager import get_api_manager
from modules.tools.emergency_call import emergency_call


def parse_json_actions(text: str) -> List[Dict[str, Any]]:
    """
    从文本中提取 JSON 格式的 action 数组
    支持紧凑格式和多行格式化 JSON，并自动修复常见格式错误
    """
    actions = []
    cq_mapping = {}
    
    # 移除代码块标记（如果有）
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    
    # 修复常见的错误格式
    # 修复: {"action": [...] + [...]} -> {"action": [..., ...]}
    def fix_array_concat(json_str):
        pattern = r'\]\s*\+\s*\['
        if re.search(pattern, json_str):
            fixed = re.sub(pattern, ',', json_str)
            logger.debug("JSON修复", "修复了数组拼接语法")
            return fixed
        return json_str
    
    # 修复缺失的结束括号
    def fix_missing_brace(json_str):
        if json_str.count('{') > json_str.count('}'):
            json_str = json_str + '}'
            logger.debug("JSON修复", "添加了缺失的 }")
        if json_str.count('[') > json_str.count(']'):
            json_str = json_str + ']'
            logger.debug("JSON修复", "添加了缺失的 ]")
        return json_str
    
    # 修复CQ码中的特殊字符
    def fix_cq_code(json_str):
        # 查找所有CQ码
        cq_pattern = r'\[CQ:[^\]]+\]'
        cq_codes = re.findall(cq_pattern, json_str)
        
        # 创建映射并替换
        for i, cq_code in enumerate(cq_codes):
            placeholder = f"__CQ_PLACEHOLDER_{i}__"
            cq_mapping[placeholder] = cq_code
            json_str = json_str.replace(cq_code, placeholder)
        
        return json_str
    
    # 查找所有可能的 JSON 对象
    i = 0
    while i < len(text):
        if text[i] == '{':
            brace_count = 0
            in_string = False
            escape = False
            start = i
            
            for j in range(i, len(text)):
                char = text[j]
                
                if escape:
                    escape = False
                    continue
                
                if char == '\\':
                    escape = True
                    continue
                
                if char == '"':
                    in_string = not in_string
                    continue
                
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = j + 1
                            json_str = text[start:end]
                            break
            else:
                i += 1
                continue
            
            # 修复 JSON
            json_str = fix_array_concat(json_str)
            json_str = fix_missing_brace(json_str)
            json_str = fix_cq_code(json_str)
            
            try:
                # 确保使用UTF-8编码处理包含表情符号的JSON
                # 替换换行符为转义序列
                json_str = json_str.replace('\n', '\\n')
                json_str = json_str.replace('\r', '\\r')
                
                data = json.loads(json_str)
                
                if isinstance(data, dict) and 'action' in data:
                    if isinstance(data['action'], list):
                        for item in data['action']:
                            if isinstance(item, str):
                                # 格式错误：["emergency_call", {"params":...}]
                                # 需要转换为：[{"action": "emergency_call", "params": {...}}]
                                if len(data['action']) > 1 and isinstance(data['action'][1], dict):
                                    if 'params' in data['action'][1]:
                                        fixed_action = {
                                            'action': item,
                                            'params': data['action'][1]['params']
                                        }
                                        actions.append(fixed_action)
                                    elif 'action' in data['action'][1] and 'params' in data['action'][1]:
                                        # 格式已经正确，直接添加
                                        actions.append(data['action'][1])
                            elif isinstance(item, dict):
                                actions.append(item)
                        # 如果数组中没有可处理的元素，使用原始逻辑
                        if not actions:
                            actions.extend(data['action'])
                    elif isinstance(data['action'], dict):
                        actions.append(data['action'])
                
                i = end
            except json.JSONDecodeError as e:
                logger.error("JSON解析", f"解析失败: {e} - 内容: {json_str[:100]}...")
                # 尝试多种修复方法
                try:
                    # 方法1: 修复消息内容中的特殊字符
                    # 查找message字段并修复其中的特殊字符
                    message_pattern = r'"message":"([^"]*(?:\\.[^"]*)*)"'
                    
                    def fix_message_content(match):
                        message_content = match.group(1)
                        # 转义消息内容中的特殊字符
                        message_content = message_content.replace('\n', '\\n')
                        message_content = message_content.replace('\r', '\\r')
                        message_content = message_content.replace('"', '\\"')
                        message_content = message_content.replace("'", "\\'")
                        return f'"message":"{message_content}"'
                    
                    fixed_json = re.sub(message_pattern, fix_message_content, json_str)
                    data = json.loads(fixed_json)
                    if isinstance(data, dict) and 'action' in data:
                        if isinstance(data['action'], list):
                            actions.extend(data['action'])
                        elif isinstance(data['action'], dict):
                            actions.append(data['action'])
                except:
                    try:
                        # 方法2: 直接使用UTF-8编码处理
                        fixed_json = json_str.encode('utf-8').decode('utf-8')
                        data = json.loads(fixed_json)
                        if isinstance(data, dict) and 'action' in data:
                            if isinstance(data['action'], list):
                                actions.extend(data['action'])
                            elif isinstance(data['action'], dict):
                                actions.append(data['action'])
                    except:
                        try:
                            # 方法3: 清理字符串中的特殊字符
                            # 移除所有非ASCII字符
                            cleaned_json = re.sub(r'[^\x00-\x7F]+', '', json_str)
                            data = json.loads(cleaned_json)
                            if isinstance(data, dict) and 'action' in data:
                                if isinstance(data['action'], list):
                                    actions.extend(data['action'])
                                elif isinstance(data['action'], dict):
                                    actions.append(data['action'])
                        except:
                            try:
                                # 方法4: 尝试使用更宽松的解析方式
                                data = ast.literal_eval(json_str)
                                if isinstance(data, dict) and 'action' in data:
                                    if isinstance(data['action'], list):
                                        actions.extend(data['action'])
                                    elif isinstance(data['action'], dict):
                                        actions.append(data['action'])
                            except:
                                pass
                i = end
        else:
            i += 1
    
    return actions, cq_mapping


def execute_json_actions(json_actions: List[Dict[str, Any]], context: Dict[str, Any] = None, cq_mapping: Dict[str, str] = None):
    """执行JSON动作"""
    logger.info("JSON动作", f"解析出 {len(json_actions)} 个操作")
    
    # 获取上下文信息
    context = context or {}
    default_group_id = context.get('group_id')
    
    # 如果提供了CQ码映射，恢复CQ码
    if cq_mapping:
        # 恢复CQ码占位符为原始CQ码
        def restore_cq_codes(obj):
            if isinstance(obj, str):
                # 将占位符替换回原始CQ码
                for placeholder, cq_code in cq_mapping.items():
                    if placeholder in obj:
                        obj = obj.replace(placeholder, cq_code)
                return obj
            elif isinstance(obj, dict):
                return {k: restore_cq_codes(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [restore_cq_codes(item) for item in obj]
            return obj
        
        # 恢复所有动作中的CQ码
        restored_actions = []
        for action in json_actions:
            restored_action = restore_cq_codes(action)
            restored_actions.append(restored_action)
        json_actions = restored_actions
    
    for action in json_actions:
        action_name = action.get('action')
        params = action.get('params', {})
        
        if not action_name:
            logger.warning("JSON动作", "缺少action字段")
            continue
        
        logger.info("JSON动作", f"执行操作: {action_name}, 参数: {params}")
        
        try:
            if action_name == 'send_group_msg':
                group_id = params.get('group_id') or default_group_id
                message = params.get('message', '')
                if group_id and message:
                    # 检查消息是否包含图片CQ码并转换为base64格式
                    import re
                    image_pattern = r'\[CQ:image,file=([^\]]+)\]'
                    
                    def convert_to_base64(match):
                        image_path = match.group(1)
                        import os
                        import base64
                        
                        # 获取完整路径
                        filename = os.path.basename(image_path)
                        full_path = os.path.join('data', 'emoji', filename)
                        
                        if os.path.exists(full_path):
                            try:
                                with open(full_path, 'rb') as f:
                                    image_data = f.read()
                                base64_data = base64.b64encode(image_data).decode('utf-8')
                                return f'[CQ:image,file=base64://{base64_data}]'
                            except Exception as e:
                                logger.error("JSON动作", f"转换图片为base64失败: {e}")
                                return match.group(0)
                        else:
                            logger.error("JSON动作", f"图片文件不存在: {full_path}")
                            return match.group(0)
                    
                    # 转换所有图片为base64格式
                    message = re.sub(image_pattern, convert_to_base64, message)
                    
                    logger.info("JSON动作", f"发送消息内容: {message[:100]}...")
                    
                    # 发送修复后的消息
                    result = get_api_manager().send_group_msg(group_id, message)
                    logger.info("JSON动作", f"发送群消息成功，API返回: {result}")
                else:
                    logger.error("JSON动作", f"参数缺失: group_id={group_id}, message={message}")
            
            elif action_name == 'send_group_image':
                group_id = params.get('group_id') or default_group_id
                image_path = params.get('image_path')
                if group_id and image_path:
                    result = get_api_manager().send_group_image(group_id, image_path)
                    logger.info("JSON动作", f"发送群图片成功")
                else:
                    logger.error("JSON动作", f"参数缺失")
            
            elif action_name == 'send_group_at':
                group_id = params.get('group_id') or default_group_id
                user_id = params.get('user_id')
                text = params.get('text', '')
                if group_id and user_id and text:
                    result = get_api_manager().send_group_at(group_id, user_id, text)
                    logger.info("JSON动作", f"发送@消息成功")
                else:
                    logger.error("JSON动作", f"参数缺失: group_id={group_id}, user_id={user_id}")
            
            elif action_name == 'send_group_reply':
                group_id = params.get('group_id') or default_group_id
                message_id = params.get('message_id')
                text = params.get('text', '')
                if group_id and message_id and text:
                    result = get_api_manager().send_group_reply(group_id, message_id, text)
                    logger.info("JSON动作", f"发送回复消息成功")
                else:
                    logger.error("JSON动作", f"参数缺失")
            
            elif action_name == 'send_private_text':
                user_id = params.get('user_id')
                text = params.get('text', '')
                if user_id and text:
                    try:
                        user_id = int(user_id)
                        
                        # 检查是否为好友关系
                        friend_list = get_api_manager().get_friend_list()
                        if friend_list.get("status") == "ok":
                            friends = friend_list.get("data", [])
                            friend_ids = [friend.get("user_id") for friend in friends]
                            if user_id not in friend_ids:
                                logger.warning("JSON动作", f"用户 {user_id} 不是好友，无法发送私聊消息")
                                return
                        
                        result = get_api_manager().send_private_msg(user_id, text)
                        logger.info("JSON动作", f"发送私聊消息成功")
                    except ValueError:
                        logger.error("JSON动作", f"user_id 必须是整数类型: {user_id}")
                else:
                    logger.error("JSON动作", f"参数缺失")
            
            elif action_name == 'send_group_notice':
                group_id = params.get('group_id') or default_group_id
                content = params.get('content', '')
                if group_id and content:
                    result = get_api_manager().send_group_notice(group_id, content)
                    logger.info("JSON动作", f"发送群公告成功")
                else:
                    logger.error("JSON动作", f"参数缺失")
            
            elif action_name == 'set_group_ban':
                group_id = params.get('group_id') or default_group_id
                user_id = params.get('user_id')
                duration = params.get('duration', 3600)
                if group_id and user_id:
                    try:
                        user_id = int(user_id)
                        duration = int(duration)
                        result = get_api_manager().set_group_ban(group_id, user_id, duration)
                        logger.info("JSON动作", f"禁言成功")
                    except ValueError:
                        logger.error("JSON动作", f"参数类型错误")
                else:
                    logger.error("JSON动作", f"参数缺失")
            
            elif action_name == 'get_user_id_by_name':
                group_id = params.get('group_id') or default_group_id
                name = params.get('name')
                if group_id and name:
                    try:
                        from modules.tools.user_manager import get_user_id_by_name
                        user_id = get_user_id_by_name(group_id, name)
                        logger.info("JSON动作", f"根据昵称获取用户ID成功: {name} -> {user_id}")
                    except Exception as e:
                        logger.error("JSON动作", f"获取用户ID失败: {e}")
                else:
                    logger.error("JSON动作", f"参数缺失")
            
            elif action_name == 'emergency_call':
                location = params.get('location')
                details = params.get('details')
                user_name = params.get('user_name')
                phone_number = params.get('phone_number')
                extra_info = params.get('extra_info')
                
                if location and details:
                    result = emergency_call(location, details, user_name, phone_number, extra_info)
                    logger.info("JSON动作", f"紧急呼救成功")
                else:
                    logger.error("JSON动作", f"参数缺失: location和details为必填项")
            
            elif action_name == 'weather_query':
                city = params.get('city')
                if city:
                    try:
                        from modules.tools.weather_query import query_weather
                        weather_info = query_weather(city)
                        logger.info("JSON动作", f"天气查询成功: {city}")
                        
                        # 获取当前群号并发送天气信息
                        group_id = params.get('group_id') or default_group_id
                        if group_id:
                            get_api_manager().send_group_msg(group_id, weather_info)
                        else:
                            logger.warning("JSON动作", "天气查询成功但未指定发送目标")
                    except Exception as e:
                        logger.error("JSON动作", f"天气查询失败: {e}")
                else:
                    logger.error("JSON动作", f"参数缺失: city为必填项")
            
            elif action_name == 'web_query':
                query = params.get('query')
                if query:
                    try:
                        from modules.tools.web_search import web_query
                        result = web_query(query)
                        logger.info("JSON动作", f"网络查询成功: {query[:50]}...")
                        
                        # 获取当前群号并发送查询结果
                        group_id = params.get('group_id') or default_group_id
                        if group_id:
                            get_api_manager().send_group_msg(group_id, result)
                        else:
                            logger.warning("JSON动作", "网络查询成功但未指定发送目标")
                    except Exception as e:
                        logger.error("JSON动作", f"网络查询失败: {e}")
                else:
                    logger.error("JSON动作", f"参数缺失: query为必填项")
            
            elif action_name == 'update_album':
                try:
                    from modules.tools.photo_crawler import update_album
                    new_photos = update_album()
                    logger.info("JSON动作", f"相册更新成功，新增 {len(new_photos)} 张照片")
                    
                    # 获取当前群号并发送更新通知
                    group_id = params.get('group_id') or default_group_id
                    if group_id:
                        message = f"📸 相册更新成功！\n\n新增 {len(new_photos)} 张美丽的风景照～"
                        get_api_manager().send_group_msg(group_id, message)
                    else:
                        logger.warning("JSON动作", "相册更新成功但未指定发送目标")
                except Exception as e:
                    logger.error("JSON动作", f"相册更新失败: {e}")
            
            elif action_name == 'get_album_photos':
                try:
                    from modules.tools.photo_crawler import get_album_photos
                    photos = get_album_photos()
                    logger.info("JSON动作", f"获取相册照片成功，共 {len(photos)} 张")
                    
                    # 获取当前群号并发送照片列表
                    group_id = params.get('group_id') or default_group_id
                    if group_id:
                        if photos:
                            message = f"📸 相册共有 {len(photos)} 张照片：\n"
                            for i, photo in enumerate(photos[:5], 1):
                                message += f"{i}. {os.path.basename(photo)}\n"
                            if len(photos) > 5:
                                message += f"... 还有 {len(photos) - 5} 张照片"
                        else:
                            message = "📸 相册目前为空"
                        get_api_manager().send_group_msg(group_id, message)
                    else:
                        logger.warning("JSON动作", "获取相册照片成功但未指定发送目标")
                except Exception as e:
                    logger.error("JSON动作", f"获取相册照片失败: {e}")
            
            elif hasattr(get_api_manager(), action_name):
                method = getattr(get_api_manager(), action_name)
                result = method(**params)
                logger.info("JSON动作", f"API调用 {action_name} 结果: {result}")
            else:
                logger.warning("JSON动作", f"未知操作: {action_name}")
                
        except Exception as e:
            logger.error("JSON动作", f"操作 {action_name} 失败: {e}")
            import traceback
            traceback.print_exc()


def parse_all_messages(text: str) -> List[Dict[str, Any]]:
    """解析所有消息（文本和图片）"""
    messages = []
    
    # 解析CQ码图片
    image_pattern = r'\[CQ:image,file=([^\]]+)\]'
    for match in re.finditer(image_pattern, text):
        image_path = match.group(1)
        messages.append({
            'type': 'image',
            'path': image_path
        })
    
    # 提取文本部分（移除CQ码）
    text_content = re.sub(image_pattern, '', text).strip()
    if text_content:
        messages.append({
            'type': 'text',
            'content': text_content
        })
    
    return messages
