"""提供子代理功能的中间件 - 通过 task 工具启动子代理"""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, NotRequired, TypedDict, cast

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, InterruptOnConfig
from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ModelResponse
from langchain.tools import BaseTool, ToolRuntime
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import StructuredTool
from langgraph.types import Command


# ============================================================
# TypedDict 定义
# ============================================================

class SubAgent(TypedDict):
    """子代理规格定义"""
    name: str
    description: str
    system_prompt: str
    tools: Sequence[BaseTool | Callable | dict[str, Any]]
    model: NotRequired[str | BaseChatModel]
    middleware: NotRequired[list[AgentMiddleware]]
    interrupt_on: NotRequired[dict[str, bool | InterruptOnConfig]]

class CompiledSubAgent(TypedDict):
    """预编译的子代理规范"""
    name: str
    description: str
    runnable: Runnable


# ============================================================
# 常量定义
# ============================================================

DEFAULT_SUBAGENT_PROMPT = "为了完成用户交给你的目标，你可以使用一系列标准工具。"

# 传递给子代理时排除的状态键
_EXCLUDED_STATE_KEYS = {"messages", "todos", "structured_response"}

TASK_TOOL_DESCRIPTION = """启动一个临时子代理来处理复杂的、多步骤的独立任务，每个子代理有独立的上下文窗口。

可用的代理类型及其工具：
{available_agents}

使用 Task 工具时，必须通过 subagent_type 参数指定要使用的代理类型。

## 使用说明：
1. 尽可能并发启动多个代理以最大化性能；在单条消息中使用多个工具调用即可实现
2. 代理完成后会返回一条消息给你。代理返回的结果对用户不可见。要向用户展示结果，你需要发送文本消息给用户，简要总结结果
3. 每次代理调用都是无状态的。你无法向代理发送额外消息，代理也无法在最终报告之外与你通信。因此，你的提示词应包含详细的任务描述，让代理自主执行，并明确指定代理应在最终消息中返回什么信息
4. 代理的输出通常应该被信任
5. 明确告诉代理你期望它创建内容、执行分析，还是只做研究（搜索、读文件、网页抓取等），因为它不知道用户的意图
6. 如果代理描述中提到应该主动使用，那么你应该在用户没有明确要求的情况下主动使用它
7. 当只提供了通用代理时，你应该用它来处理所有任务。它非常适合隔离上下文和 token 使用

### 通用代理使用示例：

<example_agent_descriptions>
"general-purpose": 用于通用任务的代理，拥有与主代理相同的所有工具
</example_agent_descriptions>

<example>
用户: "我想研究勒布朗·詹姆斯、迈克尔·乔丹和科比·布莱恩特的成就，然后比较他们。"
助手: *并行使用 task 工具对三位球员分别进行独立研究*
助手: *综合三个独立研究任务的结果并回复用户*
<commentary>
研究本身就是一个复杂的多步骤任务。
每个球员的研究相互独立。
助手使用 task 工具将复杂目标分解为三个独立任务。
每个研究任务只需关注一个球员的上下文和 token，然后返回综合信息。
这样每个研究任务可以深入研究每个球员，但最终结果是综合信息，在比较球员时节省 token。
</commentary>
</example>

<example>
用户: "分析一个大型代码仓库的安全漏洞并生成报告。"
助手: *启动单个 task 子代理进行仓库分析*
助手: *接收报告并整合结果到最终总结*
<commentary>
即使只有一个任务，也使用子代理来隔离这个上下文繁重的任务。这防止主线程被细节淹没。
如果用户后续有问题，我们有简洁的报告可以参考，而不是整个分析和工具调用的历史。
</commentary>
</example>

<example>
用户: "帮我安排两个会议并为每个会议准备议程。"
助手: *并行调用 task 工具启动两个子代理（每个会议一个）来准备议程*
助手: *返回最终的日程和议程*
<commentary>
每个任务单独来看很简单，但子代理帮助隔离议程准备工作。
每个子代理只需关注一个会议的议程。
</commentary>
</example>

<example>
用户: "我想从达美乐订披萨，从麦当劳订汉堡，从赛百味订沙拉。"
助手: *直接并行调用工具完成三个订单*
<commentary>
助手没有使用 task 工具，因为目标非常简单明确，只需要几个简单的工具调用。
直接完成任务比使用 task 工具更好。
</commentary>
</example>

### 自定义代理使用示例：

<example_agent_descriptions>
"content-reviewer": 在完成重要内容或文档创建后使用此代理进行审查
"greeting-responder": 当回复用户问候时使用此代理，以友好的玩笑回应
"research-analyst": 使用此代理对复杂主题进行深入研究
</example_agent_descriptions>

<example>
用户: "请写一个检查数字是否为质数的函数"
助手: 好的，让我写一个检查数字是否为质数的函数
助手: 首先让我使用 Write 工具写代码：
<code>
function isPrime(n) {{
  if (n <= 1) return false
  for (let i = 2; i * i <= n; i++) {{
    if (n % i === 0) return false
  }}
  return true
}}
</code>
<commentary>
由于创建了重要内容且任务已完成，现在使用 content-reviewer 代理来审查代码
</commentary>
助手: 现在让我使用 content-reviewer 代理来审查代码
助手: 使用 Task 工具启动 content-reviewer 代理
</example>

<example>
用户: "你能帮我研究不同可再生能源对环境的影响并创建一份综合报告吗？"
<commentary>
这是一个复杂的研究任务，适合使用 research-analyst 代理进行深入分析
</commentary>
助手: 我来帮你研究可再生能源对环境的影响。让我使用 research-analyst 代理来进行综合研究。
助手: 使用 Task 工具启动 research-analyst 代理，提供详细的研究指示和报告格式要求
</example>

<example>
用户: "你好"
<commentary>
由于用户在打招呼，使用 greeting-responder 代理以友好的玩笑回应
</commentary>
助手: "我要使用 Task 工具启动 greeting-responder 代理"
</example>"""

