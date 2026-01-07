"""StateBackend: 将文件存储在 LangGraph 状态中（临时存储）"""

from typing import TYPE_CHECKING

from my_deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileInfo,
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

# TYPE_CHECKING 的作用：
# if TYPE_CHECKING:
#     from langchain.tools import ToolRuntime

# # TYPE_CHECKING 在运行时为 False，只在类型检查时为 True
# # 这样可以避免循环导入，同时保留类型提示

class StateBackend(BackendProtocol):
    """将文件存储在 Agent 状态中的后端
    
    特点：
    - 文件保存在 LangGraph 状态中
    - 单次对话内有效，跨对话不持久
    - 通过 Checkpointer 自动保存
    """

    def __init__(self, runtime: "ToolRuntime"):
        """初始化，接收 LangChain 的 ToolRuntime"""
        self.runtime = runtime

    def ls_info(self, path: str) -> list[FileInfo]:
        """列出目录内容（非递归）
        
        Args:
            path: 目录绝对路径
            
        Returns:
           目录下的文件和子目录列表
        """
        files = self.runtime.state.get("files", {})
        infos: list[FileInfo] = []
        subdirs: set[str] = set()

        # 规范化路径，确保以 / 结尾
        normalized_path = path if path.endswith("/") else path + "/"

        for k, fd in files.items():
            # 检查文件是否在指定目录下
            if not k.startswith(normalized_path):
                continue

            # 获取相对路径
            relative = k[len(normalized_path):]

            # 如果包含 /，说明在子目录中
            if "/" in relative:
                # Extract the immediate subdirectory name
                subdir_name = relative.split("/")[0]
                subdirs.add(normalized_path + subdir_name + "/")
                continue

            # 直接在当前目录的文件
            size = len("\n".join(fd.get("content", [])))
            infos.append({
                "path": k,
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

    # 核心逻辑图示：
    # state["files"] = {
    #     "/src/main.py": {...},
    #     "/src/utils/helper.py": {...},
    #     "/README.md": {...},
    # }

    # ls_info("/src/") 返回:
    # [
    #     {"path": "/src/main.py", "is_dir": False, ...},
    #     {"path": "/src/utils/", "is_dir": True, ...},  # 子目录
    # ]

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """读取文件内容（带行号）
        
        Args:
            file_path: 文件绝对路径
            offset: 起始行（0索引）
            limit: 最大行数
        """
        files = self.runtime.state.get("files", {})
        file_data = files.get(file_path)

        if file_data is None:
            return f"Error: File '{file_path}' not found"

        return format_read_response(file_data, offset, limit)

    def write(
          self,
          file_path: str,
          content: str,
      ) -> WriteResult:
          """创建新文件（文件已存在则报错）
          
          返回 WriteResult，包含 files_update 用于更新 LangGraph 状态
          """
          files = self.runtime.state.get("files", {})

          if file_path in files:
              return WriteResult(
                  error=f"Cannot write to {file_path} because it already exists. "
                        f"Read and then make an edit, or write to a new path."
              )

          new_file_data = create_file_data(content)
          return WriteResult(path=file_path, files_update={file_path: new_file_data})

    # 为什么返回 files_update 而不是直接修改状态？

    # # LangGraph 状态是不可变的，不能直接修改
    # self.runtime.state["files"][path] = data  # ❌ 错误

    # # 必须通过返回值告诉 LangGraph 如何更新状态
    # return WriteResult(files_update={path: data})  # ✅ 正确

    # # 中间件会处理这个返回值，用 Command 更新状态

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """编辑文件，替换字符串
        
        返回 EditResult，包含 files_update 和替换次数
        """
        files = self.runtime.state.get("files", {})
        file_data = files.get(file_path)

        if file_data is None:
            return EditResult(error=f"Error: File '{file_path}' not found")

        # 将 FileData 转为字符串
        content = file_data_to_string(file_data)

        # 执行替换
        result = perform_string_replacement(content, old_string, new_string, replace_all)

        # 检查是否出错（返回字符串表示错误）
        if isinstance(result, str):
            return EditResult(error=result)

        # 成功：更新文件数据
        new_content, occurrences = result
        new_file_data = update_file_data(file_data, new_content)

        return EditResult(
            path=file_path,
            files_update={file_path: new_file_data},
            occurrences=int(occurrences)
        )
    
    def grep_raw(
        self,
        pattern: str,
        path: str = "/",
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """搜索文件内容"""
        files = self.runtime.state.get("files", {})
        return grep_matches_from_files(files, pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """根据 glob 模式查找文件"""
        files = self.runtime.state.get("files", {})
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