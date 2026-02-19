# -*- coding: utf-8 -*-
"""
Power BI 缓存工具
实现简单的内存缓存机制，避免重复计算
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Callable


class SimpleCache:
    """简单的内存缓存"""
    
    def __init__(self, ttl: int = 900):
        """
        初始化缓存
        
        Args:
            ttl: 缓存过期时间（秒），默认 15 分钟
        """
        self.ttl = ttl
        self._cache: dict[str, tuple[Any, float]] = {}
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """生成缓存键"""
        # 将参数转换为字符串
        key_parts = [prefix]
        key_parts.extend(str(arg) for arg in args)
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        
        # 生成哈希
        key_str = ":".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Any | None:
        """获取缓存值"""
        if key not in self._cache:
            return None
        
        value, expire_time = self._cache[key]
        
        # 检查是否过期
        if time.time() > expire_time:
            del self._cache[key]
            return None
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """设置缓存值"""
        expire_time = time.time() + self.ttl
        self._cache[key] = (value, expire_time)
    
    def delete(self, key: str) -> None:
        """删除缓存值"""
        if key in self._cache:
            del self._cache[key]
    
    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()
    
    def cached(self, prefix: str):
        """缓存装饰器"""
        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                # 生成缓存键
                cache_key = self._generate_key(prefix, *args, **kwargs)
                
                # 尝试从缓存获取
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    return cached_value
                
                # 执行函数
                result = func(*args, **kwargs)
                
                # 存入缓存
                self.set(cache_key, result)
                
                return result
            
            return wrapper
        return decorator


# 全局缓存实例（15 分钟过期）
pbi_cache = SimpleCache(ttl=900)


def clear_pbi_cache():
    """清空 Power BI 缓存"""
    pbi_cache.clear()

