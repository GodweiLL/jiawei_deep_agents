"""Protocol definition for pluggable memory backends.

定义所有后端必须实现的接口协议。
后端可以将文件存储在不同位置（状态、文件系统、数据库等），
并提供统一的文件操作接口。
"""

import abc
import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypeAlias

from langgraph.types import ToolRuntime
from typing_extensions import TypedDict

# 标准的文件操作错误码
FileOperationError = Literal[
    "file_not_found",  # 文件不存在
    "permission_denied",  # 权限不足
    "is_directory",  # 尝试下载目录作为文件
    "invalid_path",  # 路径语法错误
]

# 响应数据类 - FileDownloadResponse
