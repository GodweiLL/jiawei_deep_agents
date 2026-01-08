"""Middleware package - 中间件系统，扩展 Agent 能力"""

from my_deepagents.middleware.filesystem import FilesystemMiddleware, FilesystemState
from my_deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from my_deepagents.middleware.subagents import (
    CompiledSubAgent,
    SubAgent,
    SubAgentMiddleware,
)

__all__ = [
    "FilesystemMiddleware",
    "FilesystemState",
    "PatchToolCallsMiddleware",
    "SubAgentMiddleware",
    "SubAgent",
    "CompiledSubAgent",
]
