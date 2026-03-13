from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime
from app.models.api_log import ApiLog
from app.middleware.auth import get_current_admin
from app.utils.response import success_response, paginated_response

router = APIRouter(prefix="/api-logs", tags=["API Logs"])


@router.get("", summary="Get API logs", dependencies=[Depends(get_current_admin)])
async def get_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    method: Optional[str] = None,
    status_code: Optional[int] = None,
    success: Optional[bool] = None,
    source_ip: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    filters = []
    if method:
        filters.append({"method": method.upper()})
    if status_code:
        filters.append({"$or": [{"status_code": status_code}, {"statusCode": status_code}]})
    if success is not None:
        filters.append({"success": success})
    if source_ip:
        filters.append({"$or": [{"source_ip": source_ip}, {"sourceIp": source_ip}, {"ip_address": source_ip}]})

    query = {"$and": filters} if filters else {}
    collection = ApiLog.get_motor_collection()
    total = await collection.count_documents(query)
    skip = (page - 1) * limit
    sort_dir = -1 if sort_order == "desc" else 1
    sort_field = {"created_at": "created_at", "createdAt": "createdAt", "timestamp": "timestamp"}.get(sort_by, sort_by)
    logs = await collection.find(query).sort(sort_field, sort_dir).skip(skip).limit(limit).to_list(length=limit)

    return paginated_response(
        [_serialize(l) for l in logs], page, limit, total
    )


@router.get("/stats", summary="Get API log stats", dependencies=[Depends(get_current_admin)])
async def get_log_stats():
    collection = ApiLog.get_motor_collection()
    total = await collection.count_documents({})
    successful = await collection.count_documents({"success": True})
    failed = total - successful
    all_logs = await collection.find({}).to_list(length=None)
    avg_response = round(sum((_raw_value(l, 'response_time_ms', 'response_time', 'responseTime') or 0) for l in all_logs) / total, 2) if total else 0
    return success_response({
        "totalRequests": total,
        "successfulRequests": successful,
        "failedRequests": failed,
        "successRate": f"{round(successful / total * 100, 1)}%" if total else "0%",
        "avgResponseTime": f"{avg_response}ms",
    })


@router.delete("", summary="Clear all API logs", dependencies=[Depends(get_current_admin)])
async def clear_logs():
    await ApiLog.find().delete()
    return success_response({"message": "All API logs cleared"})


def _raw_value(doc: dict, *keys: str):
    for key in keys:
        if key in doc and doc[key] is not None:
            return doc[key]
    return None


def _serialize(l) -> dict:
    is_raw = isinstance(l, dict)
    ts = _raw_value(l, 'created_at', 'createdAt', 'timestamp') if is_raw else getattr(l, 'created_at', None)
    if isinstance(ts, datetime):
        ts_value = ts.isoformat()
    else:
        ts_value = ts
    return {
        "id": str((l.get('_id') or l.get('id')) if is_raw else l.id), "_id": str((l.get('_id') or l.get('id')) if is_raw else l.id),
        "timestamp": ts_value,
        "created_at": ts_value,
        "createdAt": ts_value,
        "method": _raw_value(l, 'method') if is_raw else getattr(l, 'method', 'POST'),
        "endpoint": (_raw_value(l, 'path', 'endpoint') if is_raw else (getattr(l, 'path', '') or getattr(l, 'endpoint', ''))),
        "path": _raw_value(l, 'path') if is_raw else getattr(l, 'path', ''),
        "statusCode": (_raw_value(l, 'status_code', 'statusCode') if is_raw else getattr(l, 'status_code', 200)),
        "status_code": (_raw_value(l, 'status_code', 'statusCode') if is_raw else getattr(l, 'status_code', 200)),
        "sourceIp": (_raw_value(l, 'ip_address', 'source_ip', 'sourceIp') if is_raw else (getattr(l, 'ip_address', '') or getattr(l, 'source_ip', ''))),
        "source_ip": (_raw_value(l, 'ip_address', 'source_ip', 'sourceIp') if is_raw else (getattr(l, 'ip_address', '') or getattr(l, 'source_ip', ''))),
        "ip_address": (_raw_value(l, 'ip_address', 'source_ip', 'sourceIp') if is_raw else getattr(l, 'ip_address', '')),
        "success": _raw_value(l, 'success') if is_raw else getattr(l, 'success', False),
        "orderNumber": _raw_value(l, 'order_number', 'orderNumber') if is_raw else getattr(l, 'order_number', None),
        "order_number": _raw_value(l, 'order_number', 'orderNumber') if is_raw else getattr(l, 'order_number', None),
        "payload": _raw_value(l, 'payload') if is_raw else getattr(l, 'payload', None),
        "error": _raw_value(l, 'error') if is_raw else getattr(l, 'error', None),
        "responseTime": (_raw_value(l, 'response_time_ms', 'response_time', 'responseTime') if is_raw else getattr(l, 'response_time_ms', 0)),
        "response_time": (_raw_value(l, 'response_time_ms', 'response_time', 'responseTime') if is_raw else getattr(l, 'response_time_ms', 0)),
        "response_time_ms": (_raw_value(l, 'response_time_ms', 'response_time', 'responseTime') if is_raw else getattr(l, 'response_time_ms', 0)),
        "user_agent": _raw_value(l, 'user_agent') if is_raw else getattr(l, 'user_agent', None),
        "partner_name": _raw_value(l, 'partner_name', 'partnerName') if is_raw else getattr(l, 'partner_name', None),
        "partnerName": _raw_value(l, 'partner_name', 'partnerName') if is_raw else getattr(l, 'partner_name', None),
    }