TASK_SYSTEM_PROMPT = """## `task`（子代理生成器）

你可以使用 `task` 工具来启动处理独立任务的短期子代理。这些代理是临时的——它们只在任务持续期间存在，并返回单个结果。

何时使用 task 工具：
- 当任务复杂且需要多个步骤，可以完全独立委托时
- 当任务与其他任务独立，可以并行运行时
- 当任务需要大量推理或 token/上下文使用，会使主线程膨胀时
- 当沙盒化能提高可靠性时（如代码执行、结构化搜索、数据格式化）
- 当你只关心子代理的输出而不是中间步骤时

子代理生命周期：
1. **启动** → 提供清晰的角色、指令和预期输出
2. **运行** → 子代理自主完成任务
3. **返回** → 子代理提供单个结构化结果
4. **整合** → 将结果整合或综合到主线程

何时不使用 task 工具：
- 如果你需要在子代理完成后查看中间推理或步骤（task 工具会隐藏它们）
- 如果任务很简单（几个工具调用或简单查找）
- 如果委托不会减少 token 使用、复杂性或上下文切换
- 如果拆分只会增加延迟而没有好处

## 重要的 Task 工具使用注意事项
- 尽可能并行化你的工作。无论是工具调用还是任务，当你有独立的步骤需要完成时，并行启动它们以更快完成。这为用户节省时间非常重要。
- 记住使用 `task` 工具来隔离多部分目标中的独立任务。
- 当你有一个需要多个步骤的复杂任务，且与代理需要完成的其他任务独立时，就应该使用 `task` 工具。这些代理非常称职和高效。"""

DEFAULT_GENERAL_PURPOSE_DESCRIPTION = "通用代理，用于研究复杂问题、搜索文件和内容、执行多步骤任务。当你搜索关键字或文件且不确定能否在前几次尝试中找到正确匹配时，使用此代理来执行搜索。此代理拥有与主代理相同的所有工具。"


