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
@dataclass
# @dataclass 装饰器自动生成 __init__ 方法, __repr__ 方法, __eq__ 方法, __hash__ 方法, __str__ 方法
class FileDownloadResponse:
    """文件下载响应"""
    path: str
    content: bytes | None = None
    error: FileOperationError | None = None

@dataclass
class FileUploadResponse:
    """文件上传响应"""
    path: str
    error: FileOperationError | None = None

class FileInfo(TypedDict):
    """文件信息结构"""
    path: str
    is_dir: NotRequired[bool]
    size: NotRequired[int]
    modified_at: NotRequired[str]

class GrepMatch(TypedDict):
    """grep 匹配结果"""
    path: str
    line: int
    text: str

    #   TypedDict vs dataclass 区别：
    #   | 特性      | TypedDict    | dataclass          |
    #   |-----------|--------------|--------------------|
    #   | 本质      | 字典 dict    | 类实例             |
    #   | 访问方式  | info["path"] | info.path          |
    #   | JSON 兼容 | 天然兼容     | 需要转换           |
    #   | 可选字段  | NotRequired  | field(default=...) |
    #   TypedDict 适合需要序列化/反序列化的数据结构。

@dataclass
class WriteResult:
    """写入结果"""
    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None # 状态更新字典(用于 StateBackend)

@dataclass
class EditResult:
    """编辑结果"""
    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None
    occurrences: int | None = None # 替换次数

class BackendProtocol(abc.ABC):
    f"""后端协议抽象基类

    所有后端实现都必须继承此类并实现相应方法。
    文件数据结构:
    {
        "content": list[str], # 行内容列表
        "created_at": str, # 创建时间(ISO格式)
        "modified_at": str, # 修改时间(ISO格式)
    }
    """

    def ls_info(self, path: str) -> list["FileInfo"]:
        """列出目录下的所有文件及元数据"""
        ...

    async def als_info(self, path: str) -> list["FileInfo"]:
        """异步版本 of ls_info 通过to_thread 包装同步版本"""
        return await asyncio.to_thread(self.ls_info, path)

    # abc.ABC 解释：
    # - ABC = Abstract Base Class（抽象基类）
    # - 子类必须实现标记为 @abstractmethod 的方法
    # - 这里没用 @abstractmethod，是因为采用了"鸭子类型"风格

    # 异步模式解释：
    # # asyncio.to_thread 将同步函数放到线程池执行
    # # 这样同步后端也能在异步环境中使用
    # async def als_info(self, path: str):
    #     return await asyncio.to_thread(self.ls_info, path)

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """读取文件内容,带行号
        
        Args:
            file_path: 文件路径
            offset: 起始行号
            limit: 最大读取行数

        Returns:
            带行号的文件内容,(cat -n 格式)
        """
        ...

    async def aread(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """异步版本 of read"""
        return await asyncio.to_thread(self.read, file_path, offset, limit)

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """搜索文件内容
        
            Args:
                pattern: 搜索的字符串（非正则）
                path: 搜索目录
                glob: 文件过滤模式，如 "*.py"
                
            Returns:
                成功返回 list[GrepMatch]，失败返回错误字符串
        """
        ...

    async def agrep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """异步版本 of grep_raw"""
        return await asyncio.to_thread(self.grep_raw, pattern, path, glob)

    def glob_info(
        self,
        pattern: str,
        path: str = "/",
    ) -> list[FileInfo]:
        """根据 glob 模式查找文件
        
        Args:
            pattern: glob 模式，如 "**/*.py"
            path: 基础目录，默认 "/"
            
        Returns:
            匹配的文件信息列表
        """
        ...

    async def aglob_info(
        self,
        pattern: str,
        path: str = "/",
    ) -> list[FileInfo]:
        """异步版本 of glob_info"""
        return await asyncio.to_thread(self.glob_info, pattern, path)

    def write(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        """写入新文件（文件已存在则报错）
        
        Args:
            file_path: 文件绝对路径
            content: 文件内容
            
        Returns:
            WriteResult
        """
        ...

    async def awrite(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        """异步版本 of write"""
        return await asyncio.to_thread(self.write, file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """精确字符串替换
        
        Args:
            file_path: 文件路径
            old_string: 要替换的字符串（必须精确匹配）
            new_string: 替换后的字符串
            replace_all: True=替换所有，False=只替换唯一匹配
            
        Returns:
            EditResult
        """
        ...

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """异步版本 of edit"""
        return await asyncio.to_thread(self.edit, file_path, old_string, new_string, replace_all)

    def upload_files(
        self,
        files: list[tuple[str, bytes]],
    ) -> list[FileUploadResponse]:
        """批量上传文件
        
        Args:
            files: [(路径, 内容), ...] 列表
            
        Returns:
            上传结果列表，顺序与输入一致
        """
        ...

    async def aupload_files(
        self,
        files: list[tuple[str, bytes]],
    ) -> list[FileUploadResponse]:
        """异步版本 of upload_files"""
        return await asyncio.to_thread(self.upload_files, files)

    def download_files(
        self,
        paths: list[str],
    ) -> list[FileDownloadResponse]:
        """批量下载文件
        
        Args:
            paths: 文件路径列表
            
        Returns:
            下载结果列表，顺序与输入一致
        """
        ...

    async def adownload_files(
        self,
        paths: list[str],
    ) -> list[FileDownloadResponse]:
        """异步版本 of download_files"""
        return await asyncio.to_thread(self.download_files, paths)

class ExecuteResponse:
    """执行命令响应"""
    output: str  #stdout 和 stderr 合并输出
    exit_code: int | None = None  # 进程退出码，0 表示成功，非 0 表示失败
    truncated: bool = False  # 是否被截断

class SandboxBackendProtocol(BackendProtocol):
    """沙盒后端协议 - 支持命令执行
    
    继承 BackendProtocol，额外提供 execute 能力。
    用于 Modal、Daytona 等远程沙盒环境。
    """
    def execute(
        self,
        command: str,
    ) -> ExecuteResponse:
        """执行 shell 命令
        
        Args:
            command: 完整的 shell 命令
            
        Returns:
            ExecuteResponse
        """
        ...

    async def aexecute(
        self,
        command: str,
    ) -> ExecuteResponse:
        """异步版本 of execute"""
        return await asyncio.to_thread(self.execute, command)

    def id(self) -> str:
        """沙盒实例的唯一标识符"""
        ...

# 后端工厂类型：接收 ToolRuntime，返回 BackendProtocol
BackendFactory = TypeAlias = Callable[[ToolRuntime], BackendProtocol]

# 后端类型的联合类型
BACKEND_TYPES = BackendProtocol | BackendFactory

# 为什么需要 BackendFactory？

# # 直接传入后端实例
# backend = StateBackend()
# create_deep_agent(backend=backend)

# # 或者传入工厂函数，延迟创建
# create_deep_agent(backend=lambda rt: StateBackend(rt))

# 工厂模式允许后端在运行时获取 ToolRuntime 上下文。