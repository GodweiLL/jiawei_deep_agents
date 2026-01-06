# DeepAgents 复刻学习计划

> 通过手搓deepagents框架，学习LangChain与LangGraph最新版使用方式

## 项目概览

### 原始项目分析

DeepAgents是一个基于LangChain/LangGraph的Agent框架，核心特性包括：
- **规划与任务分解** - TodoListMiddleware
- **上下文管理** - FilesystemMiddleware + Backend系统
- **子代理委托** - SubAgentMiddleware
- **长期记忆** - StoreBackend

### 原始项目完整结构

```
deepagents/
├── libs/
│   ├── deepagents/                    # [核心库] 主要复刻目标
│   │   ├── deepagents/
│   │   │   ├── __init__.py
│   │   │   ├── graph.py               # 入口函数
│   │   │   ├── backends/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── protocol.py        # 后端协议定义
│   │   │   │   ├── utils.py           # 工具函数
│   │   │   │   ├── state.py           # 状态后端
│   │   │   │   ├── filesystem.py      # 文件系统后端
│   │   │   │   ├── store.py           # 持久化后端
│   │   │   │   ├── composite.py       # 组合后端
│   │   │   │   └── sandbox.py         # 沙盒后端基类
│   │   │   └── middleware/
│   │   │       ├── __init__.py
│   │   │       ├── patch_tool_calls.py # 工具调用修补
│   │   │       ├── filesystem.py       # 文件系统中间件
│   │   │       └── subagents.py        # 子代理中间件
│   │   └── tests/
│   │       ├── unit_tests/
│   │       │   ├── middleware/
│   │       │   ├── backends/
│   │       │   └── ...
│   │       └── integration_tests/
│   │
│   ├── deepagents-cli/                # [CLI工具] 可选扩展
│   │   ├── deepagents_cli/
│   │   │   ├── __init__.py
│   │   │   ├── main.py                # CLI入口
│   │   │   ├── agent.py               # Agent封装
│   │   │   ├── config.py              # 配置管理
│   │   │   ├── tools.py               # 工具定义
│   │   │   ├── shell.py               # Shell交互
│   │   │   ├── execution.py           # 命令执行
│   │   │   ├── file_ops.py            # 文件操作
│   │   │   ├── ui.py                  # 用户界面
│   │   │   ├── input.py               # 输入处理
│   │   │   ├── image_utils.py         # 图像工具
│   │   │   ├── token_utils.py         # Token统计
│   │   │   ├── project_utils.py       # 项目工具
│   │   │   ├── agent_memory.py        # Agent记忆
│   │   │   ├── commands.py            # 命令定义
│   │   │   ├── skills/                # 技能系统
│   │   │   │   ├── __init__.py
│   │   │   │   ├── load.py            # 技能加载
│   │   │   │   ├── commands.py        # 技能命令
│   │   │   │   └── middleware.py      # 技能中间件
│   │   │   └── integrations/          # 沙盒集成
│   │   │       ├── __init__.py
│   │   │       ├── sandbox_factory.py # 沙盒工厂
│   │   │       ├── daytona.py         # Daytona集成
│   │   │       ├── modal.py           # Modal集成
│   │   │       └── runloop.py         # Runloop集成
│   │   ├── tests/
│   │   └── examples/skills/           # 技能示例
│   │
│   ├── acp/                           # [ACP协议] 可选扩展
│   │   ├── deepagents_acp/
│   │   │   ├── __init__.py
│   │   │   └── server.py              # ACP服务器
│   │   └── tests/
│   │
│   └── harbor/                        # [Harbor集成] 可选扩展
│       ├── deepagents_harbor/
│       │   ├── __init__.py
│       │   ├── backend.py             # Harbor后端
│       │   ├── deepagents_wrapper.py  # DeepAgents封装
│       │   └── tracing.py             # 追踪功能
│       └── tests/
```

### 核心模块统计

