from fastapi import APIRouter, Depends, Query
from app.models.api_log import ApiLog
from app.middleware.auth import get_current_admin
from app.utils.response import success_response, paginated_response

router = APIRouter(prefix="/api-logs", tags=["API Logs"])


@router.get("", summary="Get API logs", dependencies=[Depends(get_current_admin)])
async def get_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    method: str = None,
    status_code: int = None,
):
    filters = []
    if method:
        filters.append(ApiLog.method == method.upper())
    if status_code:
        filters.append(ApiLog.status_code == status_code)

    q = ApiLog.find(*filters).sort(-ApiLog.created_at)
    total = await q.count()
    skip = (page - 1) * limit
    logs = await q.skip(skip).limit(limit).to_list()

    return paginated_response(
        [_serialize(l) for l in logs], page, limit, total
    )


@router.delete("", summary="Clear all API logs", dependencies=[Depends(get_current_admin)])
async def clear_logs():
    await ApiLog.find().delete()
    return success_response({"message": "All API logs cleared"})


def _serialize(l: ApiLog) -> dict:
    return {
        "id": str(l.id),
        "method": l.method,
        "path": l.path,
        "status_code": l.status_code,
        "ip_address": l.ip_address,
        "user_agent": l.user_agent,
        "partner_name": l.partner_name,
        "response_time_ms": l.response_time_ms,
        "created_at": l.created_at.isoformat(),
    }
