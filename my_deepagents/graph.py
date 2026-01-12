"""DeepAgents - 集成规划、文件系统和子代理的智能代理框架"""

from collections.abc import Callable, Sequence
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    InterruptOnConfig,
    TodoListMiddleware,
)
from langchain.agents.middleware.summarization import SummarizationMiddleware
from langchain.agents.middleware.types import AgentMiddleware
from langchain.agents.structured_output import ResponseFormat
from langchain.chat_models import init_chat_model
from langchain_anthropic import ChatAnthropic
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.cache.base import BaseCache
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.types import Checkpointer

from my_deepagents.backends.protocol import BackendFactory, BackendProtocol
from my_deepagents.middleware.filesystem import FilesystemMiddleware
from my_deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from my_deepagents.middleware.subagents import (
    CompiledSubAgent,
    SubAgent,
    SubAgentMiddleware,
)


# ============================================================
# 常量定义
# ============================================================

BASE_AGENT_PROMPT = "为了完成用户交给你的目标，你可以使用一系列标准工具。"


# ============================================================
# 核心函数
# ============================================================

def get_default_model() -> ChatAnthropic:
    """获取默认模型"""
    return ChatAnthropic(
        model_name="claude-sonnet-4-5-20250929",
        max_tokens=20000,
    )

def create_deep_agent(
    model: str | BaseChatModel | None = None,
    tools: Sequence[BaseTool | Callable | dict[str, Any]] | None = None,
    *,
    system_prompt: str | None = None,
    middleware: Sequence[AgentMiddleware] = (),
    subagents: list[SubAgent | CompiledSubAgent] | None = None,
    response_format: ResponseFormat | None = None,
    context_schema: type[Any] | None = None,
    checkpointer: Checkpointer | None = None,
    store: BaseStore | None = None,
    backend: BackendProtocol | BackendFactory | None = None,
    interrupt_on: dict[str, bool | InterruptOnConfig] | None = None,
    debug: bool = False,
    name: str | None = None,
    cache: BaseCache | None = None,
) -> CompiledStateGraph:
    """创建 DeepAgent
    
    默认包含: TodoList,文件系统工具(ls/read/write/edit/glob/grep/execute),子代理工具"""

    # 1.模型初始化
    if model is None:
        model = get_default_model()
    elif isinstance(model, str):
        model = init_chat_model(model)

    # 2.配置 summarization 触发条件
    if(
        model.profile is not None
        and isinstance(model.profile, dict)
        and "max_input_tokens" in model.profile
        and isinstance(model.profile["max_input_tokens"], int)
    ):
        trigger = ("fraction", 0.85)
        keep = ("fraction", 0.10)
    else:
        trigger = ("tokens", 170000)
        keep = ("messages", 6)

    # 3. 构建中间件
    deepagent_middleware = [
        TodoListMiddleware(),
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(
            default_model=model,
            default_tools=tools,
            subagents=subagents if subagents is not None else [],
            default_middleware=[
                TodoListMiddleware(),
                FilesystemMiddleware(backend=backend),
                SummarizationMiddleware(
                    model=model,
                    trigger=trigger,
                    keep=keep,
                    trim_tokens_to_summarize=None,
                ),
                AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
                PatchToolCallsMiddleware(),
            ],
            default_interrupt_on=interrupt_on,
            general_purpose_agent=True,
        ),
        SummarizationMiddleware(
            model=model,
            trigger=trigger,
            keep=keep,
            trim_tokens_to_summarize=None,
        ),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
        PatchToolCallsMiddleware(),
    ]

    # 添加用户自定义中间件
    if middleware:
        deepagent_middleware.extend(middleware)

    # 添加人工介入中间件
    if interrupt_on is not None:
        deepagent_middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))
    
    # 4. 创建代理并设置递归限制
    return create_agent(
        model,
        system_prompt=system_prompt + "\n\n" + BASE_AGENT_PROMPT if system_prompt else BASE_AGENT_PROMPT,
        tools=tools,
        middleware=deepagent_middleware,
        response_format=response_format,
        context_schema=context_schema,
        checkpointer=checkpointer,
        store=store,
        debug=debug,
        name=name,
        cache=cache,
    ).with_config({"recursion_limit": 1000})