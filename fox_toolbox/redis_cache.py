"""Redis 缓存模块（可选依赖，故障静默降级）"""

import asyncio
import json
from typing import Any, Optional, List, Dict

from astrbot.api import logger

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except Exception:  # pragma: no cover - 依赖未安装时的降级路径
    aioredis = None
    _REDIS_AVAILABLE = False

RECENT_MESSAGES_KEY = "fox_toolbox:recent_messages"
STATS_KEY = "fox_toolbox:stats"
RECENT_MESSAGES_CAP = 200


class RedisCache:
    """Redis 缓存封装。

    - 未启用 / 依赖未安装 / 连接失败时自动进入降级模式，所有操作变为 no-op。
    - 任何异常都不会抛出，保证插件主功能不受 Redis 故障影响。
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6379,
        password: Optional[str] = None,
        db: int = 0,
        ttl: int = 300,
    ) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._db = db
        self._ttl = ttl
        self._client: Optional[Any] = None
        self._available: bool = False
        self._checked: bool = False

    @property
    def available(self) -> bool:
        return self._available

    async def connect(self) -> bool:
        """建立连接并做连通性检测；失败则进入降级模式。"""
        if self._checked:
            return self._available
        self._checked = True
        if not _REDIS_AVAILABLE:
            logger.warning(
                "[FoxToolbox] 检测到启用 Redis 缓存，但未安装 redis 包，"
                "缓存功能已自动禁用（可执行 pip install redis 后重试）"
            )
            return False
        try:
            kwargs: Dict[str, Any] = {
                "host": self._host,
                "port": self._port,
                "db": self._db,
                "decode_responses": True,
            }
            if self._password:
                kwargs["password"] = self._password
            client = aioredis.from_url(
                f"redis://{self._host}:{self._port}/{self._db}",
                password=self._password or None,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            await asyncio.wait_for(client.ping(), timeout=3)
            self._client = client
            self._available = True
            logger.info(
                f"[FoxToolbox] Redis 缓存连接成功: "
                f"{self._host}:{self._port}/{self._db} (TTL={self._ttl}s)"
            )
            return True
        except Exception as e:
            self._available = False
            logger.warning(
                f"[FoxToolbox] Redis 缓存连接失败，已自动禁用缓存功能: {e}"
            )
            return False

    async def close(self) -> None:
        """关闭连接（幂等）。"""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception as e:
                logger.debug(f"[FoxToolbox] 关闭 Redis 连接失败: {e}")
            self._client = None
        self._available = False
        self._checked = True

    async def get_stats(self) -> Optional[dict]:
        """读取缓存的消息统计；未命中或降级时返回 None。"""
        if not self._available or self._client is None:
            return None
        try:
            raw = await self._client.get(STATS_KEY)
            if not raw:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.debug(f"[FoxToolbox] 读取统计缓存失败: {e}")
            return None

    async def set_stats(self, stats: dict) -> None:
        """写入消息统计缓存（带 TTL）。"""
        if not self._available or self._client is None:
            return
        try:
            await self._client.set(
                STATS_KEY, json.dumps(stats, ensure_ascii=False), ex=self._ttl
            )
        except Exception as e:
            logger.debug(f"[FoxToolbox] 写入统计缓存失败: {e}")

    async def push_recent_message(self, record: dict) -> None:
        """将新消息推入最近消息列表（保留最近 RECENT_MESSAGES_CAP 条）。"""
        if not self._available or self._client is None:
            return
        try:
            await self._client.lpush(
                RECENT_MESSAGES_KEY, json.dumps(record, ensure_ascii=False)
            )
            await self._client.ltrim(RECENT_MESSAGES_KEY, 0, RECENT_MESSAGES_CAP - 1)
        except Exception as e:
            logger.debug(f"[FoxToolbox] 写入最近消息缓存失败: {e}")

    async def get_recent_messages(self, limit: int = 50) -> List[dict]:
        """读取最近消息列表（按时间倒序）。"""
        if not self._available or self._client is None:
            return []
        try:
            raw_items = await self._client.lrange(RECENT_MESSAGES_KEY, 0, limit - 1)
            items: List[dict] = []
            for raw in raw_items or []:
                try:
                    items.append(json.loads(raw))
                except (json.JSONDecodeError, TypeError):
                    continue
            return items
        except Exception as e:
            logger.debug(f"[FoxToolbox] 读取最近消息缓存失败: {e}")
            return []
