"""MyDeepAgents - 集成规划、文件系统和子代理的智能代理框架

通过复刻 DeepAgents 学习 LangChain 与 LangGraph
"""

from my_deepagents.backends.protocol import BackendFactory, BackendProtocol
from my_deepagents.backends.state import StateBackend
from my_deepagents.graph import create_deep_agent, get_default_model
from my_deepagents.middleware.filesystem import FilesystemMiddleware, FilesystemState
from my_deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from my_deepagents.middleware.subagents import (
    CompiledSubAgent,
    SubAgent,
    SubAgentMiddleware,
)

__all__ = [
    # 核心入口
    "create_deep_agent",
    "get_default_model",
    # 后端
    "BackendProtocol",
    "BackendFactory",
    "StateBackend",
    # 中间件
    "FilesystemMiddleware",
    "FilesystemState",
    "PatchToolCallsMiddleware",
    "SubAgentMiddleware",
    "SubAgent",
    "CompiledSubAgent",
]
