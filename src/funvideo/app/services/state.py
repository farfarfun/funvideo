import ast
from abc import ABC, abstractmethod
from typing import Any

from funvideo.app.config import config
from funvideo.app.models import const


# Base class for state management
class BaseState(ABC):
    """定义任务状态存储的统一接口。"""

    @abstractmethod
    def update_task(
        self, task_id: str, state: int, progress: int = 0, **kwargs: Any
    ) -> None:
        """更新任务的状态、进度和附加字段。

        Args:
            task_id: 任务唯一标识。
            state: 任务状态码。
            progress: 任务进度，范围为 0 至 100。
            **kwargs: 要一并保存的附加字段。
        """
        raise NotImplementedError

    @abstractmethod
    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """读取任务状态。

        Args:
            task_id: 任务唯一标识。

        Returns:
            任务状态字典；任务不存在时返回 ``None``。
        """
        raise NotImplementedError


# Memory state management
class MemoryState(BaseState):
    """将任务状态保存在当前进程内存中。"""

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}

    def update_task(
        self,
        task_id: str,
        state: int = const.TASK_STATE_PROCESSING,
        progress: int = 0,
        **kwargs: Any,
    ) -> None:
        """更新内存中的任务状态。"""
        progress = int(progress)
        if progress > 100:
            progress = 100

        self._tasks[task_id] = {
            "state": state,
            "progress": progress,
            **kwargs,
        }

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """获取内存中的任务状态。"""
        return self._tasks.get(task_id, None)

    def delete_task(self, task_id: str) -> None:
        """删除内存中的指定任务状态。"""
        if task_id in self._tasks:
            del self._tasks[task_id]


# Redis state management
class RedisState(BaseState):
    """将任务状态持久化到 Redis 哈希表。"""

    def __init__(
        self, host: str = "localhost", port: int = 6379, db: int = 0,
        password: str | None = None
    ) -> None:
        """连接 Redis 状态存储。

        Args:
            host: Redis 主机地址。
            port: Redis 端口。
            db: Redis 数据库编号。
            password: 可选的 Redis 密码。
        """
        import redis

        self._redis = redis.StrictRedis(host=host, port=port, db=db, password=password)

    def update_task(
        self,
        task_id: str,
        state: int = const.TASK_STATE_PROCESSING,
        progress: int = 0,
        **kwargs: Any,
    ) -> None:
        """更新 Redis 中的任务状态。"""
        progress = int(progress)
        if progress > 100:
            progress = 100

        fields = {
            "state": state,
            "progress": progress,
            **kwargs,
        }

        for field, value in fields.items():
            self._redis.hset(task_id, field, str(value))

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """获取 Redis 中的任务状态。"""
        task_data = self._redis.hgetall(task_id)
        if not task_data:
            return None

        task = {
            key.decode("utf-8"): self._convert_to_original_type(value)
            for key, value in task_data.items()
        }
        return task

    def delete_task(self, task_id: str) -> None:
        """删除 Redis 中的指定任务状态。"""
        self._redis.delete(task_id)

    @staticmethod
    def _convert_to_original_type(value: bytes) -> Any:
        """
        Convert the value from byte string to its original data type.
        You can extend this method to handle other data types as needed.
        """
        value_str = value.decode("utf-8")

        try:
            # try to convert byte string array to list
            return ast.literal_eval(value_str)
        except (ValueError, SyntaxError):
            pass

        if value_str.isdigit():
            return int(value_str)
        # Add more conversions here if needed
        return value_str


# Global state
_enable_redis = config.app.get("enable_redis", False)
_redis_host = config.app.get("redis_host", "localhost")
_redis_port = config.app.get("redis_port", 6379)
_redis_db = config.app.get("redis_db", 0)
_redis_password = config.get_secret("app", "redis_password")

state = (
    RedisState(
        host=_redis_host, port=_redis_port, db=_redis_db, password=_redis_password
    )
    if _enable_redis
    else MemoryState()
)
