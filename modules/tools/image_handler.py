"""图像处理模块"""
import os
import requests
import time
import base64
from PIL import Image
import io
from urllib.parse import quote
from core.logger import logger
from modules.tools.emoji_manager import get_emoji_manager

# 关闭 HuggingFace symlink 提示
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')

EMOJI_DIR = "data/emoji"
os.makedirs(EMOJI_DIR, exist_ok=True)

# ==================== 魔搭 API 配置 ====================
API_KEY = "ms-bd2eddb6-5afd-45f0-a5ca-77d922a7cfa4"
# 使用分类模型（已部署，可直接调用）
CLASSIFY_MODEL = "iic/cv_resnet50_image-classification"

# 开关：是否启用视觉识别（设为 True 启用分类模型）
ENABLE_VISION_API = False  # 视觉识别功能依赖外部API，默认关闭以避免不必要的调用和潜在错误
ENABLE_LOCAL_CLIP = False   # 本地 CLIP 需手动下载模型，暂关闭


def download_image(url, user_name=None):
    """下载图片到本地，返回保存的路径，失败返回 None"""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        content_type = resp.headers.get('content-type', '')
        if 'image' not in content_type:
            logger.warning("图片下载", f"不是图片内容类型: {content_type}")
            return None
        # 确定扩展名
        if 'jpeg' in content_type or 'jpg' in content_type:
            ext = 'jpg'
        elif 'png' in content_type:
            ext = 'png'
        elif 'gif' in content_type:
            ext = 'gif'
        else:
            ext = 'jpg'
        timestamp = int(time.time())
        user_part = user_name if user_name else "unknown"
        filename = f"{user_part}_{timestamp}.{ext}"
        filepath = os.path.join(EMOJI_DIR, filename)
        with open(filepath, 'wb') as f:
            f.write(resp.content)
        logger.info("图片下载", f"图片已保存: {filepath} (大小: {len(resp.content)} bytes)")
        return filepath
    except Exception as e:
        logger.error("图片下载", f"下载异常: {e}")
        return None


def encode_image_to_base64(image_path):
    """将图片文件编码为 base64 data URL"""
    try:
        with open(image_path, "rb") as f:
            img_data = f.read()
            b64 = base64.b64encode(img_data).decode('utf-8')
            # 根据扩展名确定 MIME 类型
            ext = os.path.splitext(image_path)[1].lower()
            if ext == '.png':
                mime = "image/png"
            elif ext == '.gif':
                mime = "image/gif"
            else:
                mime = "image/jpeg"
            return f"data:{mime};base64,{b64}"
    except Exception as e:
        logger.error("图片编码", f"base64编码失败: {e}")
        return None


def send_image_via_cq(file_path):
    """
    生成发送图片的CQ码。
    确保路径使用正斜杠，对中文等特殊字符进行URL编码但保留斜杠。
    如果文件不存在，返回错误文本。
    """
    try:
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logger.error("CQ码生成", f"图片文件不存在: {file_path}")
            return f"[图片不存在: {os.path.basename(file_path)}]"

        # 规范化路径：将反斜杠转为正斜杠
        normalized_path = file_path.replace('\\', '/')
        # 获取相对路径（相对于 NapCat 工作目录，通常是项目根目录）
        rel_path = os.path.relpath(normalized_path)
        # 对路径进行URL编码，但保留正斜杠（safe='/')
        encoded_path = quote(rel_path, safe='/')
        cq_code = f"[CQ:image,file={encoded_path}]"
        logger.debug("CQ码生成", f"生成CQ码: {cq_code}")
        return cq_code
    except Exception as e:
        logger.error("CQ码生成", f"生成CQ码失败: {e}")
        return f"[图片发送失败: {os.path.basename(file_path)}]"


def get_image_caption(image_url):
    """获取图片描述：下载图片 -> 转base64 -> 调用分类API -> 返回描述文本"""
    if not image_url:
        return ""

    # 1. 下载图片到本地
    filepath = download_image(image_url)
    if not filepath:
        logger.error("视觉识别", "下载图片失败，无法识别")
        return "图片内容（下载失败）"

    # 2. 转为 base64 data URL
    data_url = encode_image_to_base64(filepath)
    if not data_url:
        logger.error("视觉识别", "图片转base64失败")
        return "图片内容（编码失败）"

    # 3. 调用分类模型 API
    if ENABLE_VISION_API:
        caption = call_classify_api(data_url)
        if caption:
            return caption
        else:
            logger.warning("视觉识别", "分类API识别失败，使用默认描述")
            return "图片内容（分类失败）"
    else:
        return "图片内容（视觉识别已禁用）"


def call_classify_api(data_url):
    """调用魔搭图像分类 API"""
    try:
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": data_url,
            "model": CLASSIFY_MODEL
        }
        url = "https://api-inference.modelscope.cn/v1/inference"
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            # 尝试提取分类结果
            labels = data.get("output", {}).get("labels", [])
            if not labels:
                labels = data.get("result", {}).get("labels", [])
            if not labels and "output" in data:
                if isinstance(data["output"], list) and len(data["output"]) > 0:
                    labels = data["output"]
            if labels:
                best = labels[0].get("label") or labels[0].get("class") or str(labels[0])
                return f"图片内容可能是：{best}"
            else:
                logger.warning("视觉识别", f"API返回无分类结果: {data}")
                return "图片内容无法识别"
        else:
            logger.error("视觉识别", f"分类API返回{response.status_code}: {response.text}")
            return ""
    except Exception as e:
        logger.error("视觉识别", f"分类API调用失败: {e}")
        return ""


def send_image_base64(file_path):
    """将图片转为base64并生成CQ码"""
    try:
        with open(file_path, 'rb') as f:
            img_data = base64.b64encode(f.read()).decode('utf-8')
        return f"[CQ:image,file=base64://{img_data}]"
    except Exception as e:
        logger.error("图片base64", f"转换失败: {e}")
        return f"[图片发送失败: {os.path.basename(file_path)}]"
