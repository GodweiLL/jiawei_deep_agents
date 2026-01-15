"""StoreBackend: LangGraph BaseStore 适配器（持久化，跨会话）"""

from typing import TYPE_CHECKING, Any

from langgraph.config import get_config
from langgraph.store.base import BaseStore, Item

from my_deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)
from my_deepagents.backends.utils import (
    _glob_search_files,
    create_file_data,
    file_data_to_string,
    format_read_response,
    grep_matches_from_files,
    perform_string_replacement,
    update_file_data,
)

if TYPE_CHECKING:
    from langchain.tools import ToolRuntime


# ============================================================
# StoreBackend 类
# ============================================================

class StoreBackend(BackendProtocol):
    """使用 LangGraph BaseStore 的持久化后端

    特点：
    - 跨会话持久化存储
    - 支持命名空间隔离（多租户）
    - 通过 assistant_id 实现数据隔离
    """

    def __init__(self, runtime: "ToolRuntime"):
        """初始化 StoreBackend

        Args:
            runtime: ToolRuntime 实例，提供 store 访问和配置
        """
        self.runtime = runtime

    def _get_store(self) -> BaseStore:
        """获取 store 实例

        Returns:
            BaseStore 实例

        Raises:
            ValueError: 如果 runtime 中没有 store
        """
        store = self.runtime.store
        if store is None:
            msg = "Store is required but not available in runtime"
            raise ValueError(msg)
        return store

    def _get_namespace(self) -> tuple[str, ...]:
        """获取存储操作的命名空间

        优先级：
        1) 使用 self.runtime.config（测试时显式传入）
        2) 回退到 langgraph.config.get_config()
        3) 默认 ("filesystem",)

        如果配置中有 assistant_id，返回 (assistant_id, "filesystem") 实现隔离
        """
        namespace = "filesystem"

        # 优先使用 runtime 提供的配置
        runtime_cfg = getattr(self.runtime, "config", None)
        if isinstance(runtime_cfg, dict):
            assistant_id = runtime_cfg.get("metadata", {}).get("assistant_id")
            if assistant_id:
                return (assistant_id, namespace)
            return (namespace,)

        # 回退到 langgraph 上下文，但要防止在非 runnable 上下文中调用出错
        try:
            cfg = get_config()
        except Exception:
            return (namespace,)

        try:
            assistant_id = cfg.get("metadata", {}).get("assistant_id")
        except Exception:
            assistant_id = None

        if assistant_id:
            return (assistant_id, namespace)
        return (namespace,)

    def _convert_store_item_to_file_data(self, store_item: Item) -> dict[str, Any]:
        """将 Store Item 转换为 FileData 格式

        Args:
            store_item: 存储项

        Returns:
            FileData 字典，包含 content, created_at, modified_at

        Raises:
            ValueError: 如果必需字段缺失或类型错误
        """
        if "content" not in store_item.value or not isinstance(store_item.value["content"], list):
            msg = f"Store item does not contain valid content field. Got: {store_item.value.keys()}"
            raise ValueError(msg)
        if "created_at" not in store_item.value or not isinstance(store_item.value["created_at"], str):
            msg = f"Store item does not contain valid created_at field. Got: {store_item.value.keys()}"
            raise ValueError(msg)
        if "modified_at" not in store_item.value or not isinstance(store_item.value["modified_at"], str):
            msg = f"Store item does not contain valid modified_at field. Got: {store_item.value.keys()}"
            raise ValueError(msg)
        return {
            "content": store_item.value["content"],
            "created_at": store_item.value["created_at"],
            "modified_at": store_item.value["modified_at"],
        }

    def _convert_file_data_to_store_value(self, file_data: dict[str, Any]) -> dict[str, Any]:
        """将 FileData 转换为适合 store.put() 的字典

        Args:
            file_data: FileData 字典

        Returns:
            包含 content, created_at, modified_at 的字典
        """
        return {
            "content": file_data["content"],
            "created_at": file_data["created_at"],
            "modified_at": file_data["modified_at"],
        }

    def _search_store_paginated(
        self,
        store: BaseStore,
        namespace: tuple[str, ...],
        *,
        query: str | None = None,
        filter: dict[str, Any] | None = None,
        page_size: int = 100,
    ) -> list[Item]:
        """分页搜索 store，获取所有结果

        Args:
            store: 存储实例
            namespace: 命名空间前缀
            query: 可选的自然语言查询
            filter: 键值对过滤条件
            page_size: 每页数量（默认 100）

        Returns:
            所有匹配的 Item 列表
        """
        all_items: list[Item] = []
        offset = 0
        while True:
            page_items = store.search(
                namespace,
                query=query,
                filter=filter,
                limit=page_size,
                offset=offset,
            )
            if not page_items:
                break
            all_items.extend(page_items)
            if len(page_items) < page_size:
                break
            offset += page_size

        return all_items

    def _search_store_paginated(                                                                                                                         
        self,                                                                                                                                            
        store: BaseStore,                                                                                                                                
        namespace: tuple[str, ...],                                                                                                                      
        *,                                                                                                                                               
        query: str | None = None,                                                                                                                        
        filter: dict[str, Any] | None = None,                                                                                                            
        page_size: int = 100,                                                                                                                            
    ) -> list[Item]:                                                                                                                                     
        """分页搜索 store，获取所有结果                                                                                                                  
                                                                                                                                                        
        Args:                                                                                                                                            
            store: 存储实例                                                                                                                              
            namespace: 命名空间前缀                                                                                                                      
            query: 可选的自然语言查询                                                                                                                    
            filter: 键值对过滤条件                                                                                                                       
            page_size: 每页数量（默认 100）                                                                                                              
                                                                                                                                                        
        Returns:                                                                                                                                         
            所有匹配的 Item 列表                                                                                                                         
        """                                                                                                                                              
        all_items: list[Item] = []                                                                                                                       
        offset = 0                                                                                                                                       
        while True:                                                                                                                                      
            page_items = store.search(                                                                                                                   
                namespace,                                                                                                                               
                query=query,                                                                                                                             
                filter=filter,                                                                                                                           
                limit=page_size,                                                                                                                         
                offset=offset,                                                                                                                           
            )                                                                                                                                            
            if not page_items:                                                                                                                           
                break                                                                                                                                    
            all_items.extend(page_items)                                                                                                                 
            if len(page_items) < page_size:                                                                                                              
                break                                                                                                                                    
            offset += page_size                                                                                                                          
                                                                                                                                                        
        return all_items


    # ls_info

    # read

    # write

    # edit

    # grep_raw

    # glob_info

    # upload_files

    # download_files
