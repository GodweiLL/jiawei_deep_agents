import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import wcmatch.glob as wcglob

from my_deepagents.backends.protocol import FileInfo, GrepMatch

# 常量定义
EMPTY_CONTENT_WARNING = "System reminder: File exists but has empty contents"
MAX_LINE_LENGTH = 10000          # 单行最大字符数
LINE_NUMBER_WIDTH = 6            # 行号宽度
TOOL_RESULT_TOKEN_LIMIT = 20000  # token 限制
TRUNCATION_GUIDANCE = "... [results truncated, try being more specific with your parameters]"

def sanitize_tool_call_id(tool_call_id: str) -> str:
    """清理 tool_call_id，防止路径穿越攻击
    
    将危险字符 (., /, \) 替换为下划线
    """
    return tool_call_id.replace(".", "_").replace("/", "_").replace("\\", "_")

    # 为什么需要这个？
    # - tool_call_id 可能被用作文件名或路径的一部分
    # - 攻击者可能构造 ../../etc/passwd 这样的 id
    # - 替换危险字符可以防止路径穿越

def format_content_with_line_numbers(
    content: str | list[str],
    start_line: int = 1,
) -> str:
    """格式化文件内容，添加行号（类似 cat -n）
    
    超长行会被分块，使用续行标记（如 5.1, 5.2）
    """

    # 处理输入,字符串转列表
    if isinstance(content, str):
        lines = content.split("\n")
        # 移除末尾空行
        if lines and lines[-1] == "":
            lines = lines[:-1]
    else:
        lines = content

    # 结果行列表
    result_lines = []
    for i, line in enumerate(lines):
        line_num = i + start_line

        # 短行直接添加行号
        if len(line) <= MAX_LINE_LENGTH:
            result_lines.append(f"{line_num:{LINE_NUMBER_WIDTH}d}\t{line}")
        else:
            # 超长行分块，使用续行标记（如 5.1, 5.2）
            num_chunks = (len(line) + MAX_LINE_LENGTH - 1) // MAX_LINE_LENGTH
            for chunk_idx in range(num_chunks):
                start = chunk_idx * MAX_LINE_LENGTH
                end = min(start + MAX_LINE_LENGTH, len(line))
                chunk = line[start:end]
                if chunk_idx == 0:
                    # 第一块：使用正常行号
                    result_lines.append(f"{line_num:{LINE_NUMBER_WIDTH}d}\t{chunk}")
                else:
                    # 续行块：使用 decimal 标记（如 5.1, 5.2）
                    continuation_marker = f"{line_num}.{chunk_idx}"
                    result_lines.append(f"{continuation_marker:>{LINE_NUMBER_WIDTH}}\t{chunk}")

    return "\n".join(result_lines)

    #   格式化字符串语法：
    #   f"{line_num:{LINE_NUMBER_WIDTH}d}"
    #   #          ↑        ↑           ↑
    #   #          值      宽度(6)    十进制
    #   # 结果: "     1" (右对齐，宽度6)

def check_empty_content(content: str) -> str | None:
      """检查内容是否为空，返回警告信息"""
      if not content or content.strip() == "":
          return EMPTY_CONTENT_WARNING
      return None

def file_data_to_string(file_data: dict[str, Any]) -> str:
    """将 FileData 转换为字符串
    
    FileData 结构: {"content": ["line1", "line2"], ...}
    """
    return "\n".join(file_data["content"])


def create_file_data(content: str, created_at: str | None = None) -> dict[str, Any]:
    """创建 FileData 对象
    
    Args:
        content: 文件内容字符串
        created_at: 创建时间（可选）
    
    Returns:
        {"content": [...], "created_at": "...", "modified_at": "..."}
    """
    lines = content.split("\n") if isinstance(content, str) else content
    now = datetime.now(UTC).isoformat()

    return {
        "content": lines,
        "created_at": created_at or now,
        "modified_at": now,
    }


def update_file_data(file_data: dict[str, Any], content: str) -> dict[str, Any]:
    """更新 FileData，保留创建时间"""
    lines = content.split("\n") if isinstance(content, str) else content
    now = datetime.now(UTC).isoformat()

    return {
        "content": lines,
        "created_at": file_data["created_at"],  # 保留原创建时间
        "modified_at": now,
    }

# FileData 数据结构：
# {
#     "content": ["第一行", "第二行", "第三行"],  # 按行存储
#     "created_at": "2025-01-06T10:30:00+00:00",
#     "modified_at": "2025-01-06T11:00:00+00:00",
# }

