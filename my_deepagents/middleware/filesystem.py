"""为 Agent 提供文件系统工具的中间件"""

import os
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, Literal, NotRequired

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langchain.tools import ToolRuntime
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import Command
from typing_extensions import TypedDict

from my_deepagents.backends import StateBackend
from my_deepagents.backends.protocol import (
    BACKEND_TYPES,
    BackendProtocol,
    EditResult,
    SandboxBackendProtocol,
    WriteResult,
)
from my_deepagents.backends.utils import (
    format_content_with_line_numbers,
    format_grep_matches,
    sanitize_tool_call_id,
    truncate_if_too_long,
)

# 常量定义
EMPTY_CONTENT_WARNING = "System reminder: File exists but has empty contents"
MAX_LINE_LENGTH = 2000
LINE_NUMBER_WIDTH = 6
DEFAULT_READ_OFFSET = 0
DEFAULT_READ_LIMIT = 500

class FileData(TypedDict):
    """文件数据结构"""
    content:list[str]
    created_at:str
    modified_at:str

def _file_data_reducer(
    left: dict[str, FileData] | None,
    right: dict[str, FileData | None]
) -> dict[str, FileData]:
    """文件状态 Reducer - 支持合并和删除
    
    right中的None值表示删除该文件"""
    # 初始化情况:过滤掉 None 值
    if left is None:
        return {k: v for k, v in right.items() if v is not None}

    # 合并情况
    result = {**left}
    for key, value in right.items():
        if value is None:
            # None 值表示删除
            result.pop(key, None)
        else:
            # 非 None 值表示更新
            result[key] = value
    return result


class FilesystemState(AgentState):
    """文件系统中间件的状态 - 扩展 AgentState"""
    files: Annotated[NotRequired[dict[str, FileData]], _file_data_reducer]


# ============================================================
# 路径验证函数
# ============================================================

def _validate_path(path: str, *, allowed_prefixes: Sequence[str] | None = None) -> str:
    """验证并规范化文件路径，防止路径穿越攻击"""
    if ".." in path or path.startswith("~"):
        msg = f"Path traversal not allowed: {path}"
        raise ValueError(msg)

    # 拒绝 Windows 绝对路径
    if re.match(r"^[a-zA-Z]:", path):
        msg = f"Windows absolute paths are not supported: {path}"
        raise ValueError(msg)

    normalized = os.path.normpath(path)
    normalized = normalized.replace("\\", "/")

    if not normalized.startswith("/"):
        normalized = f"/{normalized}"

    if allowed_prefixes is not None and not any(normalized.startswith(prefix) for prefix in allowed_prefixes):
        msg = f"Path must start with one of {allowed_prefixes}: {path}"
        raise ValueError(msg)

    return normalized


# ============================================================
# 工具描述常量
# ============================================================

LIST_FILES_TOOL_DESCRIPTION = """Lists all files in the filesystem, filtering by directory.

Usage:
- The path parameter must be an absolute path, not a relative path
- The list_files tool will return a list of all files in the specified directory.
- This is very useful for exploring the file system and finding the right file to read or edit.
- You should almost ALWAYS use this tool before using the Read or Edit tools."""

READ_FILE_TOOL_DESCRIPTION = """Reads a file from the filesystem.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- By default, it reads up to 500 lines starting from the beginning of the file
- Use pagination with offset and limit parameters to avoid context overflow
- Results are returned using cat -n format, with line numbers starting at 1"""

EDIT_FILE_TOOL_DESCRIPTION = """Performs exact string replacements in files.

Usage:
- You must use your Read tool at least once before editing
- The edit will FAIL if old_string is not unique in the file
- Use replace_all for replacing all occurrences"""

WRITE_FILE_TOOL_DESCRIPTION = """Writes to a new file in the filesystem.

Usage:
- The file_path parameter must be an absolute path
- Prefer to edit existing files over creating new ones when possible."""

GLOB_TOOL_DESCRIPTION = """Find files matching a glob pattern.

Examples:
- **/*.py - Find all Python files
- *.txt - Find all text files in root"""

GREP_TOOL_DESCRIPTION = """Search for a pattern in files.

Usage:
- The pattern parameter is the text to search for (literal string, not regex)
- The output_mode parameter controls the output format:
  - files_with_matches: List only file paths containing matches (default)
  - content: Show matching lines with file path and line numbers
  - count: Show count of matches per file"""

EXECUTE_TOOL_DESCRIPTION = """Executes a given command in the sandbox environment.

Note: This tool is only available if the backend supports execution (SandboxBackendProtocol)."""

