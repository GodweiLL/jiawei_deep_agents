"""修复消息历史中悬空的工具调用"""
from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Overwrite

class PatchToolCallsMiddleware(AgentMiddleware):
    """修复悬空工具调用的中间件
    
    当对话被中断时，可能存在 AIMessage 发出了工具调用请求，
    但没有对应的 ToolMessage 响应。这会导致 LLM 困惑。
    此中间件在 Agent 开始前检测并修复这种情况。
    """

    def before_agent(
        self,
        state:AgentState,
        runtime:Runtime[Any],
    ) -> dict[str, Any] | None:
        """在 Agent 开始前，检测并修复悬空工具调用"""
        messages = state["messages"]

        # 如果消息列表为空，无需处理
        if not messages or len(messages) == 0:
            return None

        patched_messages = []

        # 遍历消息,检查每个 AIMessage 的工具调用部分
        for i,msg in enumerate(messages):
            patched_messages.append(msg)

            # 检查是否是带工具调用的 AI 消息
            if msg.type == "ai" and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    # 查找对应的ToolMessage
                    corresponding_tool_msg = next(
                        (
                            m for m in messages[i:] 
                            if m.type == "tool" and m.tool_call_id == tool_call["id"]
                        ),
                        None,
                    )

                    # 如果没找到对应的 ToolMessage，说明是悬空调用
                    if corresponding_tool_msg is None:
                        # 创建一个 ToolMessage 来表示悬空工具调用
                        tool_msg = (
                            f"Tool call {tool_call['name']} with id {tool_call['id']} was "
                            "cancelled - another message came in before it could be completed."
                        )
                        # 添加一个补丁 ToolMessage
                        patched_messages.append(
                            ToolMessage(
                                content=tool_msg,
                            )
                        )
        # 返回更新后的消息列表
        return {"messages": Overwrite(patched_messages)}
