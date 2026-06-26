import requests
import os
import time
import random
from typing import List
from core.config import config
from modules.tools.emoji_manager import get_emoji_manager

# 风景照片关键词列表
LANDSCAPE_KEYWORDS = [
    "自然风景", "山水风景", "海景", "山景", "日出日落", "星空", 
    "森林", "草原", "雪山", "瀑布", "湖泊", "河流", "沙滩", "峡谷"
]

# 免费图片API
IMAGE_APIS = [
    {
        "name": "pixabay",
        "url": "https://pixabay.com/api/",
        "params": {
            "key": "38778439-db184e8058d11a305e41d7308",
            "q": "",
            "image_type": "photo",
            "orientation": "horizontal",
            "per_page": 20
        }
    },
    {
        "name": "unsplash",
        "url": "https://api.unsplash.com/photos/random",
        "headers": {
            "Authorization": "Client-ID P7jM7D6zW1D7D7D7D7D7D7D7D7D7D7D7D7"
        },
        "params": {
            "query": "",
            "count": 10,
            "orientation": "landscape"
        }
    }
]

def crawl_landscape_photos(count: int = 5) -> List[str]:
    """
    爬取风景照片
    
    Args:
        count: 需要爬取的照片数量
    
    Returns:
        爬取到的照片文件路径列表
    """
    photos = []
    save_dir = config.get("album", {}).get("save_dir", "data/album")
    
    # 确保保存目录存在
    os.makedirs(save_dir, exist_ok=True)
    
    # 尝试使用免费图片API
    for api in IMAGE_APIS:
        if len(photos) >= count:
            break
            
        try:
            keyword = random.choice(LANDSCAPE_KEYWORDS)
            
            if api["name"] == "pixabay":
                api["params"]["q"] = keyword
                response = requests.get(api["url"], params=api["params"], timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    for hit in data.get("hits", []):
                        if len(photos) >= count:
                            break
                        image_url = hit.get("largeImageURL")
                        if image_url:
                            photo_path = download_image(image_url, save_dir)
                            if photo_path:
                                photos.append(photo_path)
            
            elif api["name"] == "unsplash":
                api["params"]["query"] = keyword
                response = requests.get(api["url"], headers=api["headers"], params=api["params"], timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    for photo in data:
                        if len(photos) >= count:
                            break
                        image_url = photo.get("urls", {}).get("regular")
                        if image_url:
                            photo_path = download_image(image_url, save_dir)
                            if photo_path:
                                photos.append(photo_path)
                                
        except Exception as e:
            print(f"爬取图片失败: {e}")
            continue
    
    # 如果爬取失败，使用表情包替代
    if not photos:
        photos = get_emoji_as_photos(count)
    
    return photos

def download_image(url: str, save_dir: str) -> str:
    """
    下载图片并保存到指定目录
    
    Args:
        url: 图片URL
        save_dir: 保存目录
    
    Returns:
        保存的文件路径，失败返回None
    """
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            # 获取文件扩展名
            ext = os.path.splitext(url)[1]
            if not ext:
                ext = ".jpg"
            
            # 生成文件名
            filename = f"photo_{int(time.time())}_{random.randint(1000, 9999)}{ext}"
            filepath = os.path.join(save_dir, filename)
            
            # 保存图片
            with open(filepath, "wb") as f:
                f.write(response.content)
            
            return filepath
    except Exception as e:
        print(f"下载图片失败: {e}")
    
    return None

def get_emoji_as_photos(count: int = 5) -> List[str]:
    """
    获取表情包作为替代照片
    
    Args:
        count: 需要的照片数量
    
    Returns:
        表情包文件路径列表
    """
    emoji_manager = get_emoji_manager()
    emojis = emoji_manager.get_all_emojis()
    
    # 如果没有表情包，返回空列表
    if not emojis:
        return []
    
    # 随机选择表情包
    selected_emojis = random.sample(emojis, min(count, len(emojis)))
    return selected_emojis

def update_album() -> List[str]:
    """
    更新相册，爬取新的风景照片
    
    Returns:
        更新后的照片路径列表
    """
    max_photos = config.get("album", {}).get("max_photos", 10)
    
    # 爬取新照片
    new_photos = crawl_landscape_photos(max_photos)
    
    # 清理旧照片（保留最新的max_photos张）
    save_dir = config.get("album", {}).get("save_dir", "data/album")
    if os.path.exists(save_dir):
        all_files = [f for f in os.listdir(save_dir) if f.startswith("photo_")]
        if len(all_files) > max_photos:
            # 按修改时间排序，删除旧的照片
            all_files.sort(key=lambda x: os.path.getmtime(os.path.join(save_dir, x)), reverse=True)
            for old_file in all_files[max_photos:]:
                try:
                    os.remove(os.path.join(save_dir, old_file))
                except Exception as e:
                    print(f"删除旧照片失败: {e}")
    
    return new_photos

def get_album_photos() -> List[str]:
    """
    获取相册中的所有照片
    
    Returns:
        照片文件路径列表
    """
    save_dir = config.get("album", {}).get("save_dir", "data/album")
    
    if not os.path.exists(save_dir):
        return []
    
    photos = []
    for file in os.listdir(save_dir):
        if file.startswith("photo_"):
            photos.append(os.path.join(save_dir, file))
    
    # 按修改时间排序（最新的在前）
    photos.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    
    return photos
