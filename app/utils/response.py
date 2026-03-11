from typing import Any, Optional
from fastapi.responses import JSONResponse


def success_response(data: Any = None, message: str = "Success", status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": True, "message": message, "data": data},
    )


def error_response(message: str = "Internal server error", status_code: int = 500, errors: Any = None) -> JSONResponse:
    content: dict = {"success": False, "error": message}
    if errors is not None:
        content["errors"] = errors
    return JSONResponse(status_code=status_code, content=content)


def created_response(data: Any = None, message: str = "Resource created successfully") -> JSONResponse:
    return success_response(data=data, message=message, status_code=201)


def paginated_response(
    data: Any,
    page: int,
    limit: int,
    total: int,
    message: str = "Success",
) -> JSONResponse:
    total_pages = (total + limit - 1) // limit
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": message,
            "data": data,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "totalPages": total_pages,
                "hasNextPage": page < total_pages,
                "hasPrevPage": page > 1,
            },
        },
    )
