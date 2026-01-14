"""FilesystemBackend: 直接从文件系统读写文件

安全与搜索特性:
- 安全路径解析，virtual_mode 时沙盒到 cwd
- 使用 O_NOFOLLOW 防止符号链接攻击
- 支持 Ripgrep 搜索（带 Python 回退）
"""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

import wcmatch.glob as wcglob

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
    check_empty_content,
    format_content_with_line_numbers,
    perform_string_replacement,
)


# ============================================================
# FilesystemBackend 类
# ============================================================

class FilesystemBackend(BackendProtocol):
    """直接读写文件系统的后端

    文件使用实际文件系统路径访问。相对路径相对于当前工作目录解析。
    内容以纯文本读写，元数据（时间戳）来自文件系统 stat。
    """

    def __init__(
        self,
        root_dir: str | Path | None = None,
        virtual_mode: bool = False,
        max_file_size_mb: int = 10
    ) -> None:
        """
        初始化文件后端

      Args:
          root_dir: 可选的根目录。如果提供，所有文件路径都相对于此目录解析。
                    如果不提供，使用当前工作目录。
          virtual_mode: 虚拟模式，将 / 映射到 cwd，防止访问外部文件
          max_file_size_mb: 搜索时的最大文件大小限制（MB）
        """
        self.cwd = Path(root_dir).resolve() if root_dir else Path.cwd()
        self.virtual_mode = virtual_mode
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

    def _resolve_path(self, key: str) -> Path:
        """安全解析文件路径

        当 virtual_mode=True 时：
        - 将传入路径视为 self.cwd 下的虚拟绝对路径
        - 禁止路径遍历（.., ~）
        - 确保解析后的路径在根目录内

        当 virtual_mode=False 时：
        - 绝对路径直接使用
        - 相对路径相对于 cwd 解析

        Args:
            key: 文件路径

        Returns:
            解析后的绝对 Path 对象
        """
        if self.virtual_mode:
            # 虚拟模式：沙盒到cwd
            vpath = key if key.startswith("/") else "/" + key
            if ".." in vpath or vpath.startswith("~"):
                raise ValueError("Path traversal not allowed")
            full = (self.cwd / vpath.lstrip("/")).resolve()
            try:
                full.relative_to(self.cwd)
            except ValueError:
                raise ValueError(f"Path:{full} outside root directory: {self.cwd}") from None
            return full

        # 非虚拟模式：保持原有行为
        path = Path(key)
        if path.is_absolute():
            return path
        return (self.cwd / path).resolve()

    def ls_info(self, path: str = "/") -> list[FileInfo]:
        """列出目录下的文件和子目录（非递归）

        Args:
            path: 目录路径

        Returns:
            FileInfo 列表。目录路径以 / 结尾，is_dir=True
        """
        dir_path = self._resolve_path(path)
        if not dir_path.exists() or not dir_path.is_dir():
            return []
        results: list[FileInfo] = []
        cwd_str = str(self.cwd)
        if not cwd_str.endswith("/"):
            cwd_str += "/"
        # 列出直接子目录（非递归）
        try:
            for child_path in dir_path.iterdir():
                try:
                    is_file = child_path.is_file()
                    is_dir = child_path.is_dir()
                except OSError:
                    continue
                abs_path = str(child_path)

                if not self.virtual_mode:
                    # 非虚拟模式：使用绝对路径
                    if is_file:
                        try:
                            st = child_path.stat()
                            results.append(
                                {
                                    "path": abs_path,
                                    "is_dir": False,
                                    "size": int(st.st_size),
                                    "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
                                }
                            )
                        except OSError:
                            results.append({"path": abs_path, "is_dir": False})
                    elif is_dir:
                        try:
                            st = child_path.stat()
                            results.append(
                                {
                                    "path": abs_path + "/",
                                    "is_dir": True,
                                    "size": 0,
                                    "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
                                }
                            )
                        except OSError:
                            results.append({"path": abs_path + "/", "is_dir": True})
                else:
                    # 虚拟模式：去掉cwd前缀
                    if abs_path.startswith(cwd_str):
                        relative_path = abs_path[len(cwd_str) :]
                    elif abs_path.startswith(str(self.cwd)):
                        relative_path = abs_path[len(str(self.cwd)) :].lstrip("/")
                    else:
                        relative_path = abs_path
                    virt_path = "/" + relative_path
                    if is_file:
                        try:
                            st = child_path.stat()
                            results.append(
                                {
                                    "path": virt_path,
                                    "is_dir": False,
                                    "size": int(st.st_size),
                                    "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
                                }
                            )
                        except OSError:
                            results.append({"path": virt_path, "is_dir": False})
                    elif is_dir:
                        try:
                            st = child_path.stat()
                            results.append(
                                {
                                    "path": virt_path + "/",
                                    "is_dir": True,
                                    "size": 0,
                                    "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
                                }
                            )
                        except OSError:
                            results.append({"path": virt_path + "/", "is_dir": True})
        except (OSError, PermissionError):
            pass
        # 保持确定性顺序
        results.sort(key=lambda x: x.get("path", ""))
        return results

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
        resolved_path = self._resolve_path(file_path)

        if not resolved_path.exists() or not resolved_path.is_file():
            return f"Error: File '{file_path}' not found"
        try:
            # 使用 O_NOFOLLOW 避免符号链接攻击
            fd = os.open(resolved_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "r", encoding="utf-8") as f:
                content = f.read()

            empty_msg = check_empty_content(content)
            if empty_msg:
                return empty_msg

            lines = content.splitlines()
            start_idx = offset
            end_idx = min(start_idx + limit, len(lines))
            if start_idx >= len(lines):
                return f"Error: Line offset {offset} exceeds file length ({len(lines)} lines)"

            selected_lines = lines[start_idx:end_idx]
            return format_content_with_line_numbers(selected_lines, start_line=start_idx + 1)
        
        except (OSError, UnicodeDecodeError) as e:
            return f"Error reading file '{file_path}': {e}"

    def write(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        """创建新文件

        注意：只能创建新文件，不能覆盖已存在的文件
        
        Returns:
            WriteResult，外部存储时 files_update=None
        """
        resolved_path = self._resolve_path(file_path)

        if resolved_path.exists():
            return WriteResult(error=f"Cannot write to {file_path} because it already exists. Read and then make an edit, or write to a new path.")

        try:
            # 创建父目录（如果需要）
            resolved_path.parent.mkdir(parents=True, exist_ok=True)

            # 使用 O_NOFOLLOW 避免符号链接攻击
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(resolved_path, flags, 0o644)

            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)

            return WriteResult(path=file_path, files_update=None)
        except (OSError, UnicodeEncodeError) as e:
            return WriteResult(error=f"Error writing file '{file_path}': {e}")

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

        resolved_path = self._resolve_path(file_path)

        if not resolved_path.exists() or not resolved_path.is_file():
            return EditResult(error=f"Error: File '{file_path}' not found")
        
        try:
            # 安全读取
            fd = os.open(resolved_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "r", encoding="utf-8") as f:
                content = f.read()

            result = perform_string_replacement(content, old_string, new_string, replace_all)

            if isinstance(result, str):
                return EditResult(error=result)

            new_content, occurrences = result

            # 安全写入
            flags = os.O_WRONLY | os.O_TRUNC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(resolved_path, flags)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new_content)

            return EditResult(path=file_path, files_update=None, occurrences=int(occurrences))

        except (OSError, UnicodeDecodeError, UnicodeEncodeError) as e:
            return EditResult(error=f"Error editing file '{file_path}': {e}")

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """搜索文件内容

        Args:
            pattern: 正则表达式模式
            path: 搜索路径（默认当前目录）
            glob: 文件名过滤模式（如 "*.py"）

        Returns:
            GrepMatch 列表，或错误信息
        """

        # 验证正则表达式
        try:
            re.compile(pattern)
        except re.error as e:
            return f"Invalid regex pattern: {e}"
        
        # 解析基础路径
        try:
            base_full = self._resolve_path(path or ".")
        except ValueError:
            return []

        if not base_full.exists():
            return []

        # 优先尝试 ripgrep,失败则用 python
        results = self._ripgrep_search(pattern, base_full, glob)
        if results is None:
            results = self._python_search(pattern, base_full, glob)

        matches: list[GrepMatch] = []
        for fpath, items in results.items():
            for line_num, line_text in items:
                matches.append({"path": fpath, "line": int(line_num), "text": line_text})
        return matches

    def _ripgrep_search(
        self,
        pattern: str,
        base_full: Path,
        include_glob: str | None,
    ) -> dict[str, list[tuple[int, str]]] | None:
        """使用 ripgrep 搜索

        Returns:
            搜索结果字典，或 None（ripgrep 不可用时）
        """
        cmd = ["rg", "--json"]
        if include_glob:
            cmd.extend(["--glob", include_glob])
        cmd.extend(["--", pattern, str(base_full)])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

        results: dict[str, list[tuple[int, str]]] = {}
        for line in proc.stdout.splitlines():
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("type") != "match":
                continue
            pdata = data.get("data", {})
            ftext = pdata.get("path", {}).get("text")
            if not ftext:
                continue
            p = Path(ftext)
            if self.virtual_mode:
                try:
                    virt = "/" + str(p.resolve().relative_to(self.cwd))
                except Exception:
                    continue
            else:
                virt = str(p)
            ln = pdata.get("line_number")
            lt = pdata.get("lines", {}).get("text", "").rstrip("\n")
            if ln is None:
                continue
            results.setdefault(virt, []).append((int(ln), lt))

        return results

        
    def _python_search(
        self,
        pattern: str,
        base_full: Path,
        include_glob: str | None,
    ) -> dict[str, list[tuple[int, str]]]:
        """纯 Python 搜索（ripgrep 不可用时的回退方案）"""
        try:
            regex = re.compile(pattern)
        except re.error:
            return {}

        results: dict[str, list[tuple[int, str]]] = {}
        root = base_full if base_full.is_dir() else base_full.parent

        for fp in root.rglob("*"):
            if not fp.is_file():
                continue
            # glob 过滤
            if include_glob and not wcglob.globmatch(fp.name, include_glob, flags=wcglob.BRACE):
                continue
            # 跳过大文件
            try:
                if fp.stat().st_size > self.max_file_size_bytes:
                    continue
            except OSError:
                continue
            # 读取并搜索
            try:
                content = fp.read_text()
            except (UnicodeDecodeError, PermissionError, OSError):
                continue
            for line_num, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    if self.virtual_mode:
                        try:
                            virt_path = "/" + str(fp.resolve().relative_to(self.cwd))
                        except Exception:
                            continue
                    else:
                        virt_path = str(fp)
                    results.setdefault(virt_path, []).append((line_num, line))

        return results

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """使用 glob 模式搜索文件

        Args:
            pattern: glob 模式（如 "*.py", "**/*.txt"）
            path: 搜索起始路径

        Returns:
            匹配的 FileInfo 列表
        """
        if pattern.startswith("/"):
            pattern = pattern.lstrip("/")

        search_path = self.cwd if path == "/" else self._resolve_path(path)
        if not search_path.exists() or not search_path.is_dir():
            return []

        results: list[FileInfo] = []
        try:
            for matched_path in search_path.rglob(pattern):
                try:
                    is_file = matched_path.is_file()
                except OSError:
                    continue
                if not is_file:
                    continue
                abs_path = str(matched_path)
                if not self.virtual_mode:
                    try:
                        st = matched_path.stat()
                        results.append({
                            "path": abs_path,
                            "is_dir": False,
                            "size": int(st.st_size),
                            "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
                        })
                    except OSError:
                        results.append({"path": abs_path, "is_dir": False})
                else:
                    cwd_str = str(self.cwd)
                    if not cwd_str.endswith("/"):
                        cwd_str += "/"
                    if abs_path.startswith(cwd_str):
                        relative_path = abs_path[len(cwd_str):]
                    elif abs_path.startswith(str(self.cwd)):
                        relative_path = abs_path[len(str(self.cwd)):].lstrip("/")
                    else:
                        relative_path = abs_path
                    virt = "/" + relative_path
                    try:
                        st = matched_path.stat()
                        results.append({
                            "path": virt,
                            "is_dir": False,
                            "size": int(st.st_size),
                            "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
                        })
                    except OSError:
                        results.append({"path": virt, "is_dir": False})
        except (OSError, ValueError):
            pass

        results.sort(key=lambda x: x.get("path", ""))
        return results

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """上传多个文件到文件系统

        Args:
            files: [(路径, 二进制内容), ...] 列表

        Returns:
            FileUploadResponse 列表，顺序与输入一致
        """
        responses: list[FileUploadResponse] = []
        for path, content in files:
            try:
                resolved_path = self._resolve_path(path)

                # 创建父目录
                resolved_path.parent.mkdir(parents=True, exist_ok=True)

                flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                fd = os.open(resolved_path, flags, 0o644)
                with os.fdopen(fd, "wb") as f:
                    f.write(content)

                responses.append(FileUploadResponse(path=path, error=None))
            except FileNotFoundError:
                responses.append(FileUploadResponse(path=path, error="file_not_found"))
            except PermissionError:
                responses.append(FileUploadResponse(path=path, error="permission_denied"))
            except (ValueError, OSError) as e:
                if isinstance(e, ValueError) or "invalid" in str(e).lower():
                    responses.append(FileUploadResponse(path=path, error="invalid_path"))
                else:
                    responses.append(FileUploadResponse(path=path, error="invalid_path"))

        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """下载多个文件

        Args:
            paths: 文件路径列表

        Returns:
            FileDownloadResponse 列表，顺序与输入一致
        """
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                resolved_path = self._resolve_path(path)
                # 使用 O_NOFOLLOW 防止符号链接攻击
                fd = os.open(resolved_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(fd, "rb") as f:
                    content = f.read()
                responses.append(FileDownloadResponse(path=path, content=content, error=None))
            except FileNotFoundError:
                responses.append(FileDownloadResponse(path=path, content=None, error="file_not_found"))
            except PermissionError:
                responses.append(FileDownloadResponse(path=path, content=None, error="permission_denied"))
            except IsADirectoryError:
                responses.append(FileDownloadResponse(path=path, content=None, error="is_directory"))
            except ValueError:
                responses.append(FileDownloadResponse(path=path, content=None, error="invalid_path"))
        return responses
