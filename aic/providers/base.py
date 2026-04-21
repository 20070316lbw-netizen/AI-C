"""
L2 Provider 层：抽象类 BaseProvider，stream() 接口
"""
from abc import ABC, abstractmethod
from typing import Iterator

class BaseProvider(ABC):
    @abstractmethod
    def stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
        """流式返回 token，每次 yield 一个字符串片段。"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def model(self) -> str:
        ...
