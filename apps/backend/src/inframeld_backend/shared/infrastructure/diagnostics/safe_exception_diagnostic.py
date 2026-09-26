"""Serialize exception structure without reading messages, local values, or source text.

Dictionaries here are the deliberate logging serialization boundary. These records
never cross an application contract, and only reviewed diagnostic fields are emitted.
"""

from itertools import islice
from traceback import walk_tb
from types import TracebackType
from typing import cast

from structlog.typing import ExcInfo

_MAX_EXCEPTION_FRAMES = 20
_MAX_EXCEPTION_DEPTH = 5
_MAX_EXCEPTION_GROUP_CHILDREN = 8
_MAX_EXCEPTION_NODES = 16


def _safe_exception_frames(
    traceback_value: TracebackType | None,
) -> tuple[list[dict[str, object]], bool]:
    """Extract bounded code locations without locals or source text.

    Args:
        traceback_value: Traceback whose frame locations should be recorded.

    Returns:
        The safe frame descriptions and whether additional frames were omitted.
    """
    captured = list(
        islice(
            walk_tb(traceback_value),
            _MAX_EXCEPTION_FRAMES + 1,
        )
    )

    frames: list[dict[str, object]] = []

    for frame, line_number in captured[:_MAX_EXCEPTION_FRAMES]:
        frames.append(
            {
                "filename": frame.f_code.co_filename,
                "function": frame.f_code.co_name,
                "lineno": line_number,
            }
        )

    return frames, len(captured) > _MAX_EXCEPTION_FRAMES


def build_safe_exception_diagnostic(exc_info: ExcInfo) -> dict[str, object]:
    """Build a bounded diagnostic containing only reviewed structural data.

    Exception messages, notes, local variables, source lines, and arbitrary
    object representations are deliberately never inspected or serialized.

    Args:
        exc_info: Exception information supplied by Structlog.

    Returns:
        A JSON-serializable diagnostic containing exception types, bounded
        frame locations, and bounded cause, context, and group relationships.
    """
    _, root_error, root_traceback = exc_info

    remaining_nodes = _MAX_EXCEPTION_NODES
    seen: set[int] = set()

    def visit(
        error: BaseException,
        traceback_value: TracebackType | None,
        depth: int,
    ) -> dict[str, object]:
        """Visit one exception without reading user-authored exception text."""
        nonlocal remaining_nodes

        if depth >= _MAX_EXCEPTION_DEPTH or remaining_nodes == 0:
            return {"truncated": True}

        error_identity = id(error)

        if error_identity in seen:
            return {"cycle": True}

        seen.add(error_identity)
        remaining_nodes -= 1

        frames, frames_truncated = _safe_exception_frames(traceback_value)

        node: dict[str, object] = {
            "type": type(error).__name__,
            "frames": frames,
        }

        if frames_truncated:
            node["frames_truncated"] = True

        cause = error.__cause__
        context = error.__context__

        if cause is not None:
            node["cause"] = visit(
                cause,
                cause.__traceback__,
                depth + 1,
            )
        elif context is not None and not error.__suppress_context__:
            node["context"] = visit(
                context,
                context.__traceback__,
                depth + 1,
            )

        if isinstance(error, BaseExceptionGroup):
            # isinstance() proves the runtime type, but Pyright cannot infer
            # BaseExceptionGroup's generic exception parameter.
            group_error = cast(BaseExceptionGroup[BaseException], error)
            group_exceptions = group_error.exceptions
            children = group_exceptions[:_MAX_EXCEPTION_GROUP_CHILDREN]

            node["exceptions"] = [
                visit(
                    child,
                    child.__traceback__,
                    depth + 1,
                )
                for child in children
            ]

            omitted_children = len(group_exceptions) - len(children)

            if omitted_children:
                node["exceptions_truncated"] = omitted_children

        return node

    return visit(
        root_error,
        root_traceback,
        depth=0,
    )