| 模块 | 文件 | 行数 | 复杂度 | 优先级 |
|------|------|------|--------|--------|
| graph.py | 入口函数 | ~165 | 中等 | P0 |
| backends/protocol.py | 后端协议 | ~500 | 中等 | P0 |
| backends/state.py | 状态后端 | ~188 | 简单 | P0 |
| backends/filesystem.py | 文件系统后端 | ~680 | 高 | P0 |
| backends/store.py | 持久化后端 | ~478 | 中等 | P1 |
| backends/composite.py | 组合后端 | ~450 | 高 | P1 |
| backends/sandbox.py | 沙盒后端基类 | ~361 | 中等 | P2 |
| backends/utils.py | 工具函数 | ~440 | 中等 | P0 |
| middleware/patch_tool_calls.py | 工具调用修补 | ~50 | 简单 | P0 |
| middleware/filesystem.py | 文件系统中间件 | ~1123 | 高 | P0 |
| middleware/subagents.py | 子代理中间件 | ~610 | 高 | P1 |

### 复刻项目结构（与原始保持一致）

```
jiawei_deep_agents/
├── deepagents/                        # 原始参考代码（只读）
│
├── my_deepagents/                     # [Phase 2-4] 核心库复刻
│   ├── __init__.py
│   ├── graph.py
│   ├── backends/
│   │   ├── __init__.py
│   │   ├── protocol.py
│   │   ├── utils.py
│   │   ├── state.py
│   │   ├── filesystem.py
│   │   ├── store.py
│   │   ├── composite.py
│   │   └── sandbox.py
│   └── middleware/
│       ├── __init__.py
│       ├── patch_tool_calls.py
│       ├── filesystem.py
│       └── subagents.py
│
├── my_deepagents_cli/                 # [Phase 6] CLI工具复刻（可选）
│   ├── __init__.py
│   ├── main.py
│   ├── agent.py
│   ├── config.py
│   ├── tools.py
│   ├── shell.py
│   ├── execution.py
│   ├── file_ops.py
│   ├── ui.py
│   ├── input.py
│   ├── skills/
│   │   ├── __init__.py
│   │   ├── load.py
│   │   ├── commands.py
│   │   └── middleware.py
│   └── integrations/
│       ├── __init__.py
│       ├── sandbox_factory.py
│       ├── daytona.py
│       ├── modal.py
│       └── runloop.py
│
├── my_deepagents_acp/                 # [Phase 7] ACP协议复刻（可选）
│   ├── __init__.py
│   └── server.py
│
├── tests/                             # 测试目录
│   ├── unit_tests/                    # 单元测试
│   │   ├── __init__.py
│   │   ├── backends/
│   │   │   ├── __init__.py
│   │   │   ├── test_protocol.py
│   │   │   ├── test_utils.py
│   │   │   ├── test_state.py
│   │   │   ├── test_filesystem.py
│   │   │   ├── test_store.py
│   │   │   ├── test_composite.py
│   │   │   └── test_sandbox.py
│   │   ├── middleware/
│   │   │   ├── __init__.py
│   │   │   ├── test_patch_tool_calls.py
│   │   │   ├── test_filesystem.py
│   │   │   └── test_subagents.py
│   │   ├── test_graph.py
│   │   └── chat_model.py              # 测试用FakeChatModel
│   └── integration_tests/             # 集成测试
│       ├── __init__.py
│       ├── test_deepagents.py
│       ├── test_filesystem_middleware.py
│       └── test_subagent_middleware.py
│
├── examples/                          # 示例代码
│   ├── simple_agent.py
│   ├── file_operations.py
│   ├── multi_subagent.py
│   └── skills/                        # 技能示例
│
├── plan.md
└── pyproject.toml
```

---

## Phase 1: 环境搭建与基础概念

### 1.1 创建项目结构
- [ ] 创建 `my_deepagents/` 目录结构
- [ ] 创建 `pyproject.toml` 配置文件
- [ ] 安装依赖：langchain, langchain-core, langchain-anthropic, langgraph

### 1.2 LangGraph 核心概念学习

需要掌握的核心概念：

| 概念 | 说明 | 相关类/函数 |
|------|------|-------------|
| StateGraph | 状态图定义 | `langgraph.graph.StateGraph` |
| CompiledStateGraph | 编译后的状态图 | `StateGraph.compile()` |
| State | 状态定义 | `TypedDict` |
| Reducer | 状态更新器 | `Annotated[..., reducer]` |
| Checkpointer | 检查点持久化 | `langgraph.checkpoint.Checkpointer` |
| add_messages | 消息累加器 | `langgraph.graph.add_messages` |

### 1.3 LangChain 核心概念学习