def format_read_response(
    file_data: dict[str, Any],
    offset: int,
    limit: int,
  ) -> str:
    """格式化文件读取响应（带分页）
    
    Args:
        file_data: FileData 对象
        offset: 起始行（0索引）
        limit: 最大行数
    """
    content = file_data_to_string(file_data)

    # 检查空文件
    empty_msg = check_empty_content(content)
    if empty_msg:
        return empty_msg

    lines = content.splitlines()
    start_idx = offset
    end_idx = min(start_idx + limit, len(lines))

    # 检查偏移越界
    if start_idx >= len(lines):
        return f"Error: Line offset {offset} exceeds file length ({len(lines)} lines)"

    selected_lines = lines[start_idx:end_idx]
    return format_content_with_line_numbers(selected_lines, start_line=start_idx + 1)

def perform_string_replacement(
    content: str,
    old_string: str,
    new_string: str,
    replace_all: bool,
  ) -> tuple[str, int] | str:
    """执行字符串替换
    
    Args:
        content: 原始内容
        old_string: 要替换的字符串
        new_string: 替换后的字符串
        replace_all: 是否替换所有
        
    Returns:
        成功: (新内容, 替换次数)
        失败: 错误信息字符串
    """
    # 计算旧字符串出现次数
    occurrences = content.count(old_string)

    # 检查旧字符串是否存在
    if occurrences == 0:
        return f"Error: String not found in file: '{old_string}'"

    # 检查是否替换所有
    if occurrences > 1 and not replace_all:
        return (
            f"Error: String '{old_string}' appears {occurrences} times in file. "
            f"Use replace_all=True to replace all instances, "
            f"or provide a more specific string with surrounding context."
        )

    new_content = content.replace(old_string, new_string)
    return new_content, occurrences

def truncate_if_too_long(result: list[str] | str) -> list[str] | str:
    """截断过长的结果（粗略估计：4字符≈1token）"""
    if isinstance(result, list):
        total_chars = sum(len(item) for item in result)
        if total_chars > TOOL_RESULT_TOKEN_LIMIT * 4:
            # 按比例截断列表
            truncated_len = len(result) * TOOL_RESULT_TOKEN_LIMIT * 4 // total_chars
            return result[:truncated_len] + [TRUNCATION_GUIDANCE]
        return result

    # 字符串情况
    if len(result) > TOOL_RESULT_TOKEN_LIMIT * 4:
        return result[:TOOL_RESULT_TOKEN_LIMIT * 4] + "\n" + TRUNCATION_GUIDANCE
    return result

    # 为什么要截断？
    # - LLM 上下文有限
    # - 工具返回过长会挤占对话空间
    # - 粗略估计：4 个字符 ≈ 1 个 token

def _validate_path(path: str | None) -> str:
    """验证并规范化路径
    
    Returns:
        以 / 开头和结尾的规范化路径
        
    Raises:
        ValueError: 路径无效
    """
    path = path or "/"
    if not path or path.strip() == "":
        raise ValueError("Path cannot be empty")

    # 确保以 / 开头
    normalized = path if path.startswith("/") else "/" + path

    # 确保以 / 结尾（目录）
    if not normalized.endswith("/"):
        normalized += "/"

    return normalized

    # 下划线前缀 _ 的含义：
    # _validate_path  # 内部函数，不对外暴露
    # validate_path   # 公开函数

def _glob_search_files(
    files: dict[str, Any],
    pattern: str,
    path: str = "/",
) -> str:
    """在文件字典中搜索匹配 glob 模式的路径
    
    Args:
        files: {路径: FileData} 字典
        pattern: glob 模式，如 "*.py"
        path: 基础路径
        
    Returns:
        匹配的文件路径（按修改时间排序，最新的在前）
    """
    try:
        normalized_path = _validate_path(path)
    except ValueError:
        return "No files found"

    # 过滤出指定路径下的文件
    filtered = {fp: fd for fp, fd in files.items() if fp.startswith(normalized_path)}

    effective_pattern = pattern

    matches = []
    for file_path, file_data in filtered.items():
        # 获取相对路径
        relative = file_path[len(normalized_path):].lstrip("/")
        if not relative:
            relative = file_path.split("/")[-1]

        # 使用 wcmatch 进行 glob 匹配
        # BRACE: 支持 {a,b} 语法
        # GLOBSTAR: 支持 ** 递归匹配
        if wcglob.globmatch(relative, effective_pattern, flags=wcglob.BRACE | wcglob.GLOBSTAR):
            matches.append((file_path, file_data["modified_at"]))

    # 按修改时间降序排序
    matches.sort(key=lambda x: x[1], reverse=True)

    if not matches:
        return "No files found"

    return "\n".join(fp for fp, _ in matches)

    # wcglob.globmatch 参数说明：
    # | 标志     | 作用                       |
    # |----------|----------------------------|
    # | BRACE    | 支持 {py,js} 匹配 py 或 js |
    # | GLOBSTAR | 支持 ** 递归匹配目录       |

