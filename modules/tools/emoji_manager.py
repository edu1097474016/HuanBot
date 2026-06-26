"""表情包管理模块"""
import os
import time
import threading
from PIL import Image, ImageFilter
import imagehash
from core.config import config
from core.logger import logger


class EmojiManager:
    """表情包管理器类"""
    
    def __init__(self):
        """初始化表情包管理器"""
        self.emoji_dir = config.require("emoji.dir")
        self.max_age_days = config.require("emoji.max_age_days")
        self.cleanup_interval = config.require("emoji.cleanup_interval_hours") * 3600
        self.similarity_threshold = config.require("emoji.similarity_threshold")
        self.hashes = {}  # 文件名 -> 哈希值
        self.load_existing_hashes()
        self.start_cleanup_timer()

    def load_existing_hashes(self):
        """加载现有表情包的哈希值"""
        if not os.path.exists(self.emoji_dir):
            os.makedirs(self.emoji_dir)
            return

        for filename in os.listdir(self.emoji_dir):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                filepath = os.path.join(self.emoji_dir, filename)
                try:
                    img_hash = self.get_image_hash(filepath)
                    if img_hash:
                        self.hashes[filename] = img_hash
                except Exception as e:
                    logger.error("表情包管理", f"加载哈希失败 {filename}: {e}")

    def get_image_hash(self, filepath: str) -> str:
        """获取图片的感知哈希值"""
        try:
            with Image.open(filepath) as img:
                # 转换为灰度图
                img = img.convert('L')
                # 调整大小为 8x8
                img = img.resize((8, 8), Image.Resampling.LANCZOS)
                # 计算平均值
                pixels = list(img.getdata())
                avg = sum(pixels) / len(pixels)
                # 生成哈希
                hash_str = ''.join('1' if p > avg else '0' for p in pixels)
                return hash_str
        except Exception as e:
            logger.error("表情包管理", f"计算哈希失败 {filepath}: {e}")
            return None

    def is_duplicate(self, filepath: str) -> bool:
        """检查图片是否重复"""
        img_hash = self.get_image_hash(filepath)
        if not img_hash:
            return False

        for existing_hash in self.hashes.values():
            if self.hamming_distance(img_hash, existing_hash) / 64 < (1 - self.similarity_threshold):
                return True
        return False

    def hamming_distance(self, hash1: str, hash2: str) -> int:
        """计算汉明距离"""
        return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))

    def add_emoji(self, filepath: str, filename: str = None) -> bool:
        """添加表情包，如果不重复则保存"""
        if self.is_duplicate(filepath):
            logger.info("表情包管理", f"跳过重复表情包: {filename or os.path.basename(filepath)}")
            return False

        if not filename:
            # 生成文件名
            timestamp = int(time.time())
            ext = os.path.splitext(filepath)[1].lower()
            filename = f"emoji_{timestamp}{ext}"

        dest_path = os.path.join(self.emoji_dir, filename)
        try:
            # 复制文件
            with open(filepath, 'rb') as src, open(dest_path, 'wb') as dst:
                dst.write(src.read())

            # 保存哈希
            img_hash = self.get_image_hash(dest_path)
            if img_hash:
                self.hashes[filename] = img_hash

            logger.info("表情包管理", f"添加表情包: {filename}")
            return True
        except Exception as e:
            logger.error("表情包管理", f"添加表情包失败: {e}")
            return False

    def cleanup_old_emojis(self):
        """清理旧的表情包"""
        if not os.path.exists(self.emoji_dir):
            return

        current_time = time.time()
        max_age = self.max_age_days * 24 * 3600

        removed_count = 0
        for filename in os.listdir(self.emoji_dir):
            filepath = os.path.join(self.emoji_dir, filename)
            if os.path.isfile(filepath):
                file_age = current_time - os.path.getmtime(filepath)
                if file_age > max_age:
                    try:
                        os.remove(filepath)
                        if filename in self.hashes:
                            del self.hashes[filename]
                        removed_count += 1
                        logger.info("表情包管理", f"清理旧表情包: {filename}")
                    except Exception as e:
                        logger.error("表情包管理", f"清理表情包失败 {filename}: {e}")

        if removed_count > 0:
            logger.info("表情包管理", f"清理完成，共删除 {removed_count} 个旧表情包")

    def start_cleanup_timer(self):
        """启动定时清理任务"""
        def cleanup_task():
            while True:
                self.cleanup_old_emojis()
                time.sleep(self.cleanup_interval)

        thread = threading.Thread(target=cleanup_task, daemon=True)
        thread.start()
        logger.info("表情包管理", f"启动定时清理任务，间隔 {self.cleanup_interval / 3600} 小时")

    def get_recent_emojis(self, max_count: int = 10) -> list:
        """获取最近的表情包列表（返回完整路径）"""
        if not os.path.exists(self.emoji_dir):
            return []

        files = []
        for filename in os.listdir(self.emoji_dir):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                filepath = os.path.join(self.emoji_dir, filename)
                mtime = os.path.getmtime(filepath)
                files.append((filepath, mtime))

        # 按修改时间排序
        files.sort(key=lambda x: x[1], reverse=True)
        return [f[0] for f in files[:max_count]]

    def get_all_emojis(self) -> list:
        """获取所有表情包的完整路径列表"""
        if not os.path.exists(self.emoji_dir):
            return []

        all_emojis = []
        for filename in os.listdir(self.emoji_dir):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                filepath = os.path.join(self.emoji_dir, filename)
                all_emojis.append(filepath)
        
        return all_emojis

    def search_similar_emojis(self, query_filepath: str, max_results: int = 5) -> list:
        """搜索相似表情包"""
        query_hash = self.get_image_hash(query_filepath)
        if not query_hash:
            return []

        similarities = []
        for filename, hash_val in self.hashes.items():
            distance = self.hamming_distance(query_hash, hash_val)
            similarity = 1 - (distance / 64)
            if similarity >= self.similarity_threshold:
                similarities.append((filename, similarity))

        similarities.sort(key=lambda x: x[1], reverse=True)
        return [f[0] for f in similarities[:max_results]]


# 全局实例
emoji_manager = None


def get_emoji_manager():
    """获取表情包管理器实例（延迟初始化）"""
    global emoji_manager
    if emoji_manager is None:
        emoji_manager = EmojiManager()
    return emoji_manager
