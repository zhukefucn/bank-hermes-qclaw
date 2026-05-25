"""
企业级 API 接口
提供多租户管理、RBAC、审计日志、配额管理等接口
"""

import logging
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from enterprise.models import (
    Tenant, User, AuditLog, ApiQuota, DataMaskingRule,
)
from enterprise.rbac import (
    require_permission, PERM_MANAGE_TENANT, PERM_VIEW_AUDIT,
    PERM_EXPORT_DATA, PERM_MANAGE_USERS, PERM_VIEW_USAGE,
)
from enterprise.audit import AuditLogger, AuditLogQuery
from enterprise.quota import quota_manager, init_tenant_quota
from enterprise.masking import masking_manager, init_default_masking_rules
from enterprise.sso import sso_manager
from enterprise.config import get_enterprise_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enterprise", tags=["enterprise"])


# ============================================================
# 租户管理接口
# ============================================================

@router.get("/tenants", response_model=List[dict])
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_MANAGE_TENANT)),
):
    """列出所有租户（admin only）"""
    result = await db.execute(select(Tenant))
    tenants = result.scalars().all()
    return [{
        "id": t.id,
        "name": t.name,
        "code": t.code,
        "is_active": t.is_active,
        "quota_tokens": t.quota_tokens,
        "quota_api_calls": t.quota_api_calls,
        "created_at": t.created_at.isoformat(),
    } for t in tenants]


@router.post("/tenants", response_model=dict)
async def create_tenant(
    name: str,
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_MANAGE_TENANT)),
):
    """创建租户"""
    # 检查 code 唯一性
    result = await db.execute(select(Tenant).where(Tenant.code == code))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tenant code already exists")

    tenant = Tenant(
        name=name,
        code=code,
        is_active=True,
    )
    db.add(tenant)
    await db.flush()

    # 初始化配额
    await init_tenant_quota(db, tenant.id)

    # 初始化脱敏规则
    await init_default_masking_rules(db, tenant.id)

    # 记录审计日志
    audit_logger = AuditLogger(db)
    await audit_logger.log(
        action="tenant_create",
        resource_type="tenant",
        resource_id=tenant.id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
    )

    await db.commit()

    return {
        "id": tenant.id,
        "name": tenant.name,
        "code": tenant.code,
        "message": "Tenant created successfully",
    }


# ============================================================
# 用户管理接口
# ============================================================

@router.get("/users", response_model=List[dict])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_MANAGE_USERS)),
):
    """列出租户用户"""
    result = await db.execute(
        select(User).where(User.tenant_id == current_user.tenant_id)
    )
    users = result.scalars().all()
    return [{
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "display_name": u.display_name,
        "role": u.role,
        "is_active": u.is_active,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
    } for u in users]


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    new_role: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_MANAGE_USERS)),
):
    """更新用户角色"""
    # 验证角色合法
    valid_roles = ["admin", "manager", "operator", "viewer", "auditor"]
    if new_role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of {valid_roles}")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 只能修改同租户用户
    if user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Can only manage users in same tenant")

    old_role = user.role
    user.role = new_role
    await db.flush()

    # 记录审计日志
    audit_logger = AuditLogger(db)
    await audit_logger.log(
        action="user_role_update",
        resource_type="user",
        resource_id=user_id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        changes={"old_role": old_role, "new_role": new_role},
    )

    await db.commit()

    return {"message": f"User role updated to {new_role}"}


# ============================================================
# 审计日志接口
# ============================================================

@router.get("/audit/logs", response_model=List[dict])
async def query_audit_logs(
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    status: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_VIEW_AUDIT)),
):
    """查询审计日志"""
    query_tool = AuditLogQuery(db)
    logs = await query_tool.query(
        tenant_id=current_user.tenant_id,
        action=action,
        resource_type=resource_type,
        status=status,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    return [{
        "id": log.id,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "user_id": log.user_id,
        "status": log.status,
        "ip_address": log.ip_address,
        "created_at": log.created_at.isoformat(),
        "requires_review": log.requires_review,
    } for log in logs]


@router.get("/audit/compliance-report")
async def get_compliance_report(
    start_time: datetime,
    end_time: datetime,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_VIEW_AUDIT)),
):
    """生成合规报告"""
    query_tool = AuditLogQuery(db)
    report = await query_tool.get_compliance_report(
        tenant_id=current_user.tenant_id,
        start_time=start_time,
        end_time=end_time,
    )
    return report


# ============================================================
# 配额管理接口
# ============================================================

@router.get("/quota/status")
async def get_quota_status(
    quota_type: str = "token",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_VIEW_USAGE)),
):
    """获取配额状态"""
    status = await quota_manager.get_quota_status(
        db, current_user.tenant_id, quota_type
    )
    return status


