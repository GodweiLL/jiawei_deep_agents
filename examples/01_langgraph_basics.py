"""LangGraph 核心概念学习 - 第一课"""

from typing import Annotated
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage

class AgentState(TypedDict):
    """Agent 状态定义
    
    messages 使用 Annotated 添加 add_messages 作为Reducer
    意味着新消息会自动累加到 messages 列表中,而不是覆盖
    """
    messages: Annotated[list, add_messages]

def chatbot(state: AgentState) -> AgentState:
    """聊天机器人节点
    
    节点函数签名:
    - 输入:当前状态
    - 输出:状态更新（会通过 Reducer 合并）
    """
    # 获取最后一条用户消息
    last_message = state["messages"][-1]

    # 模拟 AI 回复
    response = AIMessage(content=f"你说的是: {last_message.content}")

    # 返回状态更新
    # 因为 messages 有 add_messages 作为Reducer,所以新消息会自动累加到列表中
    return {"messages": [response]}

def build_graph():
    """构建并编译状态图"""
    
    # 1.创建状态图,传入状态类型
    graph = StateGraph(AgentState)

    # 2.添加节点
    graph.add_node("chatbot", chatbot)

    # 3.连接节点
    graph.add_edge(START, "chatbot")
    graph.add_edge("chatbot", END)

    # 4.编译图
    return graph.compile()

if __name__ == "__main__":
    app = build_graph()

    initial_state = {
        "messages": [HumanMessage(content="你好")]
    }

    # 执行图
    # invoke 是同步执行,会阻塞当前线程,直到图执行完成
    result = app.invoke(initial_state)
    print(result)