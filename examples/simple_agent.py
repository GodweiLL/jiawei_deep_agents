"""简单 Agent 示例

演示如何使用 create_deep_agent 创建一个基本的 Agent
"""

import os
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from my_deepagents import create_deep_agent


# 配置 API
API_KEY = os.getenv("OPENAI_API_KEY", "sk-xxxxx")
API_BASE = os.getenv("OPENAI_API_BASE", "https://bmc-llm-relay.bluemediagroup.cn/v1")


def main():
    # 1. 创建模型
    model = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=API_KEY,
        base_url=API_BASE,
        max_tokens=2000,
    )
    
    # 2. 创建检查点（用于会话持久化）
    checkpointer = MemorySaver()
    
    # 3. 创建 Agent
    agent = create_deep_agent(
        model=model,
        system_prompt="你是一个友好、专业的助手，可以帮助用户完成各种任务。",
        checkpointer=checkpointer,
    )
    
    # 4. 配置会话
    config = {"configurable": {"thread_id": "demo-session"}}
    
    # 5. 交互循环
    print("=" * 50)
    print("DeepAgent 演示")
    print("输入 'quit' 退出")
    print("=" * 50)
    
    while True:
        user_input = input("\n你: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            print("再见！")
            break
        
        if not user_input:
            continue
        
        # 调用 Agent
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
        )
        
        # 输出响应
        response = result["messages"][-1].content
        print(f"\n助手: {response}")


if __name__ == "__main__":
    main()
