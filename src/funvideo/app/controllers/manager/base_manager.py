import threading
from collections.abc import Callable
from typing import Any

from farlog import getLogger

logger = getLogger("funvideo")


class TaskManager:
    """管理后台任务的并发数量和等待队列。

    Args:
        max_concurrent_tasks: 同时执行任务的最大数量。
    """

    def __init__(self, max_concurrent_tasks: int) -> None:
        self.max_concurrent_tasks = max_concurrent_tasks
        self.current_tasks = 0
        self.lock = threading.Lock()
        self.queue = self.create_queue()

    def create_queue(self) -> Any:
        """创建任务队列。

        Returns:
            具体实现所使用的队列对象。
        """
        raise NotImplementedError()

    def add_task(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """立即执行或入队一个任务。

        Args:
            func: 待执行的可调用对象。
            *args: 传递给任务的位置参数。
            **kwargs: 传递给任务的关键字参数。
        """
        with self.lock:
            if self.current_tasks < self.max_concurrent_tasks:
                logger.info(
                    f"add task: {func.__name__}, current_tasks: {self.current_tasks}"
                )
                self.execute_task(func, *args, **kwargs)
            else:
                logger.info(
                    f"enqueue task: {func.__name__}, current_tasks: {self.current_tasks}"
                )
                self.enqueue({"func": func, "args": args, "kwargs": kwargs})

    def execute_task(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> None:
        """在线程中执行任务。

        Args:
            func: 待执行的可调用对象。
            *args: 传递给任务的位置参数。
            **kwargs: 传递给任务的关键字参数。
        """
        thread = threading.Thread(
            target=self.run_task, args=(func, *args), kwargs=kwargs
        )
        thread.start()

    def run_task(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """运行任务并在结束后调度下一个等待任务。

        Args:
            func: 待执行的可调用对象。
            *args: 传递给任务的位置参数。
            **kwargs: 传递给任务的关键字参数。
        """
        try:
            with self.lock:
                self.current_tasks += 1
            func(*args, **kwargs)  # 在这里调用函数，传递*args和**kwargs
        finally:
            self.task_done()

    def check_queue(self) -> None:
        """在有可用并发槽位时启动队首任务。"""
        with self.lock:
            if (
                self.current_tasks < self.max_concurrent_tasks
                and not self.is_queue_empty()
            ):
                task_info = self.dequeue()
                if task_info is None:
                    return
                func = task_info["func"]
                args = task_info.get("args", ())
                kwargs = task_info.get("kwargs", {})
                self.execute_task(func, *args, **kwargs)

    def task_done(self) -> None:
        """记录任务完成并检查是否可继续消费队列。"""
        with self.lock:
            self.current_tasks -= 1
        self.check_queue()

    def enqueue(self, task: dict[str, Any]) -> None:
        """将任务加入等待队列。

        Args:
            task: 包含函数和调用参数的任务描述。
        """
        raise NotImplementedError()

    def dequeue(self) -> dict[str, Any] | None:
        """取出一个等待任务。

        Returns:
            任务描述；队列为空时返回 ``None``。
        """
        raise NotImplementedError()

    def is_queue_empty(self) -> bool:
        """判断等待队列是否为空。

        Returns:
            队列为空时返回 ``True``。
        """
        raise NotImplementedError()
