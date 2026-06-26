"""LLM客户端模块"""
import os
import time
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI
from openai._exceptions import RateLimitError
from core.config import config
from core.logger import logger


class LLMClient:
    """LLM客户端类"""
    
    def __init__(self):
        """初始化LLM客户端"""
        self.api_key = config.require("bot.api_key")
        self.base_url = config.require("bot.base_url")
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
    
    def call_llm(self, messages: List[Dict[str, str]], model_name: str = "Qwen/Qwen3.5-27B", 
                 stream: bool = False, temperature: float = 0.7) -> Any:
        """
        调用LLM模型
        
        Args:
            messages: 消息列表
            model_name: 模型名称
            stream: 是否流式输出
            temperature: 温度参数
            
        Returns:
            模型响应
        """
        try:
            response = self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                stream=stream,
                temperature=temperature,
                max_tokens=2048
            )
            return response
        except RateLimitError:
            logger.error("LLM", "请求频率过高，请稍后再试")
            time.sleep(1)
            return self.call_llm(messages, model_name, stream, temperature)
        except Exception as e:
            logger.error("LLM", f"调用失败: {e}")
            raise


# 全局LLM客户端实例
llm_client = None


def get_llm_client():
    """获取LLM客户端实例（延迟初始化）"""
    global llm_client
    if llm_client is None:
        llm_client = LLMClient()
    return llm_client


def call_llm(messages: List[Dict[str, str]], model_name: str = "Qwen/Qwen3.5-27B", 
             stream: bool = False, temperature: float = 0.7) -> Any:
    """调用LLM模型的便捷函数"""
    return get_llm_client().call_llm(messages, model_name, stream, temperature)


def get_llm_model(model_type: str) -> str:
    """根据模型类型获取模型名称"""
    if model_type == "planner":
        return config.get("llm.planner_model", "Qwen/Qwen3.5-27B")
    elif model_type == "executor":
        return config.get("llm.executor_model", "Qwen/Qwen3.5-27B")
    else:
        return "Qwen/Qwen3.5-27B"
