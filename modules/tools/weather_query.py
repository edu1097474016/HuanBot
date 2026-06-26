"""天气查询模块"""
import requests
import json
from core.logger import logger
from core.config import config

def query_weather(city: str) -> str:
    """
    查询指定城市的天气
    
    Args:
        city: 城市名称
        
    Returns:
        天气信息文本
    """
    try:
        api_key = config.get("weather", {}).get("api_key", "")
        
        if not api_key:
            return "天气API密钥未配置"
            
        # 使用和风天气API
        url = f"https://restapi.amap.com/v3/weather/weatherInfo"
        params = {
            "key": api_key,
            "city": city,
            "extensions": "base"  # base=实时天气, all=预报
        }
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get("status") == "1":
                lives = data.get("lives", [])
                if lives:
                    weather = lives[0]
                    return f"""🌡️ {city}天气：
当前温度：{weather.get("temperature")}°C
天气状况：{weather.get("weather")}
风力等级：{weather.get("windpower")}
风向：{weather.get("winddirection")}
湿度：{weather.get("humidity")}%
更新时间：{weather.get("reporttime")}"""
                else:
                    return f"未找到{city}的天气数据"
            else:
                return f"查询失败：{data.get('info', '未知错误')}"
        else:
            return f"天气查询失败，HTTP状态码：{response.status_code}"
            
    except Exception as e:
        logger.error("天气查询", f"查询 {city} 天气失败: {e}")
        return f"天气查询失败：{str(e)}"
