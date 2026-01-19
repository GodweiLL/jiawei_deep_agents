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

    def ls_info(self, path: str) -> list[FileInfo]:                                                                                                      
        """列出目录下的文件和子目录（非递归）                                                                                                            
                                                                                                                                                        
        Args:                                                                                                                                            
            path: 目录路径                                                                                                                               
                                                                                                                                                        
        Returns:                                                                                                                                         
            FileInfo 列表。目录以 / 结尾，is_dir=True                                                                                                    
        """                                                                                                                                              
        store = self._get_store()                                                                                                                        
        namespace = self._get_namespace()                                                                                                                
                                                                                                                                                        
        # 获取所有项目，本地过滤                                                                                                                         
        items = self._search_store_paginated(store, namespace)                                                                                           
        infos: list[FileInfo] = []                                                                                                                       
        subdirs: set[str] = set()                                                                                                                        
                                                                                                                                                        
        # 规范化路径，确保以 / 结尾                                                                                                                      
        normalized_path = path if path.endswith("/") else path + "/"                                                                                     
                                                                                                                                                        
        for item in items:                                                                                                                               
            # 检查文件是否在指定目录下                                                                                                                   
            if not str(item.key).startswith(normalized_path):                                                                                            
                continue                                                                                                                                 
                                                                                                                                                        
            # 获取相对路径                                                                                                                               
            relative = str(item.key)[len(normalized_path):]                                                                                              
                                                                                                                                                        
            # 如果包含 /，说明在子目录中                                                                                                                 
            if "/" in relative:                                                                                                                          
                subdir_name = relative.split("/")[0]                                                                                                     
                subdirs.add(normalized_path + subdir_name + "/")                                                                                         
                continue                                                                                                                                 
                                                                                                                                                        
            # 直接在当前目录的文件                                                                                                                       
            try:                                                                                                                                         
                fd = self._convert_store_item_to_file_data(item)                                                                                         
            except ValueError:                                                                                                                           
                continue                                                                                                                                 
            size = len("\n".join(fd.get("content", [])))                                                                                                 
            infos.append({                                                                                                                               
                "path": item.key,                                                                                                                        
                "is_dir": False,                                                                                                                         
                "size": int(size),                                                                                                                       
                "modified_at": fd.get("modified_at", ""),                                                                                                
            })                                                                                                                                           
                                                                                                                                                        
        # 添加子目录                                                                                                                                     
        for subdir in sorted(subdirs):                                                                                                                   
            infos.append({                                                                                                                               
                "path": subdir,                                                                                                                          
                "is_dir": True,                                                                                                                          
                "size": 0,                                                                                                                               
                "modified_at": "",                                                                                                                       
            })                                                                                                                                           
                                                                                                                                                        
        infos.sort(key=lambda x: x.get("path", ""))                                                                                                      
        return infos

    def read(                                                                                                                                            
        self,                                                                                                                                            
        file_path: str,                                                                                                                                  
        offset: int = 0,                                                                                                                                 
        limit: int = 2000,                                                                                                                               
    ) -> str:                                                                                                                                            
        """读取文件内容（带行号）                                                                                                                        
                                                                                                                                                        
        Args:                                                                                                                                            
            file_path: 文件路径                                                                                                                          
            offset: 起始行号（0-indexed）                                                                                                                
            limit: 最大读取行数                                                                                                                          
                                                                                                                                                        
        Returns:                                                                                                                                         
            带行号的文件内容，或错误信息                                                                                                                 
        """                                                                                                                                              
        store = self._get_store()                                                                                                                        
        namespace = self._get_namespace()                                                                                                                
        item: Item | None = store.get(namespace, file_path)                                                                                              
                                                                                                                                                        
        if item is None:                                                                                                                                 
            return f"Error: File '{file_path}' not found"                                                                                                
                                                                                                                                                        
        try:                                                                                                                                             
            file_data = self._convert_store_item_to_file_data(item)                                                                                      
        except ValueError as e:                                                                                                                          
            return f"Error: {e}"                                                                                                                         
                                                                                                                                                        
        return format_read_response(file_data, offset, limit) 

    def write(                                                                                                                                           
        self,                                                                                                                                            
        file_path: str,                                                                                                                                  
        content: str,                                                                                                                                    
    ) -> WriteResult:                                                                                                                                    
        """创建新文件                                                                                                                                    
                                                                                                                                                        
        Returns:                                                                                                                                         
            WriteResult，外部存储时 files_update=None                                                                                                    
        """                                                                                                                                              
        store = self._get_store()                                                                                                                        
        namespace = self._get_namespace()                                                                                                                
                                                                                                                                                        
        # 检查文件是否已存在                                                                                                                             
        existing = store.get(namespace, file_path)                                                                                                       
        if existing is not None:                                                                                                                         
            return WriteResult(error=f"Cannot write to {file_path} because it already exists. Read and then make an edit, or write to a new path.")      
                                                                                                                                                        
        # 创建新文件                                                                                                                                     
        file_data = create_file_data(content)                                                                                                            
        store_value = self._convert_file_data_to_store_value(file_data)                                                                                  
        store.put(namespace, file_path, store_value)                                                                                                     
        return WriteResult(path=file_path, files_update=None)

    def edit(                                                                                                                                            
        self,                                                                                                                                            
        file_path: str,                                                                                                                                  
        old_string: str,                                                                                                                                 
        new_string: str,                                                                                                                                 
        replace_all: bool = False,                                                                                                                       
    ) -> EditResult:                                                                                                                                     
        """编辑文件（字符串替换）                                                                                                                        
                                                                                                                                                        
        Returns:                                                                                                                                         
            EditResult，外部存储时 files_update=None                                                                                                     
        """                                                                                                                                              
        store = self._get_store()                                                                                                                        
        namespace = self._get_namespace()                                                                                                                
                                                                                                                                                        
        # 获取现有文件                                                                                                                                   
        item = store.get(namespace, file_path)                                                                                                           
        if item is None:                                                                                                                                 
            return EditResult(error=f"Error: File '{file_path}' not found")                                                                              
                                                                                                                                                        
        try:                                                                                                                                             
            file_data = self._convert_store_item_to_file_data(item)                                                                                      
        except ValueError as e:                                                                                                                          
            return EditResult(error=f"Error: {e}")                                                                                                       
                                                                                                                                                        
        content = file_data_to_string(file_data)                                                                                                         
        result = perform_string_replacement(content, old_string, new_string, replace_all)                                                                
                                                                                                                                                        
        if isinstance(result, str):                                                                                                                      
            return EditResult(error=result)                                                                                                              
                                                                                                                                                        
        new_content, occurrences = result                                                                                                                
        new_file_data = update_file_data(file_data, new_content)                                                                                         
                                                                                                                                                        
        # 更新文件到 store                                                                                                                               
        store_value = self._convert_file_data_to_store_value(new_file_data)                                                                              
        store.put(namespace, file_path, store_value)                                                                                                     
        return EditResult(path=file_path, files_update=None, occurrences=int(occurrences))

    def grep_raw(                                                                                                                                        
        self,                                                                                                                                            
        pattern: str,                                                                                                                                    
        path: str = "/",                                                                                                                                 
        glob: str | None = None,                                                                                                                         
    ) -> list[GrepMatch] | str:                                                                                                                          
        """搜索文件内容"""                                                                                                                               
        store = self._get_store()                                                                                                                        
        namespace = self._get_namespace()                                                                                                                
        items = self._search_store_paginated(store, namespace)                                                                                           
        files: dict[str, Any] = {}                                                                                                                       
        for item in items:                                                                                                                               
            try:                                                                                                                                         
                files[item.key] = self._convert_store_item_to_file_data(item)                                                                            
            except ValueError:                                                                                                                           
                continue                                                                                                                                 
        return grep_matches_from_files(files, pattern, path, glob) 

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:                                                                                
        """使用 glob 模式搜索文件"""                                                                                                                     
        store = self._get_store()                                                                                                                        
        namespace = self._get_namespace()                                                                                                                
        items = self._search_store_paginated(store, namespace)                                                                                           
        files: dict[str, Any] = {}                                                                                                                       
        for item in items:                                                                                                                               
            try:                                                                                                                                         
                files[item.key] = self._convert_store_item_to_file_data(item)                                                                            
            except ValueError:                                                                                                                           
                continue                                                                                                                                 
        result = _glob_search_files(files, pattern, path)                                                                                                
        if result == "No files found":                                                                                                                   
            return []                                                                                                                                    
        paths = result.split("\n")                                                                                                                       
        infos: list[FileInfo] = []                                                                                                                       
        for p in paths:                                                                                                                                  
            fd = files.get(p)                                                                                                                            
            size = len("\n".join(fd.get("content", []))) if fd else 0                                                                                    
            infos.append({                                                                                                                               
                "path": p,                                                                                                                               
                "is_dir": False,                                                                                                                         
                "size": int(size),                                                                                                                       
                "modified_at": fd.get("modified_at", "") if fd else "",                                                                                  
            })                                                                                                                                           
        return infos

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:                                                                  
        """上传多个文件到 store                                                                                                                          
                                                                                                                                                        
        Args:                                                                                                                                            
            files: [(路径, 二进制内容), ...] 列表                                                                                                        
                                                                                                                                                        
        Returns:                                                                                                                                         
            FileUploadResponse 列表，顺序与输入一致                                                                                                      
        """                                                                                                                                              
        store = self._get_store()                                                                                                                        
        namespace = self._get_namespace()                                                                                                                
        responses: list[FileUploadResponse] = []                                                                                                         
                                                                                                                                                        
        for path, content in files:                                                                                                                      
            content_str = content.decode("utf-8")                                                                                                        
            # 创建文件数据                                                                                                                               
            file_data = create_file_data(content_str)                                                                                                    
            store_value = self._convert_file_data_to_store_value(file_data)                                                                              
                                                                                                                                                        
            # 存储文件                                                                                                                                   
            store.put(namespace, path, store_value)                                                                                                      
            responses.append(FileUploadResponse(path=path, error=None))                                                                                  
                                                                                                                                                        
        return responses      

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:                                                                            
        """下载多个文件                                                                                                                                  
                                                                                                                                                        
        Args:                                                                                                                                            
            paths: 文件路径列表                                                                                                                          
                                                                                                                                                        
        Returns:                                                                                                                                         
            FileDownloadResponse 列表，顺序与输入一致                                                                                                    
        """                                                                                                                                              
        store = self._get_store()                                                                                                                        
        namespace = self._get_namespace()                                                                                                                
        responses: list[FileDownloadResponse] = []                                                                                                       
                                                                                                                                                        
        for path in paths:                                                                                                                               
            item = store.get(namespace, path)                                                                                                            
                                                                                                                                                        
            if item is None:                                                                                                                             
                responses.append(FileDownloadResponse(path=path, content=None, error="file_not_found"))                                                  
                continue                                                                                                                                 
                                                                                                                                                        
            file_data = self._convert_store_item_to_file_data(item)                                                                                      
            # 转换为 bytes                                                                                                                               
            content_str = file_data_to_string(file_data)                                                                                                 
            content_bytes = content_str.encode("utf-8")                                                                                                  
                                                                                                                                                        
            responses.append(FileDownloadResponse(path=path, content=content_bytes, error=None))                                                         
                                                                                                                                                        
        return responses 
