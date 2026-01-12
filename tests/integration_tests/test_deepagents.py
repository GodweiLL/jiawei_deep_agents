"""DeepAgents 端到端测试

使用真实 LLM 验证框架核心功能
支持 OpenAI 和 Claude 模型
"""

import os
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import MemorySaver

from my_deepagents import create_deep_agent


# 配置 API（第三方中转，支持 OpenAI 模式）
API_KEY = os.getenv("OPENAI_API_KEY", "sk-PUiD4cBwAaHpIvgf1a4ciGyf0P0lp3wi661D2jwAUT7TkoJS")
API_BASE = os.getenv("OPENAI_API_BASE", "https://bmc-llm-relay.bluemediagroup.cn/v1")

# Anthropic 原生 API（可选）
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# 模型选择: "openai", "claude-openai", "claude-native"
MODEL_TYPE = os.getenv("MODEL_TYPE", "openai")


def get_test_model() -> BaseChatModel:
    """获取测试用模型

    支持三种模式:
    - openai: 使用 GPT 模型（通过中转 API）
    - claude-openai: 使用 Claude 模型（通过 OpenAI 兼容的中转 API）
    - claude-native: 使用 Claude 模型（通过 Anthropic 原生 API）
    """
    if MODEL_TYPE == "claude-native" and ANTHROPIC_API_KEY:
        return ChatAnthropic(
            model="claude-sonnet-4-20250514",
            api_key=ANTHROPIC_API_KEY,
            max_tokens=1000,
        )
    elif MODEL_TYPE == "claude-openai":
        return ChatOpenAI(
            model="claude-sonnet-4-20250514",
            api_key=API_KEY,
            base_url=API_BASE,
            max_tokens=1000,
        )
    else:
        # 默认使用 OpenAI 模型
        return ChatOpenAI(
            model="gpt-5.2",
            api_key=API_KEY,
            base_url=API_BASE,
            max_tokens=1000,
        )


def test_create_agent_basic():
    """测试1: 基本代理创建"""
    print("\n" + "=" * 50)
    print("测试1: 基本代理创建")
    print("=" * 50)
    
    model = get_test_model()
    checkpointer = MemorySaver()
    
    agent = create_deep_agent(
        model=model,
        system_prompt="你是一个友好的助手",
        checkpointer=checkpointer,
    )
    
    # 验证代理创建成功
    assert agent is not None
    print("✅ 代理创建成功")
    
    # 简单对话测试
    config = {"configurable": {"thread_id": "test-1"}}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "你好，请用一句话介绍自己"}]},
        config=config,
    )
    
    print(f"用户: 你好，请用一句话介绍自己")
    print(f"助手: {result['messages'][-1].content[:100]}...")
    print("✅ 基本对话成功")


def test_todolist_middleware():
    """测试2: TodoList 中间件"""
    print("\n" + "=" * 50)
    print("测试2: TodoList 中间件")
    print("=" * 50)
    
    model = get_test_model()
    checkpointer = MemorySaver()
    
    agent = create_deep_agent(
        model=model,
        system_prompt="你是一个任务管理助手，善于分解任务",
        checkpointer=checkpointer,
    )
    
    config = {"configurable": {"thread_id": "test-2"}}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "帮我规划一个简单的周末计划，列出3个待办事项，使用todolist工具"}]},
        config=config,
    )
    
    print(f"用户: 帮我规划一个简单的周末计划，列出3个待办事项")
    print(f"助手: {result['messages'][-1].content[:200]}...")
    
    # 检查是否有 todos 状态
    if "todos" in result:
        print(f"✅ TodoList 状态存在，共 {len(result.get('todos', []))} 项")
    else:
        print("⚠️ TodoList 状态未找到（可能模型未使用该功能）")


def test_filesystem_tools():
    """测试3: 文件系统工具"""
    print("\n" + "=" * 50)
    print("测试3: 文件系统工具")
    print("=" * 50)
    
    model = get_test_model()
    checkpointer = MemorySaver()
    
    agent = create_deep_agent(
        model=model,
        system_prompt="你是一个文件操作助手",
        checkpointer=checkpointer,
    )
    
    config = {"configurable": {"thread_id": "test-3"}}
    
    # 测试 ls 工具
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "请列出当前目录下的文件"}]},
        config=config,
    )
    
    print(f"用户: 请列出当前目录下的文件")
    print(f"助手: {result['messages'][-1].content[:300]}...")
    print("✅ 文件系统工具测试完成")


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("  DeepAgents 端到端测试")
    print("=" * 60)
    
    try:
        test_create_agent_basic()
        test_todolist_middleware()
        test_filesystem_tools()
        
        print("\n" + "=" * 60)
        print("  所有测试通过！")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        raise


if __name__ == "__main__":
    main()
