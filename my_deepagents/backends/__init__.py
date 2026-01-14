"""Backends package - 后端系统，处理文件存储和操作"""

from my_deepagents.backends.filesystem import FilesystemBackend
from my_deepagents.backends.protocol import (
    BackendFactory,
    BackendProtocol,
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileOperationError,
    FileUploadResponse,
    GrepMatch,
    SandboxBackendProtocol,
    WriteResult,
)
from my_deepagents.backends.state import StateBackend

__all__ = [
    "BackendFactory",
    "BackendProtocol",
    "EditResult",
    "ExecuteResponse",
    "FileDownloadResponse",
    "FileInfo",
    "FileOperationError",
    "FilesystemBackend",
    "FileUploadResponse",
    "GrepMatch",
    "SandboxBackendProtocol",
    "StateBackend",
    "WriteResult",
]
