"""
L2 Provider 层：抽象类 BaseProvider，stream() 接口
"""
from abc import ABC, abstractmethod
from typing import Any, Iterator

class BaseProvider(ABC):
    @abstractmethod
    def stream(self, messages: list[dict], **kwargs) -> Iterator[str | dict[str, Any]]:
        """流式返回内容，每次 yield 一个字符串片段或状态事件。"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def model(self) -> str:
        ...
