"""
审计日志中间件
符合银行合规要求：所有操作可追溯、不可篡改
"""

import logging
import json
import uuid
from datetime import datetime
from typing import Callable, Awaitable, Any, Dict, Optional
from fastapi import Request, Response
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from enterprise.models import AuditLog, User, Tenant

logger = logging.getLogger(__name__)


# ============================================================
# 审计日志记录器
# ============================================================

class AuditLogger:
    """审计日志记录器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        changes: Optional[Dict] = None,
        requires_review: bool = False,
    ) -> AuditLog:
        """记录审计日志"""
        audit_log = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            status=status,
            error_message=error_message,
            changes=changes,
            requires_review=requires_review,
        )
        self.db.add(audit_log)
        await self.db.flush()

        logger.info(
            f"Audit: action={action} user={user_id} resource={resource_type}:{resource_id} status={status}"
        )

        return audit_log

    async def log_login(
        self,
        user_id: str,
        tenant_id: str,
        ip_address: str,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> AuditLog:
        """记录登录审计"""
        return await self.log(
            action="login",
            resource_type="user",
            resource_id=user_id,
            user_id=user_id,
            tenant_id=tenant_id,
            ip_address=ip_address,
            status=status,
            error_message=error_message,
        )

    async def log_chat(
        self,
        user_id: str,
        tenant_id: str,
        session_id: str,
        message_count: int,
        token_used: int,
        ip_address: str,
    ) -> AuditLog:
        """记录对话审计"""
        return await self.log(
            action="chat",
            resource_type="session",
            resource_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            ip_address=ip_address,
            changes={
                "message_count": message_count,
                "token_used": token_used,
            },
        )

    async def log_data_export(
        self,
        user_id: str,
        tenant_id: str,
        resource_type: str,
        resource_id: str,
        ip_address: str,
    ) -> AuditLog:
        """记录数据导出审计（敏感操作）"""
        return await self.log(
            action="data_export",
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            tenant_id=tenant_id,
            ip_address=ip_address,
            requires_review=True,  # 数据导出需要复核
        )


# ============================================================
# 审计中间件
# ============================================================

async def audit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """
    审计中间件 - 记录所有 API 调用
    使用方法：
        app.add_middleware(AuditMiddleware)
    """
    # 生成请求 ID（用于链路追踪）
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    # 提取用户信息（从 JWT Token）
    user_id = None
    tenant_id = None
    # TODO: 从 request.state 或 JWT 中提取用户信息

    # 记录请求开始
    start_time = datetime.utcnow()

    # 执行请求
    response = await call_next(request)

    # 计算耗时
    duration = (datetime.utcnow() - start_time).total_seconds() * 1000

    # 记录审计日志（异步，不阻塞响应）
    # TODO: 使用后台任务记录审计日志

    # 添加响应头
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration:.2f}ms"

    return response


class AuditMiddleware:
    """审计中间件（FastAPI 兼容）"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # TODO: 实现 ASGI 中间件
        await self.app(scope, receive, send)


# ============================================================
# 审计日志查询
# ============================================================

class AuditLogQuery:
    """审计日志查询（用于合规报表）"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def query(
        self,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        status: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        requires_review: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """查询审计日志"""
        query = select(AuditLog)

        if tenant_id:
            query = query.where(AuditLog.tenant_id == tenant_id)
        if user_id:
            query = query.where(AuditLog.user_id == user_id)
        if action:
            query = query.where(AuditLog.action == action)
        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)
        if status:
            query = query.where(AuditLog.status == status)
        if start_time:
            query = query.where(AuditLog.created_at >= start_time)
        if end_time:
            query = query.where(AuditLog.created_at <= end_time)
        if requires_review is not None:
            query = query.where(AuditLog.requires_review == requires_review)

        query = query.order_by(AuditLog.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_compliance_report(
        self,
        tenant_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        """生成合规报告"""
        logs = await self.query(
            tenant_id=tenant_id,
            start_time=start_time,
            end_time=end_time,
            limit=10000,
        )

        # 统计
        total_operations = len(logs)
        failed_operations = sum(1 for log in logs if log.status == "failure")
        sensitive_operations = sum(1 for log in logs if log.requires_review)

        # 按操作类型分组
        by_action = {}
        for log in logs:
            by_action[log.action] = by_action.get(log.action, 0) + 1

        # 按用户分组
        by_user = {}
        for log in logs:
            if log.user_id:
                by_user[log.user_id] = by_user.get(log.user_id, 0) + 1

        return {
            "tenant_id": tenant_id,
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            "summary": {
                "total_operations": total_operations,
                "failed_operations": failed_operations,
                "sensitive_operations": sensitive_operations,
                "failure_rate": f"{failed_operations / total_operations * 100:.2f}%" if total_operations > 0 else "0%",
            },
            "by_action": by_action,
            "by_user": by_user,
            "logs": [{
                "id": log.id,
                "action": log.action,
                "user_id": log.user_id,
                "status": log.status,
                "created_at": log.created_at.isoformat(),
                "requires_review": log.requires_review,
            } for log in logs[:100]]  # 只返回前100条详情
        }
