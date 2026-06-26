"""配置管理模块"""
import json
import os
from typing import Dict, Any


class Config:
    """配置管理类"""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.data = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """加载配置文件，必须存在且格式正确"""
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(
                f"配置文件 {self.config_file} 不存在，请创建后再启动。"
            )
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            raise ValueError(f"加载配置文件失败: {e}")

    def save_config(self):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            raise IOError(f"保存配置文件失败: {e}")

    def get(self, key: str, default=None):
        """获取配置值，支持点分隔的键"""
        keys = key.split('.')
        value = self.data
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def require(self, key: str):
        """获取必须存在的配置项，否则抛出异常"""
        value = self.get(key)
        if value is None:
            raise KeyError(f"配置项缺失: {key}")
        return value

    def set(self, key: str, value: Any):
        """设置配置值"""
        keys = key.split('.')
        data = self.data
        for k in keys[:-1]:
            if k not in data or not isinstance(data[k], dict):
                data[k] = {}
            data = data[k]
        data[keys[-1]] = value
        self.save_config()


# 全局配置实例
config = Config()
