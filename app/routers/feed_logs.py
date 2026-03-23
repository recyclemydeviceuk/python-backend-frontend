from fastapi import APIRouter, Depends, Query
from typing import Optional
from app.middleware.auth import get_current_admin
from app.models.feed_log import FeedLog
from app.utils.response import success_response

router = APIRouter(prefix="/feed-logs", tags=["Feed Logs"])


@router.get("", summary="Get feed access logs", dependencies=[Depends(get_current_admin)])
async def get_feed_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    endpoint: Optional[str] = None,
):
    skip = (page - 1) * limit
    
    filters = []
    if endpoint:
        filters.append(FeedLog.endpoint == endpoint)
    
    logs = await FeedLog.find(*filters).sort(-FeedLog.created_at).skip(skip).limit(limit).to_list()
    total = await FeedLog.find(*filters).count()
    
    logs_data = []
    for log in logs:
        logs_data.append({
            "id": str(log.id),
            "endpoint": log.endpoint,
            "source_ip": log.source_ip,
            "user_agent": log.user_agent,
            "partner_name": log.partner_name,
            "rows_returned": log.rows_returned,
            "query_params": log.query_params,
            "response_time_ms": log.response_time_ms,
            "created_at": log.created_at.isoformat(),
        })
    
    return success_response({
        "logs": logs_data,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit,
        }
    })


@router.get("/stats", summary="Get feed access statistics", dependencies=[Depends(get_current_admin)])
async def get_feed_stats():
    total_accesses = await FeedLog.count()
    
    pipeline = [
        {
            "$group": {
                "_id": "$endpoint",
                "count": {"$sum": 1},
                "total_rows": {"$sum": "$rows_returned"},
                "avg_response_time": {"$avg": "$response_time_ms"}
            }
        },
        {"$sort": {"count": -1}}
    ]
    
    endpoint_stats = await FeedLog.aggregate(pipeline).to_list()
    
    recent_logs = await FeedLog.find().sort(-FeedLog.created_at).limit(10).to_list()
    
    recent_data = []
    for log in recent_logs:
        recent_data.append({
            "endpoint": log.endpoint,
            "source_ip": log.source_ip,
            "rows_returned": log.rows_returned,
            "created_at": log.created_at.isoformat(),
        })
    
    return success_response({
        "total_accesses": total_accesses,
        "endpoint_stats": endpoint_stats,
        "recent_accesses": recent_data,
    })