# ============================================================
# 核心函数
# ============================================================

def _get_subagents(
    *,
    default_model: str | BaseChatModel,
    default_tools: Sequence[BaseTool | Callable | dict[str, Any]],
    default_middleware: list[AgentMiddleware] | None,
    default_interrupt_on: dict[str, bool | InterruptOnConfig] | None,
    subagents: list[SubAgent | CompiledSubAgent],
    general_purpose_agent: bool,
) -> tuple[dict[str, Any], list[str]]:
    """从规格创建子代理实例
    
    Returns:
    - 子代理字典: 按名称映射的运行实例
    - 描述列表: 格式化的子代理描述
    """
    default_subagent_middleware = default_middleware or []
    agents: dict[str, Any] = {}
    subagent_descriptions = []

    # 创建通用代理（若启用）
    if general_purpose_agent:
        general_purpose_middleware = [*default_subagent_middleware]
        if default_interrupt_on:
            general_purpose_middleware.append(
                HumanInTheLoopMiddleware(interrupt_on=default_interrupt_on)
            )
        general_purpose_subagent = create_agent(
            default_model,
            system_prompt=DEFAULT_SUBAGENT_PROMPT,
            tools=default_tools,
            middleware=general_purpose_middleware,
        )
        agents["general-purpose"] = general_purpose_subagent
        subagent_descriptions.append(f"- general-purpose: {DEFAULT_GENERAL_PURPOSE_DESCRIPTION}")

    # 处理自定义子代理
    for agent_ in subagents:
        subagent_descriptions.append(f"- {agent_['name']}: {agent_['description']}")

        # 若是预编译的代理,直接使用
        if "runnable" in agent_:
            custom_agent = cast("CompiledSubAgent", agent_)
            agents[custom_agent["name"]] = custom_agent["runnable"]
            continue
        
        #否则需要编译
        _tools = agent_.get("tools", list(default_tools))
        subagent_model = agent_.get("model", default_model)
        _middleware = (
            [*default_subagent_middleware, *agent_["middleware"]] 
            if "middleware" in agent_ 
            else [*default_subagent_middleware]
        )

        interrupt_on = agent_.get("interrupt_on", default_interrupt_on)
        if interrupt_on:
            _middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))

        agents[agent_["name"]] = create_agent(
            subagent_model,
            system_prompt=agent_["system_prompt"],
            tools=_tools,
            middleware=_middleware,
        )
    return agents, subagent_descriptions