FILESYSTEM_SYSTEM_PROMPT = """## Filesystem Tools

You have access to a filesystem which you can interact with using these tools.
All file paths must start with a /.

- ls: list files in a directory
- read_file: read a file from the filesystem
- write_file: write to a file in the filesystem
- edit_file: edit a file in the filesystem
- glob: find files matching a pattern
- grep: search for text within files"""

EXECUTION_SYSTEM_PROMPT = """## Execute Tool

You have access to an execute tool for running shell commands in a sandboxed environment."""


# ============================================================
# 辅助函数
# ============================================================

def _get_backend(backend: BACKEND_TYPES, runtime: ToolRuntime) -> BackendProtocol:
    """获取后端实例（支持工厂函数）"""
    if callable(backend):
        return backend(runtime)
    return backend


# ============================================================
# 工具生成器函数
# ============================================================

def _ls_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
    custom_description: str | None = None,
) -> BaseTool:
    """生成 ls 工具"""
    tool_description = custom_description or LIST_FILES_TOOL_DESCRIPTION

    def sync_ls(runtime: ToolRuntime[None, FilesystemState], path: str) -> str:
        resolved_backend = _get_backend(backend, runtime)
        validated_path = _validate_path(path)
        infos = resolved_backend.ls_info(validated_path)
        paths = [fi.get("path", "") for fi in infos]
        result = truncate_if_too_long(paths)
        return str(result)

    async def async_ls(runtime: ToolRuntime[None, FilesystemState], path: str) -> str:
        resolved_backend = _get_backend(backend, runtime)
        validated_path = _validate_path(path)
        infos = await resolved_backend.als_info(validated_path)
        paths = [fi.get("path", "") for fi in infos]
        result = truncate_if_too_long(paths)
        return str(result)

    return StructuredTool.from_function(
        name="ls",
        description=tool_description,
        func=sync_ls,
        coroutine=async_ls,
    )


