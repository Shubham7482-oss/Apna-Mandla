from typing import Any, Dict, Optional


def standard_response(
    data: Any = None,
    message: str = "OK",
    success: bool = True,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Lightweight, backwards-friendly response envelope.

    NOTE:
    - Existing endpoints can gradually opt-in.
    - Shape keeps core payload under `data` and keeps a human
      readable `message` for clients already relying on it.
    """
    return {
        "success": success,
        "message": message,
        "data": data,
        "meta": meta or {},
    }


def error_response(
    message: str,
    status_code: int,
    error_code: Optional[str] = None,
    details: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Consistent error payload used by central exception handlers.
    """
    meta: Dict[str, Any] = {"status_code": status_code}
    if error_code:
        meta["error_code"] = error_code
    if details is not None:
        meta["details"] = details

    return standard_response(
        data=None,
        message=message,
        success=False,
        meta=meta,
    )