def _create_task_tool(
    *,
    default_model: str | BaseChatModel,
    default_tools: Sequence[BaseTool | Callable | dict[str, Any]],
    default_middleware: list[AgentMiddleware] | None,
    default_interrupt_on: dict[str, bool | InterruptOnConfig] | None,
    subagents: list[SubAgent | CompiledSubAgent],
    general_purpose_agent: bool,
    task_description: str | None = None,
) -> BaseTool:
    """创建用于调用子代理的task工具"""

    subagent_graphs, subagent_descriptions = _get_subagents(
        default_model=default_model,
        default_tools=default_tools,
        default_middleware=default_middleware,
        default_interrupt_on=default_interrupt_on,
        subagents=subagents,
        general_purpose_agent=general_purpose_agent,
    )
    subagent_description_str = "\n".join(subagent_descriptions)

    def _return_command_with_state_update(result: dict, tool_call_id: str) -> Command:
        """从子代理结果构建 Command"""
        state_update = {k: v for k, v in result.items() if k not in _EXCLUDED_STATE_KEYS}
        message_text = result["messages"][-1].text.rstrip() if result["messages"][-1].text else ""
        return Command(
            update={
                **state_update,
                "messages": [ToolMessage(message_text, tool_call_id=tool_call_id)],
            }
        )
    
    def _validate_and_prepare_state(
        subagent_type: str, 
        description: str, 
        runtime: ToolRuntime
    ) -> tuple[Runnable, dict]:
        """验证并准备子代理状态"""
        subagent = subagent_graphs[subagent_type]
        subagent_state = {k: v for k, v in runtime.state.items() if k not in _EXCLUDED_STATE_KEYS}
        subagent_state["messages"] = [HumanMessage(content=description)]
        return subagent, subagent_state
    
    # 处理工具描述
    if task_description is None:
        task_description = TASK_TOOL_DESCRIPTION.format(available_agents=subagent_description_str)
    elif "{available_agents}" in task_description:
        task_description = task_description.format(available_agents=subagent_description_str)

    def task(
        description: str, subagent_type: str, runtime: ToolRuntime
    ) -> str | Command:
        """同步执行子代理"""
        if subagent_type not in subagent_graphs:
            allowed_types = ", ".join([f"`{k}`" for k in subagent_graphs])
            return f"无法调用子代理 {subagent_type}，因为不存在，允许的类型有 {allowed_types}"

        subagent, subagent_state = _validate_and_prepare_state(subagent_type, description, runtime)
        result = subagent.invoke(subagent_state, runtime.config)

        if not runtime.tool_call_id:
            raise ValueError("子代理调用需要 tool_call_id")
        return _return_command_with_state_update(result, runtime.tool_call_id)
    
    async def atask(
        description: str,
        subagent_type: str,
        runtime: ToolRuntime,
    ) -> str | Command:
        """异步执行子代理"""
        if subagent_type not in subagent_graphs:
            allowed_types = ", ".join([f"`{k}`" for k in subagent_graphs])
            return f"无法调用子代理 {subagent_type}，它不存在。允许的类型有：{allowed_types}"

        subagent, subagent_state = _validate_and_prepare_state(subagent_type, description, runtime)
        result = await subagent.ainvoke(subagent_state, runtime.config)

        if not runtime.tool_call_id:
            raise ValueError("子代理调用需要 tool_call_id")
        return _return_command_with_state_update(result, runtime.tool_call_id)

    return StructuredTool.from_function(
        name="task",
        func=task,
        coroutine=atask,
        description=task_description,
    )
            
class SubAgentMiddleware(AgentMiddleware):
    """子代理中间件 - 通过 task 工具提供子代理功能
    
    这个中间件添加一个 task 工具，让代理可以启动子代理来处理复杂任务。
    子代理的好处是可以处理多步骤任务，然后返回简洁的结果给主代理。
    """

    def __init__(
        self,
        *,
        default_model: str | BaseChatModel,
        default_tools: Sequence[BaseTool | Callable | dict[str, Any]] | None = None,
        default_middleware: list[AgentMiddleware] | None = None,
        default_interrupt_on: dict[str, bool | InterruptOnConfig] | None = None,
        subagents: list[SubAgent | CompiledSubAgent] | None = None,
        system_prompt: str | None = TASK_SYSTEM_PROMPT,
        general_purpose_agent: bool = True,
        task_description: str | None = None,
    ) -> None:
        """初始化子代理中间件"""
        super().__init__()
        self.system_prompt = system_prompt
        task_tool = _create_task_tool(
            default_model=default_model,
            default_tools=default_tools or [],
            default_middleware=default_middleware,
            default_interrupt_on=default_interrupt_on,
            subagents=subagents or [],
            general_purpose_agent=general_purpose_agent,
            task_description=task_description,
        )
        self.tools = [task_tool]
    
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """在系统提示词中注入子代理说明"""
        if self.system_prompt is not None:
            system_prompt = (
                request.system_prompt + "\n\n" + self.system_prompt
                if request.system_prompt
                else self.system_prompt
            )
            return handler(request.override(system_prompt=system_prompt))
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """异步版本"""
        if self.system_prompt is not None:
            system_prompt = (
                request.system_prompt + "\n\n" + self.system_prompt 
                if request.system_prompt 
                else self.system_prompt
            )
            return await handler(request.override(system_prompt=system_prompt))
        return await handler(request)