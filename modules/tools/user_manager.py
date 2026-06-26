"""用户管理模块"""
from core.api_manager import get_api_manager
from core.logger import logger


def get_user_id_by_name(group_id: int, name: str) -> int:
    """根据昵称或群名片在群成员中查找QQ号"""
    try:
        members = get_api_manager().get_group_member_list(group_id)
        if members.get("status") == "ok" and "data" in members:
            for member in members["data"]:
                card = member.get("card", "")
                nickname = member.get("nickname", "")
                if card == name or nickname == name:
                    return member.get("user_id")
        return None
    except Exception as e:
        logger.error("用户查询", f"查找用户失败: {e}")
        return None