def _format_grep_results(
    results: dict[str, list[tuple[int, str]]],
    output_mode: Literal["files_with_matches", "content", "count"],
) -> str:
    """格式化 grep 搜索结果
    
    Args:
        results: {文件路径: [(行号, 内容), ...]}
        output_mode: 输出模式
    """
    if output_mode == "files_with_matches":
        # 只输出文件名
        return "\n".join(sorted(results.keys()))

    if output_mode == "count":
        # 输出匹配计数
        lines = []
        for file_path in sorted(results.keys()):
            count = len(results[file_path])
            lines.append(f"{file_path}: {count}")
        return "\n".join(lines)

    # content 模式：输出完整内容
    lines = []
    for file_path in sorted(results.keys()):
        lines.append(f"{file_path}:")
        for line_num, line in results[file_path]:
            lines.append(f"  {line_num}: {line}")
    return "\n".join(lines)

def _grep_search_files(
    files: dict[str, Any],
    pattern: str,
    path: str | None = None,
    glob: str | None = None,
    output_mode: Literal["files_with_matches", "content", "count"] = "files_with_matches",
) -> str:
    """在文件内容中搜索正则模式
    
    Args:
        files: {路径: FileData} 字典
        pattern: 正则表达式
        path: 基础搜索路径
        glob: 文件过滤模式
        output_mode: 输出格式
    """
    # 编译正则
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Invalid regex pattern: {e}"

    # 验证路径
    try:
        normalized_path = _validate_path(path)
    except ValueError:
        return "No matches found"

    # 过滤路径
    filtered = {fp: fd for fp, fd in files.items() if fp.startswith(normalized_path)}

    # 过滤文件类型
    if glob:
        filtered = {
            fp: fd for fp, fd in filtered.items()
            if wcglob.globmatch(Path(fp).name, glob, flags=wcglob.BRACE)
        }

    # 搜索内容
    results: dict[str, list[tuple[int, str]]] = {}
    for file_path, file_data in filtered.items():
        for line_num, line in enumerate(file_data["content"], 1):
            if regex.search(line):
                if file_path not in results:
                    results[file_path] = []
                results[file_path].append((line_num, line))

    if not results:
        return "No matches found"

    return _format_grep_results(results, output_mode)

# -------- Structured helpers for composition --------

def grep_matches_from_files(
    files: dict[str, Any],
    pattern: str,
    path: str | None = None,
    glob: str | None = None,
) -> list[GrepMatch] | str:
    """返回结构化的 grep 匹配结果
    
    与 _grep_search_files 不同，返回 list[GrepMatch] 而非格式化字符串。
    便于组合后端聚合结果。
    """
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Invalid regex pattern: {e}"

    try:
        normalized_path = _validate_path(path)
    except ValueError:
        return []

    filtered = {fp: fd for fp, fd in files.items() if fp.startswith(normalized_path)}

    if glob:
        filtered = {
            fp: fd for fp, fd in filtered.items()
            if wcglob.globmatch(Path(fp).name, glob, flags=wcglob.BRACE)
        }

    matches: list[GrepMatch] = []
    for file_path, file_data in filtered.items():
        for line_num, line in enumerate(file_data["content"], 1):
            if regex.search(line):
                matches.append({"path": file_path, "line": int(line_num), "text": line})

    return matches

def build_grep_results_dict(matches: list[GrepMatch]) -> dict[str, list[tuple[int, str]]]:
    """将结构化匹配转换为旧格式字典（供格式化函数使用）"""
    grouped: dict[str, list[tuple[int, str]]] = {}
    for m in matches:
        grouped.setdefault(m["path"], []).append((m["line"], m["text"]))
    return grouped


def format_grep_matches(
    matches: list[GrepMatch],
    output_mode: Literal["files_with_matches", "content", "count"],
) -> str:
    """格式化结构化的 grep 匹配结果"""
    if not matches:
        return "No matches found"
    return _format_grep_results(build_grep_results_dict(matches), output_mode)

# 为什么有两套 grep 函数？

# | 函数                    | 返回类型        | 用途             |
# |-------------------------|-----------------|------------------|
# | _grep_search_files      | str             | 直接给用户展示   |
# | grep_matches_from_files | list[GrepMatch] | 程序内部组合使用 |

# # CompositeBackend 需要聚合多个后端的结果
# results1 = backend1.grep_raw(...)  # list[GrepMatch]
# results2 = backend2.grep_raw(...)  # list[GrepMatch]
# combined = results1 + results2     # 可以直接合并！
# return format_grep_matches(combined, "content")  # 最后统一格式化