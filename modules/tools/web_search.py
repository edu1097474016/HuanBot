"""网络搜索和网页内容提取模块"""
import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from core.logger import logger
from core.config import config

def search_web(query: str, max_results: int = 5) -> list:
    """
    使用搜索引擎查询信息
    
    Args:
        query: 搜索关键词
        max_results: 返回结果数量
        
    Returns:
        搜索结果列表，每个结果包含标题、描述和URL
    """
    try:
        # 尝试使用Bing搜索API
        bing_api_key = config.get("bing", {}).get("api_key")
        
        if bing_api_key:
            url = "https://api.bing.microsoft.com/v7.0/search"
            headers = {
                "Ocp-Apim-Subscription-Key": bing_api_key
            }
            params = {
                "q": query,
                "count": max_results,
                "mkt": "zh-CN"
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                for item in data.get("webPages", {}).get("value", []):
                    results.append({
                        "title": item.get("name", ""),
                        "description": item.get("snippet", ""),
                        "url": item.get("url", "")
                    })
                
                return results
            else:
                logger.error("网络搜索", f"Bing API搜索失败，HTTP状态码：{response.status_code}")
                return []
        else:
            # 没有配置Bing API，返回提示信息
            return [{"title": "提示", "description": "搜索功能需要配置Bing API密钥", "url": ""}]
            
    except Exception as e:
        logger.error("网络搜索", f"搜索 {query} 失败: {e}")
        return [{"title": "搜索失败", "description": str(e), "url": ""}]

def extract_content_from_url(url: str) -> str:
    """
    从URL提取网页内容
    
    Args:
        url: 网页URL
        
    Returns:
        提取的文本内容
    """
    try:
        # 安全检查
        if not is_safe_url(url):
            return "该链接存在安全风险，无法访问"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 移除脚本和样式
            for script in soup(["script", "style"]):
                script.decompose()
            
            # 获取标题
            title = soup.title.string if soup.title else "无标题"
            
            # 获取主要内容
            content = soup.get_text(separator='\n')
            
            # 清理文本
            content = re.sub(r'\n+', '\n', content).strip()
            
            # 限制内容长度
            if len(content) > 2000:
                content = content[:2000] + "..."
            
            return f"网页标题：{title}\n\n网页内容：\n{content}"
        else:
            return f"访问失败，HTTP状态码：{response.status_code}"
            
    except Exception as e:
        logger.error("内容提取", f"提取 {url} 内容失败: {e}")
        return f"内容提取失败：{str(e)}"

def is_safe_url(url: str) -> bool:
    """
    安全审查URL
    
    Args:
        url: 要检查的URL
        
    Returns:
        是否安全
    """
    try:
        parsed = urlparse(url)
        
        # 检查协议
        if parsed.scheme not in ["http", "https"]:
            return False
        
        # 检查域名
        domain = parsed.netloc.lower()
        
        # 黑名单域名
        blacklist = [
            "malware.com",
            "phishing.com",
            "virus.com",
            "scam.com"
        ]
        
        for bad_domain in blacklist:
            if bad_domain in domain:
                return False
        
        # 检查端口
        if parsed.port and parsed.port not in [80, 443]:
            return False
        
        return True
        
    except Exception as e:
        logger.error("安全审查", f"URL安全检查失败: {e}")
        return False

def web_query(query: str) -> str:
    """
    URL内容提取函数
    
    Args:
        query: URL链接
        
    Returns:
        提取的网页内容
    """
    # 检测是否包含URL
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, query)
    
    if urls:
        # 如果包含多个URL，只处理第一个
        url = urls[0]
        logger.info("网络查询", f"检测到URL: {url}，开始提取内容")
        
        # 提取网页内容
        content = extract_content_from_url(url)
        return content
    else:
        # 如果不是URL，返回提示信息
        return "未检测到有效的URL链接，请提供完整的网页链接（如 https://example.com）"