| 概念 | 说明 | 相关类/函数 |
|------|------|-------------|
| BaseChatModel | 聊天模型基类 | `langchain_core.language_models.BaseChatModel` |
| BaseTool | 工具基类 | `langchain_core.tools.BaseTool` |
| @tool | 工具装饰器 | `langchain_core.tools.tool` |
| AgentMiddleware | 中间件基类 | `langchain.agents.middleware.AgentMiddleware` |
| Messages | 消息类型 | `AIMessage`, `HumanMessage`, `ToolMessage` |

### 1.4 产出物
- [ ] `my_deepagents/__init__.py`
- [ ] `pyproject.toml`
- [ ] 简单的"Hello World" Agent示例

---

## Phase 2: 核心入口 - graph.py

### 2.1 学习目标
理解 `create_deep_agent()` 函数如何组装各个组件

### 2.2 函数签名分析

```python
def create_deep_agent(
    model: str | BaseChatModel | None = None,          # 模型选择
    tools: Sequence[BaseTool | Callable | dict] = None, # 自定义工具
    system_prompt: str | None = None,                  # 系统提示词
    middleware: Sequence[AgentMiddleware] = (),        # 自定义中间件
    subagents: list[SubAgent | CompiledSubAgent] = None, # 子代理
    response_format: ResponseFormat | None = None,     # 响应格式
    context_schema: type[Any] | None = None,           # 上下文模式
    checkpointer: Checkpointer | None = None,          # 检查点
    store: BaseStore | None = None,                    # 存储
    backend: BackendProtocol | BackendFactory = None,  # 后端
    interrupt_on: dict[str, bool | InterruptOnConfig] = None, # HITL
    debug: bool = False,
    name: str | None = None,
    cache: BaseCache | None = None,
) -> CompiledStateGraph
```

### 2.3 核心实现步骤
1. [ ] 理解默认模型初始化 (Claude Sonnet)
2. [ ] 理解中间件栈的组装顺序
3. [ ] 理解 `create_agent_react()` 的调用方式
4. [ ] 理解 StateGraph 的编译过程

### 2.4 关键代码点
- 默认后端选择逻辑
- 中间件注入机制
- 递归限制设置 (recursion_limit=1000)

### 2.5 产出物
- [ ] `my_deepagents/graph.py`
- [ ] `tests/test_graph.py`
- [ ] 学习笔记：中间件组装机制

---

## Phase 3: 后端系统 - backends/

### 3.1 protocol.py - 后端协议定义

**学习目标**: 理解Backend的抽象设计

```python
class BackendProtocol(Protocol):
    async def ls(path: str) -> list[FileInfo]: ...
    async def read(path: str) -> FileDownloadResponse: ...
    async def write(path: str, content: str) -> WriteResult: ...
    async def edit(path: str, old: str, new: str) -> EditResult: ...
    async def glob(pattern: str, path: str) -> list[str]: ...
    async def grep(pattern: str, path: str) -> list[GrepMatch]: ...
    async def execute(command: str) -> tuple[str, str, int]: ...  # 可选
```

**产出物**:
- [ ] `my_deepagents/backends/protocol.py`
- [ ] 学习笔记：Python Protocol类型提示

### 3.2 utils.py - 工具函数

**核心函数**:
- `_glob_search_files()` - glob模式匹配
- `grep_matches_from_files()` - 内容搜索
- `create_file_data()` - 创建文件数据结构
- `perform_string_replacement()` - 字符串替换编辑
- `format_content_with_line_numbers()` - 格式化输出
- `truncate_if_too_long()` - 长内容截断

**产出物**:
- [ ] `my_deepagents/backends/utils.py`
- [ ] `tests/test_backends/test_utils.py`

### 3.3 state.py - 状态后端

**学习目标**: 最简单的后端实现，文件存储在LangGraph状态中

**核心概念**:
- State Reducer (`_file_data_reducer`)
- 临时存储（单次对话）
- 路径验证

**产出物**:
- [ ] `my_deepagents/backends/state.py`
- [ ] `tests/test_backends/test_state.py`

### 3.4 filesystem.py - 文件系统后端

**学习目标**: 真实文件系统操作

**核心特性**:
- 虚拟模式（沙盒到cwd）
- O_NOFOLLOW防止符号链接攻击
- Ripgrep集成（可选）
- 文件大小限制

