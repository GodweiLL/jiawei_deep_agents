"""CompositeBackend: Route operations to different backends based on path prefix."""

from collections import defaultdict

from my_deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    SandboxBackendProtocol,
    WriteResult,
)
from my_deepagents.backends.state import StateBackend


class CompositeBackend:
    """根据路径前缀将操作路由到不同后端的后端.

    Example:
        ```python
        composite = CompositeBackend(
            default=StateBackend(runtime),
            routes={
                "/memories/": StoreBackend(runtime),
                "/workspace/": FilesystemBackend("/tmp/workspace", virtual_mode=True),
            }
        )
        # /memories/notes.txt -> StoreBackend with path /notes.txt
        # /workspace/code.py -> FilesystemBackend with path /code.py
        # /other.txt -> StateBackend with path /other.txt
        ```
    """

    def __init__(                                                                                                                                        
        self,                                                                                                                                            
        default: BackendProtocol | StateBackend,                                                                                                         
        routes: dict[str, BackendProtocol],                                                                                                              
    ) -> None:                                                                                                                                           
        """用默认的后端和路由初始化CompositeBackend.                                                                                  
                                                                                                                                                        
        Args:                                                                                                                                            
            default: Default backend for unmatched paths.                                                                                                
            routes: Dict mapping path prefixes to backends.                                                                                              
                    Prefixes should end with '/', e.g., "/memories/".                                                                                    
        """                                                                                                                                             
        # 默认后端                                                                                                                                       
        self.default = default                                                                                                                           
                                                                                                                                                        
        # 虚拟路由                                                                                                                                       
        self.routes = routes                                                                                                                             
                                                                                                                                                        
        # 按长度排序（最长优先）以确保正确的前缀匹配                                                                                                     
        self.sorted_routes = sorted(routes.items(), key=lambda x: len(x[0]), reverse=True)

    def _get_backend_and_key(self, key: str) -> tuple[BackendProtocol, str]:                                                                             
        """确定哪个后端处理此路径并去除前缀.                                                                                                             
                                                                                                                                                        
        Args:                                                                                                                                            
            key: 原始文件路径                                                                                                                            
                                                                                                                                                        
        Returns:                                                                                                                                         
            (backend, stripped_key) 元组，stripped_key 已去除路由前缀但保留前导斜杠                                                                      
            例如: "/memories/notes.txt" → (MemoriesBackend, "/notes.txt")                                                                                
                "/memories/" → (MemoriesBackend, "/")                                                                                                   
        """                                                                                                                                              
        # 按长度顺序检查路由（最长优先）                                                                                                                 
        for prefix, backend in self.sorted_routes:                                                                                                       
            if key.startswith(prefix):                                                                                                                   
                # 去除完整前缀并确保保留前导斜杠                                                                                                         
                suffix = key[len(prefix):]                                                                                                               
                stripped_key = f"/{suffix}" if suffix else "/"                                                                                           
                return backend, stripped_key                                                                                                             
                                                                                                                                                        
        return self.default, key

    def _sync_state_if_needed(self, files_update: dict | None) -> None:                                                                                  
        """如果有状态更新，同步到默认后端的 state.                                                                                                       
                                                                                                                                                        
        Args:                                                                                                                                            
            files_update: 需要更新的文件数据字典，为 None 则跳过                                                                                         
        """                                                                                                                                              
        if not files_update:                                                                                                                             
            return                                                                                                                                       
        try:                                                                                                                                             
            runtime = getattr(self.default, "runtime", None)                                                                                             
            if runtime is not None:                                                                                                                      
                state = runtime.state                                                                                                                    
                files = state.get("files", {})                                                                                                           
                files.update(files_update)                                                                                                               
                state["files"] = files                                                                                                                   
        except Exception:                                                                                                                                
            pass 

    def ls_info(self, path: str) -> list[FileInfo]:                                                                                                      
        """列出指定目录中的文件和目录（非递归）.                                                                                                         
                                                                                                                                                        
        Args:                                                                                                                                            
            path: 目录的绝对路径                                                                                                                         
                                                                                                                                                        
        Returns:                                                                                                                                         
            FileInfo 列表，路径已添加路由前缀                                                                                                            
        """                                                                                                                                              
        # 检查路径是否匹配特定路由                                                                                                                       
        for route_prefix, backend in self.sorted_routes:                                                                                                 
            if path.startswith(route_prefix.rstrip("/")):                                                                                                
                # 只查询匹配的路由后端                                                                                                                   
                suffix = path[len(route_prefix):]                                                                                                        
                search_path = f"/{suffix}" if suffix else "/"                                                                                            
                infos = backend.ls_info(search_path)                                                                                                     
                # 添加路由前缀到结果路径                                                                                                                 
                prefixed: list[FileInfo] = []                                                                                                            
                for fi in infos:                                                                                                                         
                    fi = dict(fi)                                                                                                                        
                    fi["path"] = f"{route_prefix[:-1]}{fi['path']}"                                                                                      
                    prefixed.append(fi)                                                                                                                  
                return prefixed                                                                                                                          
                                                                                                                                                        
        # 根目录：聚合默认后端和所有路由后端                                                                                                             
        if path == "/":                                                                                                                                  
            results: list[FileInfo] = []                                                                                                                 
            results.extend(self.default.ls_info(path))                                                                                                   
            for route_prefix, backend in self.sorted_routes:                                                                                             
                # 将路由本身作为目录添加（如 /memories/）                                                                                                
                results.append(                                                                                                                          
                    {                                                                                                                                    
                        "path": route_prefix,                                                                                                            
                        "is_dir": True,                                                                                                                  
                        "size": 0,                                                                                                                       
                        "modified_at": "",                                                                                                               
                    }                                                                                                                                    
                )                                                                                                                                        
            results.sort(key=lambda x: x.get("path", ""))                                                                                                
            return results                                                                                                                               
                                                                                                                                                        
        # 路径不匹配任何路由：只查询默认后端                                                                                                             
        return self.default.ls_info(path)

    def read(                                                                                                                                            
        self,                                                                                                                                            
        file_path: str,                                                                                                                                  
        offset: int = 0,                                                                                                                                 
        limit: int = 2000,                                                                                                                               
    ) -> str:                                                                                                                                            
        """读取文件内容，路由到对应后端.                                                                                                                 
                                                                                                                                                        
        Args:                                                                                                                                            
            file_path: 文件绝对路径                                                                                                                      
            offset: 起始行号（0-indexed）                                                                                                                
            limit: 最大读取行数                                                                                                                          
                                                                                                                                                        
        Returns:                                                                                                                                         
            带行号的文件内容，或错误信息                                                                                                                 
        """                                                                                                                                              
        backend, stripped_key = self._get_backend_and_key(file_path)                                                                                     
        return backend.read(stripped_key, offset=offset, limit=limit)

    def write(self, file_path: str, content: str) -> WriteResult:                                                                                        
        """创建新文件，路由到对应后端."""                                                                                                                
        backend, stripped_key = self._get_backend_and_key(file_path)                                                                                     
        res = backend.write(stripped_key, content)                                                                                                       
        self._sync_state_if_needed(res.files_update)                                                                                                     
        return res

    def edit(                                                                                                                                            
        self,                                                                                                                                            
        file_path: str,                                                                                                                                  
        old_string: str,                                                                                                                                 
        new_string: str,                                                                                                                                 
        replace_all: bool = False,                                                                                                                       
    ) -> EditResult:                                                                                                                                     
        """编辑文件，路由到对应后端."""                                                                                                                  
        backend, stripped_key = self._get_backend_and_key(file_path)                                                                                     
        res = backend.edit(stripped_key, old_string, new_string, replace_all=replace_all)                                                                
        self._sync_state_if_needed(res.files_update)                                                                                                     
        return res

    def grep_raw(                                                                                                                                        
        self,                                                                                                                                            
        pattern: str,                                                                                                                                    
        path: str | None = None,                                                                                                                         
        glob: str | None = None,                                                                                                                         
    ) -> list[GrepMatch] | str:                                                                                                                          
        """搜索文件内容，可跨多个后端聚合结果.                                                                                                           
                                                                                                                                                        
        Args:                                                                                                                                            
            pattern: 搜索的正则表达式                                                                                                                    
            path: 限定搜索路径（可选）                                                                                                                   
            glob: 文件名过滤模式（可选）                                                                                                                 
                                                                                                                                                        
        Returns:                                                                                                                                         
            GrepMatch 列表或错误字符串                                                                                                                   
        """                                                                                                                                              
        # 如果路径指向特定路由，只搜索该后端                                                                                                             
        for route_prefix, backend in self.sorted_routes:                                                                                                 
            if path is not None and path.startswith(route_prefix.rstrip("/")):                                                                           
                search_path = path[len(route_prefix) - 1:]                                                                                               
                raw = backend.grep_raw(pattern, search_path if search_path else "/", glob)                                                               
                if isinstance(raw, str):                                                                                                                 
                    return raw                                                                                                                           
                # 添加路由前缀到结果路径                                                                                                                 
                return [{**m, "path": f"{route_prefix[:-1]}{m['path']}"} for m in raw]                                                                   
                                                                                                                                                        
        # 否则，搜索默认后端和所有路由后端并合并                                                                                                         
        all_matches: list[GrepMatch] = []                                                                                                                
                                                                                                                                                        
        # 搜索默认后端                                                                                                                                   
        raw_default = self.default.grep_raw(pattern, path, glob)                                                                                         
        if isinstance(raw_default, str):                                                                                                                 
            return raw_default                                                                                                                           
        all_matches.extend(raw_default)                                                                                                                  
                                                                                                                                                        
        # 搜索所有路由后端                                                                                                                               
        for route_prefix, backend in self.routes.items():                                                                                                
            raw = backend.grep_raw(pattern, "/", glob)                                                                                                   
            if isinstance(raw, str):                                                                                                                     
                return raw                                                                                                                               
            all_matches.extend({**m, "path": f"{route_prefix[:-1]}{m['path']}"} for m in raw)                                                            
                                                                                                                                                        
        return all_matches

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:                                                                                
        """按模式搜索文件，可跨多个后端聚合结果.                                                                                                         
                                                                                                                                                        
        Args:                                                                                                                                            
            pattern: glob 模式（如 "*.py", "**/*.txt"）                                                                                                  
            path: 搜索起始路径                                                                                                                           
                                                                                                                                                        
        Returns:                                                                                                                                         
            匹配的 FileInfo 列表                                                                                                                         
        """                                                                                                                                              
        results: list[FileInfo] = []                                                                                                                     
                                                                                                                                                        
        # 基于路径路由，而非模式                                                                                                                         
        for route_prefix, backend in self.sorted_routes:                                                                                                 
            if path.startswith(route_prefix.rstrip("/")):                                                                                                
                search_path = path[len(route_prefix) - 1:]                                                                                               
                infos = backend.glob_info(pattern, search_path if search_path else "/")                                                                  
                return [{**fi, "path": f"{route_prefix[:-1]}{fi['path']}"} for fi in infos]                                                              
                                                                                                                                                        
        # 路径不匹配任何特定路由 - 搜索默认后端和所有路由后端                                                                                            
        results.extend(self.default.glob_info(pattern, path))                                                                                            
                                                                                                                                                        
        for route_prefix, backend in self.routes.items():                                                                                                
            infos = backend.glob_info(pattern, "/")                                                                                                      
            results.extend({**fi, "path": f"{route_prefix[:-1]}{fi['path']}"} for fi in infos)                                                           
                                                                                                                                                        
        # 确定性排序                                                                                                                                     
        results.sort(key=lambda x: x.get("path", ""))                                                                                                    
        return results

    def execute(self, command: str) -> ExecuteResponse:                                                                                                  
        """执行命令，委托给默认后端.                                                                                                                     
                                                                                                                                                        
        命令执行不是基于路径的，始终委托给默认后端。                                                                                                     
        默认后端必须实现 SandboxBackendProtocol。                                                                                                        
                                                                                                                                                        
        Args:                                                                                                                                            
            command: 要执行的 shell 命令                                                                                                                 
                                                                                                                                                        
        Returns:                                                                                                                                         
            ExecuteResponse 包含输出、退出码和截断标志                                                                                                   
                                                                                                                                                        
        Raises:                                                                                                                                          
            NotImplementedError: 如果默认后端不支持命令执行                                                                                              
        """                                                                                                                                              
        if isinstance(self.default, SandboxBackendProtocol):                                                                                             
            return self.default.execute(command)                                                                                                         
                                                                                                                                                        
        raise NotImplementedError(                                                                                                                       
            "默认后端不支持命令执行（SandboxBackendProtocol）. "                                                               
            "要启用执行，请提供实现 SandboxBackendProtocol 的默认后端。"                                                     
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:                                                                  
        """批量上传文件，按后端分组以提高效率.                                                                                                           
                                                                                                                                                        
        将文件按目标后端分组，每个后端只调用一次 upload_files。                                                                                          
                                                                                                                                                        
        Args:                                                                                                                                            
            files: (路径, 内容) 元组列表                                                                                                                 
                                                                                                                                                        
        Returns:                                                                                                                                         
            FileUploadResponse 列表，顺序与输入一致                                                                                                      
        """                                                                                                                                              
        # 预分配结果列表                                                                                                                                 
        results: list[FileUploadResponse | None] = [None] * len(files)                                                                                   
                                                                                                                                                        
        # 按后端分组，记录原始索引                                                                                                                       
        backend_batches: dict[BackendProtocol, list[tuple[int, str, bytes]]] = defaultdict(list)                                                         
                                                                                                                                                        
        for idx, (path, content) in enumerate(files):                                                                                                    
            backend, stripped_path = self._get_backend_and_key(path)                                                                                     
            backend_batches[backend].append((idx, stripped_path, content))                                                                               
                                                                                                                                                        
        # 处理每个后端的批次                                                                                                                             
        for backend, batch in backend_batches.items():                                                                                                   
            # 提取数据                                                                                                                                   
            indices, stripped_paths, contents = zip(*batch, strict=False)                                                                                
            batch_files = list(zip(stripped_paths, contents, strict=False))                                                                              
                                                                                                                                                        
            # 调用后端（每个后端只调用一次）                                                                                                             
            batch_responses = backend.upload_files(batch_files)                                                                                          
                                                                                                                                                        
            # 将响应放回原始位置，使用原始路径                                                                                                           
            for i, orig_idx in enumerate(indices):                                                                                                       
                results[orig_idx] = FileUploadResponse(                                                                                                  
                    path=files[orig_idx][0],  # 原始路径                                                                                                 
                    error=batch_responses[i].error if i < len(batch_responses) else None,                                                                
                )                                                                                                                                        
                                                                                                                                                        
        return results  # type: ignore[return-value]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:                                                                            
        """批量下载文件，按后端分组以提高效率.                                                                                                           
                                                                                                                                                        
        将路径按目标后端分组，每个后端只调用一次 download_files。                                                                                        
                                                                                                                                                        
        Args:                                                                                                                                            
            paths: 文件路径列表                                                                                                                          
                                                                                                                                                        
        Returns:                                                                                                                                         
            FileDownloadResponse 列表，顺序与输入一致                                                                                                    
        """                                                                                                                                              
        # 预分配结果列表                                                                                                                                 
        results: list[FileDownloadResponse | None] = [None] * len(paths)                                                                                 
                                                                                                                                                        
        # 按后端分组                                                                                                                                     
        backend_batches: dict[BackendProtocol, list[tuple[int, str]]] = defaultdict(list)                                                                
                                                                                                                                                        
        for idx, path in enumerate(paths):                                                                                                               
            backend, stripped_path = self._get_backend_and_key(path)                                                                                     
            backend_batches[backend].append((idx, stripped_path))                                                                                        
                                                                                                                                                        
        # 处理每个后端的批次                                                                                                                             
        for backend, batch in backend_batches.items():                                                                                                   
            # 提取数据                                                                                                                                   
            indices, stripped_paths = zip(*batch, strict=False)                                                                                          
                                                                                                                                                        
            # 调用后端（每个后端只调用一次）                                                                                                             
            batch_responses = backend.download_files(list(stripped_paths))                                                                               
                                                                                                                                                        
            # 将响应放回原始位置，使用原始路径                                                                                                           
            for i, orig_idx in enumerate(indices):                                                                                                       
                results[orig_idx] = FileDownloadResponse(                                                                                                
                    path=paths[orig_idx],  # 原始路径                                                                                                    
                    content=batch_responses[i].content if i < len(batch_responses) else None,                                                            
                    error=batch_responses[i].error if i < len(batch_responses) else None,                                                                
                )                                                                                                                                        
                                                                                                                                                        
        return results  # type: ignore[return-value]
