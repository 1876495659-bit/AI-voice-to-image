"""栈式撤销/重做历史管理。

仅存储操作数据（每个 ~100 字节），而非像素快照。
50 条上限仅约 5KB，远低于像素快照方案。

引用: 设计源于 `engine/operations.py` 中定义的 DrawingOperation 数据类。
"""

from __future__ import annotations

from typing import List, Optional, TypeVar

from engine.operations import DrawingOperation

T = TypeVar("T", bound=DrawingOperation)


class UndoHistory:
    """基于双栈的撤销/重做管理器。

    Attributes:
        max_size: 历史上限，超过时自动淘汰最旧条目。默认 50。

    Attributes:
        _undo_stack: 正向操作栈，pop() = 撤销一步。
        _redo_stack: 反向操作栈，pop() = 重做一步。
    """

    def __init__(self, max_size: int = 50) -> None:
        self.max_size = max_size
        self._undo_stack: List[T] = []
        self._redo_stack: List[T] = []

    # --- 公共 API ---

    def push(self, operation: T) -> None:
        """压入一个新操作。

        压入操作后，redo 栈清空（新操作打断重做链）。
        如果历史已满，淘汰最旧的一条。
        """
        if len(self._undo_stack) >= self.max_size:
            self._undo_stack.pop(0)
        self._undo_stack.append(operation)
        self._redo_stack.clear()

    def push_multiple(self, operations: List[T]) -> None:
        """批量压入操作。

        同样清空 redo 栈。
        """
        for op in operations:
            self.push(op)

    def undo(self) -> Optional[T]:
        """撤销一步，返回被撤销的操作（用于重做栈压入）。

        Returns:
            被撤销的操作，历史为空时返回 None。
        """
        if not self._undo_stack:
            return None
        operation = self._undo_stack.pop()
        self._redo_stack.append(operation)
        return operation

    def redo(self) -> Optional[T]:
        """重做一步，返回被重做的操作（用于撤销栈压入）。

        Returns:
            被重做的操作，redo 栈为空时返回 None。
        """
        if not self._redo_stack:
            return None
        operation = self._redo_stack.pop()
        self._undo_stack.append(operation)
        return operation

    # --- 查询 ---

    def can_undo(self) -> bool:
        """是否还能撤销。"""
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        """是否还能重做。"""
        return len(self._redo_stack) > 0

    @property
    def undo_count(self) -> int:
        """当前撤销步数。"""
        return len(self._undo_stack)

    @property
    def redo_count(self) -> int:
        """当前重做步数。"""
        return len(self._redo_stack)

    def clear(self) -> None:
        """清空整个历史（清空画布时使用）。"""
        self._undo_stack.clear()
        self._redo_stack.clear()

    @property
    def history(self) -> List[T]:
        """只读的历史快照（用于调试/日志）。"""
        return list(self._undo_stack)
