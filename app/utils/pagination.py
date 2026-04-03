from math import ceil
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


def paginate(items: list[Any], total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if total > 0 else 0,
    }