@router.put("/quota/update")
async def update_quota(
    quota_type: str,
    limit_daily: Optional[int] = None,
    limit_monthly: Optional[int] = None,
    limit_concurrent: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_MANAGE_QUOTA)),
):
    """更新租户配额"""
    result = await db.execute(
        select(ApiQuota).where(
            ApiQuota.tenant_id == current_user.tenant_id,
            ApiQuota.quota_type == quota_type,
        )
    )
    quota = result.scalar_one_or_none()
    if not quota:
        raise HTTPException(status_code=404, detail="Quota not found")

    if limit_daily is not None:
        quota.limit_daily = limit_daily
    if limit_monthly is not None:
        quota.limit_monthly = limit_monthly
    if limit_concurrent is not None:
        quota.limit_concurrent = limit_concurrent

    await db.flush()

    # 记录审计日志
    audit_logger = AuditLogger(db)
    await audit_logger.log(
        action="quota_update",
        resource_type="quota",
        resource_id=quota.id,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        changes={
            "quota_type": quota_type,
            "limit_daily": limit_daily,
            "limit_monthly": limit_monthly,
            "limit_concurrent": limit_concurrent,
        },
    )

    await db.commit()

    return {"message": "Quota updated successfully"}


# ============================================================
# 数据脱敏规则接口
# ============================================================

@router.get("/masking/rules", response_model=List[dict])
async def list_masking_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_MANAGE_TENANT)),
):
    """列出脱敏规则"""
    result = await db.execute(
        select(DataMaskingRule).where(
            DataMaskingRule.tenant_id == current_user.tenant_id
        ).order_by(DataMaskingRule.priority)
    )
    rules = result.scalars().all()
    return [{
        "id": r.id,
        "name": r.name,
        "pattern": r.pattern,
        "replacement": r.replacement,
        "priority": r.priority,
        "apply_to_input": r.apply_to_input,
        "apply_to_output": r.apply_to_output,
        "apply_to_log": r.apply_to_log,
        "is_active": r.is_active,
    } for r in rules]


@router.post("/masking/rules", response_model=dict)
async def create_masking_rule(
    name: str,
    pattern: str,
    replacement: str,
    priority: int = 100,
    apply_to_input: bool = True,
    apply_to_output: bool = True,
    apply_to_log: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_MANAGE_TENANT)),
):
    """创建脱敏规则"""
    rule = DataMaskingRule(
        tenant_id=current_user.tenant_id,
        name=name,
        pattern=pattern,
        replacement=replacement,
        priority=priority,
        apply_to_input=apply_to_input,
        apply_to_output=apply_to_output,
        apply_to_log=apply_to_log,
        is_active=True,
    )
    db.add(rule)
    await db.flush()

    # 刷新脱敏处理器缓存
    await masking_manager.refresh_tenant(current_user.tenant_id)

    await db.commit()

    return {
        "id": rule.id,
        "message": "Masking rule created successfully",
    }


# ============================================================
# SSO 配置接口
# ============================================================

@router.get("/sso/config")
async def get_sso_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_MANAGE_TENANT)),
):
    """获取 SSO 配置（敏感信息掩码）"""
    config = get_enterprise_config()
    # 不返回敏感信息（client_secret 等）
    sso_config = config.SSO_CONFIG.copy()
    if "client_secret" in sso_config:
        sso_config["client_secret"] = "***masked***"
    if "bind_password" in sso_config:
        sso_config["bind_password"] = "***masked***"

    return {
        "sso_enabled": config.SSO_ENABLED,
        "sso_provider": config.SSO_PROVIDER,
        "sso_config": sso_config,
    }


@router.post("/sso/test")
async def test_sso_connection(
    provider_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PERM_MANAGE_TENANT)),
):
    """测试 SSO 连接"""
    provider = sso_manager.providers.get(provider_name)
    if not provider:
        raise HTTPException(status_code=404, detail=f"SSO provider not found: {provider_name}")

    # TODO: 实现连接测试
    return {
        "provider": provider_name,
        "status": "test_not_implemented",
    }


# ============================================================
# 依赖注入辅助函数
# ============================================================

async def get_db() -> AsyncSession:
    """获取数据库会话（占位符，需要与实际 db 模块集成）"""
    # TODO: 集成实际的 database session
    raise NotImplementedError("get_db not implemented")


# ============================================================
# 注册路由
# ============================================================

def register_enterprise_routes(app):
    """注册企业级路由到 FastAPI 应用"""
    app.include_router(router)
    logger.info("Enterprise routes registered")
