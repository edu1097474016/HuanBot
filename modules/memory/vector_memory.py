"""向量记忆系统模块"""
import os
import time
import threading
import uuid
from datetime import datetime

# 设置HF镜像源
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

# 延迟导入依赖
CHROMADB_AVAILABLE = False
chromadb = None
try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError as e:
    print(f"警告: ChromaDB 未安装 - {e}")
    chromadb = None

SENTENCE_TRANSFORMERS_AVAILABLE = False
SentenceTransformer = None
try:
    import importlib.util
    spec = importlib.util.find_spec("sentence_transformers")
    if spec is not None:
        from sentence_transformers import SentenceTransformer
        SENTENCE_TRANSFORMERS_AVAILABLE = True
except Exception as e:
    print(f"警告: SentenceTransformers 不可用 - {e}")

# 如果任一依赖不可用，整个记忆系统不可用
MEMORY_AVAILABLE = CHROMADB_AVAILABLE and SENTENCE_TRANSFORMERS_AVAILABLE


def get_time():
    """获取当前时间字符串"""
    return time.strftime("%Y-%m-%d %H:%M:%S")


class VectorMemory:
    """向量记忆系统类"""
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """单例模式，确保全局只有一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, collection_name="qq_memory", persist_dir="./chroma_db", 
                 model_name="all-MiniLM-L6-v2", max_memories=500):
        """
        初始化向量记忆系统
        
        Args:
            collection_name: 集合名称
            persist_dir: 持久化目录
            model_name: 嵌入模型名称
            max_memories: 最大记忆条数
        """
        # 避免重复初始化
        if hasattr(self, 'collection_name'):
            return
            
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        self.max_memories = max_memories
        self.model_name = model_name
        self.model = None
        self.collection = None
        self.client = None
        self.query_cache = {}  # 查询缓存
        
        if not MEMORY_AVAILABLE:
            print("[记忆系统] 依赖不可用，使用模拟模式")
            self.memories = []  # 简单列表存储
            return
            
        # 初始化ChromaDB客户端（不立即加载模型）
        print(f"[{get_time()}][记忆系统]正在初始化ChromaDB客户端")
        self.client = chromadb.PersistentClient(path=persist_dir)
        try:
            self.collection = self.client.get_collection(collection_name)
            print(f"[{get_time()}][记忆系统]已获取现有集合: {collection_name}")
        except:
            self.collection = self.client.create_collection(collection_name)
            print(f"[{get_time()}][记忆系统]已创建新集合: {collection_name}")
        
        # 定时清理
        self.cleanup_seconds = 300
        self.start_cleanup_thread()
        
        print(f"[{get_time()}][记忆系统]已启动向量记忆，模型={model_name}，最大条数={max_memories}")
    
    def _get_model(self):
        """延迟加载嵌入模型"""
        if self.model is None and SENTENCE_TRANSFORMERS_AVAILABLE:
            print(f"[{get_time()}][记忆系统]正在加载嵌入模型: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            print(f"[{get_time()}][记忆系统]嵌入模型加载完成")
        return self.model

    def add_memory(self, content):
        """添加记忆"""
        if not MEMORY_AVAILABLE:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memory_line = f"[{timestamp}]{content}"
            self.memories.append(memory_line)
            if len(self.memories) > self.max_memories:
                self.memories.pop(0)
            print(f"[{get_time()}][记忆]已添加: {memory_line}")
            return
            
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        memory_line = f"[{timestamp}]{content}"
        
        # 使用延迟加载的模型
        model = self._get_model()
        embedding = model.encode(memory_line).tolist()
        
        doc_id = str(uuid.uuid4())
        self.collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            metadatas=[{"timestamp": timestamp, "content": memory_line}],
            documents=[memory_line]
        )
        print(f"[{get_time()}][记忆]已添加: {memory_line}")

    def get_recent_memories(self, lines=10):
        """获取最近 lines 条记忆（按时间戳排序）"""
        if not MEMORY_AVAILABLE:
            return self.memories[-lines:] if self.memories else []
            
        all_memories = self.collection.get()
        if not all_memories['ids']:
            return []
        items = list(zip(all_memories['ids'], all_memories['metadatas']))
        items.sort(key=lambda x: x[1]['timestamp'], reverse=True)
        recent = items[:lines]
        return [meta['content'] for _, meta in recent]

    def get_all_memories(self):
        """获取所有记忆（按时间戳排序，最新在前）"""
        if not MEMORY_AVAILABLE:
            # 简单模式返回列表（已经是时间顺序）
            return list(reversed(self.memories)) if self.memories else []
        try:
            all_memories = self.collection.get()
            if not all_memories['ids']:
                return []
            items = list(zip(all_memories['ids'], all_memories['metadatas']))
            items.sort(key=lambda x: x[1]['timestamp'], reverse=True)
            return [meta['content'] for _, meta in items]
        except Exception as e:
            print(f"[记忆]获取所有记忆失败: {e}")
            return []

    def search_similar(self, query, top_k=5):
        """检索相似记忆"""
        if not MEMORY_AVAILABLE:
            # 简单文本匹配
            matches = [mem for mem in self.memories if query.lower() in mem.lower()]
            return matches[-top_k:] if matches else []
            
        # 检查缓存
        cache_key = f"{query}_{top_k}"
        if cache_key in self.query_cache:
            return self.query_cache[cache_key]
            
        # 使用延迟加载的模型
        model = self._get_model()
        query_embedding = model.encode(query).tolist()
        
        # 确保嵌入格式正确，处理可能的多维数组
        if isinstance(query_embedding[0], (list, tuple)):
            query_embedding = query_embedding[0]
            
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        if results['documents']:
            cached_results = results['documents'][0]
            # 缓存结果，限制缓存大小
            if len(self.query_cache) > 100:
                # 清空旧缓存
                self.query_cache.clear()
            self.query_cache[cache_key] = cached_results
            return cached_results
        return []

    def cleanup_old_memories(self):
        """清理超出最大条数的旧记忆"""
        if not MEMORY_AVAILABLE:
            return
            
        all = self.collection.get()
        if not all['ids']:
            return
        items = list(zip(all['ids'], all['metadatas']))
        items.sort(key=lambda x: x[1]['timestamp'])
        if len(items) > self.max_memories:
            to_delete = [id for id, _ in items[:-self.max_memories]]
            self.collection.delete(ids=to_delete)
            print(f"[{get_time()}][记忆清理]删除了{len(to_delete)}条旧记忆")

    def start_cleanup_thread(self):
        """启动定时清理线程"""
        if not MEMORY_AVAILABLE:
            return
            
        def cleanup_loop():
            while True:
                time.sleep(self.cleanup_seconds)
                self.cleanup_old_memories()
                
        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()
        print(f"[{get_time()}][记忆系统]启动清理线程，每{self.cleanup_seconds//60}分钟清理一次")