**产出物**:
- [ ] `my_deepagents/backends/filesystem.py`
- [ ] `tests/test_backends/test_filesystem.py`

### 3.5 store.py - 持久化后端

**学习目标**: LangGraph BaseStore持久化

**核心特性**:
- 跨对话持久存储
- 命名空间隔离
- assistant_id隔离

**产出物**:
- [ ] `my_deepagents/backends/store.py`
- [ ] `tests/test_backends/test_store.py`

### 3.6 composite.py - 组合后端

**学习目标**: 路由系统设计

**核心特性**:
- 前缀匹配路由
- 跨后端聚合
- 透明前缀管理

**产出物**:
- [ ] `my_deepagents/backends/composite.py`
- [ ] `tests/test_backends/test_composite.py`

### 3.7 sandbox.py - 沙盒后端基类

**学习目标**: 理解远程沙盒执行的抽象设计

**核心特性**:
- `BaseSandbox` 抽象基类
- 子类只需实现 `execute()` 方法
- 其他操作通过shell命令自动实现
- 用于Modal、Daytona等远程沙盒

**产出物**:
- [ ] `my_deepagents/backends/sandbox.py`
- [ ] `tests/test_backends/test_sandbox.py`

---

## Phase 4: 中间件系统 - middleware/

### 4.1 patch_tool_calls.py - 工具调用修补

**学习目标**: 最简单的中间件实现

**功能**: 处理中断后的悬空工具调用

**产出物**:
- [ ] `my_deepagents/middleware/patch_tool_calls.py`
- [ ] 学习笔记：AgentMiddleware生命周期

### 4.2 filesystem.py - 文件系统中间件

**学习目标**: 理解工具集的设计模式

**工具列表**:
| 工具 | 功能 |
|------|------|
| ls | 列出目录内容 |
| read_file | 读取文件（支持分页） |
| write_file | 创建/覆写文件 |
| edit_file | 精确字符串替换 |
| glob | 模式匹配搜索 |
| grep | 文本内容搜索 |
| execute | Shell命令执行（可选） |

**产出物**:
- [ ] `my_deepagents/middleware/filesystem.py`
- [ ] `tests/test_middleware/test_filesystem.py`

### 4.3 subagents.py - 子代理中间件

**学习目标**: 理解子代理委托机制

**核心概念**:
- SubAgent TypedDict定义
- 并发执行
- 状态隔离
- 上下文传递

**产出物**:
- [ ] `my_deepagents/middleware/subagents.py`
- [ ] `tests/test_middleware/test_subagents.py`

---

## Phase 5: 整合与进阶

### 5.1 端到端测试
- [ ] 编写完整的端到端测试
- [ ] 使用FakeChatModel模拟LLM
- [ ] `tests/unit_tests/chat_model.py`

### 5.2 示例应用
- [ ] `examples/simple_agent.py` - 简单文件操作Agent
- [ ] `examples/multi_subagent.py` - 多子代理协作示例
- [ ] `examples/file_operations.py` - 持久化记忆示例

---

## Phase 6: CLI工具系统（可选扩展）

### 6.1 核心模块

| 文件 | 功能 | 学习重点 |
|------|------|----------|
| main.py | CLI入口 | Click/Typer框架 |
| agent.py | Agent封装 | 如何封装DeepAgents |
| config.py | 配置管理 | YAML/JSON配置解析 |
| tools.py | 工具定义 | 额外工具实现 |
| shell.py | Shell交互 | PTK/Prompt-Toolkit |
| execution.py | 命令执行 | 异步执行管理 |
| file_ops.py | 文件操作 | 高级文件API |
| ui.py | 用户界面 | Rich终端UI |
| input.py | 输入处理 | 流式输入处理 |

### 6.2 技能系统 (skills/)

| 文件 | 功能 |
|------|------|
| load.py | 技能发现与加载 |
| commands.py | 技能命令解析 |
| middleware.py | 技能中间件 |

### 6.3 沙盒集成 (integrations/)

| 文件 | 功能 |
|------|------|
| sandbox_factory.py | 沙盒工厂模式 |
| daytona.py | Daytona云沙盒 |
| modal.py | Modal云沙盒 |
| runloop.py | Runloop沙盒 |

### 6.4 产出物
- [ ] `my_deepagents_cli/` 完整实现
- [ ] CLI使用文档
- [ ] 自定义技能示例