def _read_file_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
    custom_description: str | None = None,
) -> BaseTool:
    """生成 read_file 工具"""
    tool_description = custom_description or READ_FILE_TOOL_DESCRIPTION

    def sync_read_file(
        file_path: str,
        runtime: ToolRuntime[None, FilesystemState],
        offset: int = DEFAULT_READ_OFFSET,
        limit: int = DEFAULT_READ_LIMIT,
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        return resolved_backend.read(file_path, offset=offset, limit=limit)

    async def async_read_file(
        file_path: str,
        runtime: ToolRuntime[None, FilesystemState],
        offset: int = DEFAULT_READ_OFFSET,
        limit: int = DEFAULT_READ_LIMIT,
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        return await resolved_backend.aread(file_path, offset=offset, limit=limit)

    return StructuredTool.from_function(
        name="read_file",
        description=tool_description,
        func=sync_read_file,
        coroutine=async_read_file,
    )


def _write_file_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
    custom_description: str | None = None,
) -> BaseTool:
    """生成 write_file 工具"""
    tool_description = custom_description or WRITE_FILE_TOOL_DESCRIPTION

    def sync_write_file(
        file_path: str,
        content: str,
        runtime: ToolRuntime[None, FilesystemState],
    ) -> Command | str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        res: WriteResult = resolved_backend.write(file_path, content)
        if res.error:
            return res.error
        if res.files_update is not None:
            return Command(
                update={
                    "files": res.files_update,
                    "messages": [
                        ToolMessage(
                            content=f"Updated file {res.path}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        return f"Updated file {res.path}"

    async def async_write_file(
        file_path: str,
        content: str,
        runtime: ToolRuntime[None, FilesystemState],
    ) -> Command | str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        res: WriteResult = await resolved_backend.awrite(file_path, content)
        if res.error:
            return res.error
        if res.files_update is not None:
            return Command(
                update={
                    "files": res.files_update,
                    "messages": [
                        ToolMessage(
                            content=f"Updated file {res.path}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        return f"Updated file {res.path}"

    return StructuredTool.from_function(
        name="write_file",
        description=tool_description,
        func=sync_write_file,
        coroutine=async_write_file,
    )


def _edit_file_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
    custom_description: str | None = None,
) -> BaseTool:
    """生成 edit_file 工具"""
    tool_description = custom_description or EDIT_FILE_TOOL_DESCRIPTION

    def sync_edit_file(
        file_path: str,
        old_string: str,
        new_string: str,
        runtime: ToolRuntime[None, FilesystemState],
        *,
        replace_all: bool = False,
    ) -> Command | str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        res: EditResult = resolved_backend.edit(file_path, old_string, new_string, replace_all=replace_all)
        if res.error:
            return res.error
        if res.files_update is not None:
            return Command(
                update={
                    "files": res.files_update,
                    "messages": [
                        ToolMessage(
                            content=f"Successfully replaced {res.occurrences} instance(s) in '{res.path}'",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        return f"Successfully replaced {res.occurrences} instance(s) in '{res.path}'"

    async def async_edit_file(
        file_path: str,
        old_string: str,
        new_string: str,
        runtime: ToolRuntime[None, FilesystemState],
        *,
        replace_all: bool = False,
    ) -> Command | str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        res: EditResult = await resolved_backend.aedit(file_path, old_string, new_string, replace_all=replace_all)
        if res.error:
            return res.error
        if res.files_update is not None:
            return Command(
                update={
                    "files": res.files_update,
                    "messages": [
                        ToolMessage(
                            content=f"Successfully replaced {res.occurrences} instance(s) in '{res.path}'",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        return f"Successfully replaced {res.occurrences} instance(s) in '{res.path}'"

    return StructuredTool.from_function(
        name="edit_file",
        description=tool_description,
        func=sync_edit_file,
        coroutine=async_edit_file,
    )


def _glob_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
    custom_description: str | None = None,
) -> BaseTool:
    """生成 glob 工具"""
    tool_description = custom_description or GLOB_TOOL_DESCRIPTION

    def sync_glob(pattern: str, runtime: ToolRuntime[None, FilesystemState], path: str = "/") -> str:
        resolved_backend = _get_backend(backend, runtime)
        infos = resolved_backend.glob_info(pattern, path=path)
        paths = [fi.get("path", "") for fi in infos]
        result = truncate_if_too_long(paths)
        return str(result)

    async def async_glob(pattern: str, runtime: ToolRuntime[None, FilesystemState], path: str = "/") -> str:
        resolved_backend = _get_backend(backend, runtime)
        infos = await resolved_backend.aglob_info(pattern, path=path)
        paths = [fi.get("path", "") for fi in infos]
        result = truncate_if_too_long(paths)
        return str(result)

    return StructuredTool.from_function(
        name="glob",
        description=tool_description,
        func=sync_glob,
        coroutine=async_glob,
    )


def _grep_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
    custom_description: str | None = None,
) -> BaseTool:
    """生成 grep 工具"""
    tool_description = custom_description or GREP_TOOL_DESCRIPTION

    def sync_grep(
        pattern: str,
        runtime: ToolRuntime[None, FilesystemState],
        path: str | None = None,
        glob: str | None = None,
        output_mode: Literal["files_with_matches", "content", "count"] = "files_with_matches",
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        raw = resolved_backend.grep_raw(pattern, path=path, glob=glob)
        if isinstance(raw, str):
            return raw
        formatted = format_grep_matches(raw, output_mode)
        return truncate_if_too_long(formatted)

    async def async_grep(
        pattern: str,
        runtime: ToolRuntime[None, FilesystemState],
        path: str | None = None,
        glob: str | None = None,
        output_mode: Literal["files_with_matches", "content", "count"] = "files_with_matches",
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        raw = await resolved_backend.agrep_raw(pattern, path=path, glob=glob)
        if isinstance(raw, str):
            return raw
        formatted = format_grep_matches(raw, output_mode)
        return truncate_if_too_long(formatted)

    return StructuredTool.from_function(
        name="grep",
        description=tool_description,
        func=sync_grep,
        coroutine=async_grep,
    )


def _supports_execution(backend: BackendProtocol) -> bool:
    """检查后端是否支持命令执行"""
    return isinstance(backend, SandboxBackendProtocol)


def _execute_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
    custom_description: str | None = None,
) -> BaseTool:
    """生成 execute 工具"""
    tool_description = custom_description or EXECUTE_TOOL_DESCRIPTION

    def sync_execute(command: str, runtime: ToolRuntime[None, FilesystemState]) -> str:
        resolved_backend = _get_backend(backend, runtime)
        if not _supports_execution(resolved_backend):
            return "Error: Execution not available. Backend does not support SandboxBackendProtocol."
        try:
            result = resolved_backend.execute(command)
        except NotImplementedError as e:
            return f"Error: Execution not available. {e}"
        parts = [result.output]
        if result.exit_code is not None:
            status = "succeeded" if result.exit_code == 0 else "failed"
            parts.append(f"\n[Command {status} with exit code {result.exit_code}]")
        if result.truncated:
            parts.append("\n[Output was truncated due to size limits]")
        return "".join(parts)

    async def async_execute(command: str, runtime: ToolRuntime[None, FilesystemState]) -> str:
        resolved_backend = _get_backend(backend, runtime)
        if not _supports_execution(resolved_backend):
            return "Error: Execution not available. Backend does not support SandboxBackendProtocol."
        try:
            result = await resolved_backend.aexecute(command)
        except NotImplementedError as e:
            return f"Error: Execution not available. {e}"
        parts = [result.output]
        if result.exit_code is not None:
            status = "succeeded" if result.exit_code == 0 else "failed"
            parts.append(f"\n[Command {status} with exit code {result.exit_code}]")
        if result.truncated:
            parts.append("\n[Output was truncated due to size limits]")
        return "".join(parts)

    return StructuredTool.from_function(
        name="execute",
        description=tool_description,
        func=sync_execute,
        coroutine=async_execute,
    )


# 工具生成器映射
TOOL_GENERATORS = {
    "ls": _ls_tool_generator,
    "read_file": _read_file_tool_generator,
    "write_file": _write_file_tool_generator,
    "edit_file": _edit_file_tool_generator,
    "glob": _glob_tool_generator,
    "grep": _grep_tool_generator,
    "execute": _execute_tool_generator,
}


def _get_filesystem_tools(
    backend: BackendProtocol,
    custom_tool_descriptions: dict[str, str] | None = None,
) -> list[BaseTool]:
    """获取所有文件系统工具"""
    if custom_tool_descriptions is None:
        custom_tool_descriptions = {}
    tools = []
    for tool_name, tool_generator in TOOL_GENERATORS.items():
        tool = tool_generator(backend, custom_tool_descriptions.get(tool_name))
        tools.append(tool)
    return tools


# 大结果提示模板
TOO_LARGE_TOOL_MSG = """Tool result too large, saved at: {file_path}
Use read_file with offset and limit to read parts of it.

First 10 lines:
{content_sample}
"""


# ============================================================
# FilesystemMiddleware 类
# ============================================================

class FilesystemMiddleware(AgentMiddleware):
    """文件系统中间件 - 为 Agent 提供文件操作工具

    提供的工具: ls, read_file, write_file, edit_file, glob, grep
    如果后端支持 SandboxBackendProtocol，还会提供 execute 工具
    """

    state_schema = FilesystemState

    def __init__(
        self,
        *,
        backend: BACKEND_TYPES | None = None,
        system_prompt: str | None = None,
        custom_tool_descriptions: dict[str, str] | None = None,
        tool_token_limit_before_evict: int | None = 20000,
    ) -> None:
        self.tool_token_limit_before_evict = tool_token_limit_before_evict
        self.backend = backend if backend is not None else (lambda rt: StateBackend(rt))
        self._custom_system_prompt = system_prompt
        self.tools = _get_filesystem_tools(self.backend, custom_tool_descriptions)

    def _get_backend(self, runtime: ToolRuntime) -> BackendProtocol:
        if callable(self.backend):
            return self.backend(runtime)
        return self.backend

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """在 LLM 调用前注入系统提示，并根据后端能力过滤工具"""
        has_execute_tool = any(
            (tool.name if hasattr(tool, "name") else tool.get("name")) == "execute"
            for tool in request.tools
        )

        backend_supports_execution = False
        if has_execute_tool:
            backend = self._get_backend(request.runtime)
            backend_supports_execution = _supports_execution(backend)

            # 如果后端不支持执行,则过滤掉execute工具
            if not backend_supports_execution:
                filtered_tools = [
                    tool for tool in request.tools 
                    if (tool.name if hasattr(tool, "name") else tool.get("name")) != "execute"
                ]
                request = request.override(tools=filtered_tools)
                has_execute_tool = False

        # 构建系统提示
        if self._custom_system_prompt is not None:
            system_prompt = self._custom_system_prompt
        else:   
            prompt_parts = [FILESYSTEM_SYSTEM_PROMPT]

            # 如果后端支持执行,则添加执行工具说明
            if has_execute_tool and backend_supports_execution:
                prompt_parts.append(EXECUTION_SYSTEM_PROMPT)

            system_prompt = "\n\n".join(prompt_parts)

        # 注入系统提示
        if system_prompt:
            new_prompt = (
                request.system_prompt + "\n\n" + system_prompt 
                if request.system_prompt 
                else system_prompt
            )
            request = request.override(system_prompt=new_prompt)

        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """异步版本 - 逻辑与同步版本相同"""
        has_execute_tool = any(
            (tool.name if hasattr(tool, "name") else tool.get("name")) == "execute"
            for tool in request.tools
        )

        backend_supports_execution = False
        if has_execute_tool:
            backend = self._get_backend(request.runtime)
            backend_supports_execution = _supports_execution(backend)

            if not backend_supports_execution:
                filtered_tools = [
                    tool for tool in request.tools
                    if (tool.name if hasattr(tool, "name") else tool.get("name")) != "execute"
                ]
                request = request.override(tools=filtered_tools)
                has_execute_tool = False

        if self._custom_system_prompt is not None:
            system_prompt = self._custom_system_prompt
        else:
            prompt_parts = [FILESYSTEM_SYSTEM_PROMPT]
            if has_execute_tool and backend_supports_execution:
                prompt_parts.append(EXECUTION_SYSTEM_PROMPT)
            system_prompt = "\n\n".join(prompt_parts)

        if system_prompt:
            new_prompt = (
                request.system_prompt + "\n\n" + system_prompt
                if request.system_prompt
                else system_prompt
            )
            request = request.override(system_prompt=new_prompt)

        return await handler(request)

    def _process_large_message(
        self,
        message: ToolMessage,
        resolved_backend: BackendProtocol,
    ) -> tuple[ToolMessage, dict[str, FileData] | None]:
        """处理单个大消息，保存到文件系统

        Returns:
            (处理后的消息, 文件更新字典或None)
        """
        content = message.content
        if not isinstance(content, str) or len(content) <= 4 * self.tool_token_limit_before_evict:
            return message, None

        sanitized_id = sanitize_tool_call_id(message.tool_call_id)
        file_path = f"/large_tool_results/{sanitized_id}"
        result = resolved_backend.write(file_path, content)

        if result.error:
            return message, None

        content_sample = format_content_with_line_numbers(
            [line[:1000] for line in content.splitlines()[:10]],
            start_line=1
        )
        processed_message = ToolMessage(
            TOO_LARGE_TOOL_MSG.format(
                file_path=file_path,
                content_sample=content_sample,
            ),
            tool_call_id=message.tool_call_id,
        )
        return processed_message, result.files_update

    def _intercept_large_tool_result(
        self,
        tool_result: ToolMessage | Command,
        runtime: ToolRuntime
    ) -> ToolMessage | Command:
        """拦截并处理过大的工具结果

        支持 ToolMessage 和 Command 两种类型
        """
        # 处理 ToolMessage 类型
        if isinstance(tool_result, ToolMessage) and isinstance(tool_result.content, str):
            if not (self.tool_token_limit_before_evict and len(tool_result.content) > 4 * self.tool_token_limit_before_evict):
                return tool_result

            resolved_backend = self._get_backend(runtime)
            processed_message, files_update = self._process_large_message(
                tool_result,
                resolved_backend,
            )
            return (
                Command(
                    update={
                        "files": files_update,
                        "messages": [processed_message],
                    }
                )
                if files_update is not None
                else processed_message
            )

        # 处理 Command 类型
        if isinstance(tool_result, Command):
            update = tool_result.update
            if update is None:
                return tool_result

            command_messages = update.get("messages", [])
            accumulated_file_updates = dict(update.get("files", {}))
            resolved_backend = self._get_backend(runtime)
            processed_messages = []

            for message in command_messages:
                # 检查是否需要处理
                if not (
                    self.tool_token_limit_before_evict
                    and isinstance(message, ToolMessage)
                    and isinstance(message.content, str)
                    and len(message.content) > 4 * self.tool_token_limit_before_evict
                ):
                    processed_messages.append(message)
                    continue

                # 处理大消息
                processed_message, files_update = self._process_large_message(
                    message,
                    resolved_backend,
                )
                processed_messages.append(processed_message)
                if files_update is not None:
                    accumulated_file_updates.update(files_update)

            return Command(update={**update, "messages": processed_messages, "files": accumulated_file_updates})

        return tool_result

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        """拦截工具调用，如果结果过大则保存到文件系统"""
        if self.tool_token_limit_before_evict is None or request.tool_call["name"] in TOOL_GENERATORS:
            return handler(request)

        tool_result = handler(request)
        return self._intercept_large_tool_result(tool_result, request.runtime)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        """异步版本"""
        if self.tool_token_limit_before_evict is None or request.tool_call["name"] in TOOL_GENERATORS:
            return await handler(request)

        tool_result = await handler(request)
        return self._intercept_large_tool_result(tool_result, request.runtime)