---

## Phase 7: ACP协议（可选扩展）

### 7.1 学习目标
理解Agent Communication Protocol的设计

### 7.2 核心实现

| 文件 | 功能 |
|------|------|
| server.py | ACP服务器实现 |

### 7.3 产出物
- [ ] `my_deepagents_acp/server.py`
- [ ] ACP协议使用示例

---

## 学习进度跟踪

### 核心模块（必学）

| 阶段 | 状态 | 完成日期 | 备注 |
|------|------|----------|------|
| Phase 1 | 未开始 | - | 环境搭建 |
| Phase 2 | 未开始 | - | graph.py |
| Phase 3.1 | 未开始 | - | protocol.py |
| Phase 3.2 | 未开始 | - | utils.py |
| Phase 3.3 | 未开始 | - | state.py |
| Phase 3.4 | 未开始 | - | filesystem.py |
| Phase 3.5 | 未开始 | - | store.py |
| Phase 3.6 | 未开始 | - | composite.py |
| Phase 3.7 | 未开始 | - | sandbox.py |
| Phase 4.1 | 未开始 | - | patch_tool_calls.py |
| Phase 4.2 | 未开始 | - | filesystem middleware |
| Phase 4.3 | 未开始 | - | subagents.py |
| Phase 5 | 未开始 | - | 整合测试 |

### 可选扩展

| 阶段 | 状态 | 完成日期 | 备注 |
|------|------|----------|------|
| Phase 6 | 未开始 | - | CLI工具系统 |
| Phase 7 | 未开始 | - | ACP协议 |

---

## 文件对照检查表

用于确保不遗漏任何文件：

### backends/ 目录

| 原始文件 | 复刻文件 | 状态 |
|----------|----------|------|
| `deepagents/libs/deepagents/deepagents/backends/__init__.py` | `my_deepagents/backends/__init__.py` | [ ] |
| `deepagents/libs/deepagents/deepagents/backends/protocol.py` | `my_deepagents/backends/protocol.py` | [ ] |
| `deepagents/libs/deepagents/deepagents/backends/utils.py` | `my_deepagents/backends/utils.py` | [ ] |
| `deepagents/libs/deepagents/deepagents/backends/state.py` | `my_deepagents/backends/state.py` | [ ] |
| `deepagents/libs/deepagents/deepagents/backends/filesystem.py` | `my_deepagents/backends/filesystem.py` | [ ] |
| `deepagents/libs/deepagents/deepagents/backends/store.py` | `my_deepagents/backends/store.py` | [ ] |
| `deepagents/libs/deepagents/deepagents/backends/composite.py` | `my_deepagents/backends/composite.py` | [ ] |
| `deepagents/libs/deepagents/deepagents/backends/sandbox.py` | `my_deepagents/backends/sandbox.py` | [ ] |

### middleware/ 目录

| 原始文件 | 复刻文件 | 状态 |
|----------|----------|------|
| `deepagents/libs/deepagents/deepagents/middleware/__init__.py` | `my_deepagents/middleware/__init__.py` | [ ] |
| `deepagents/libs/deepagents/deepagents/middleware/patch_tool_calls.py` | `my_deepagents/middleware/patch_tool_calls.py` | [ ] |
| `deepagents/libs/deepagents/deepagents/middleware/filesystem.py` | `my_deepagents/middleware/filesystem.py` | [ ] |
| `deepagents/libs/deepagents/deepagents/middleware/subagents.py` | `my_deepagents/middleware/subagents.py` | [ ] |

### 根目录

| 原始文件 | 复刻文件 | 状态 |
|----------|----------|------|
| `deepagents/libs/deepagents/deepagents/__init__.py` | `my_deepagents/__init__.py` | [ ] |
| `deepagents/libs/deepagents/deepagents/graph.py` | `my_deepagents/graph.py` | [ ] |

---

## 参考资源

- [LangChain 官方文档](https://python.langchain.com/)
- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [原始DeepAgents代码](./deepagents/libs/deepagents/deepagents/)
- [原始测试代码](./deepagents/libs/deepagents/tests/)
- [原始CLI代码](./deepagents/libs/deepagents-cli/deepagents_cli/)
- [原始ACP代码](./deepagents/libs/acp/deepagents_acp/)
