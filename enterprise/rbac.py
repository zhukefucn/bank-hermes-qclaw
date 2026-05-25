"""
RBAC (Role-Based Access Control) - 角色权限控制
支持多租户、多级角色、细粒度权限
"""

from typing import Dict, List, Set, Callable, Any
from functools import wraps
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from enterprise.models import User, Tenant, Session, AuditLog


# ============================================================
# 权限定义
# ============================================================

# 权限常量
PERM_CHAT = "chat"
PERM_CREATE_AGENT = "agent:create"
PERM_EDIT_AGENT = "agent:edit"
PERM_DELETE_AGENT = "agent:delete"
PERM_VIEW_AGENTS = "agent:view"
PERM_MANAGE_TENANT = "tenant:manage"
PERM_VIEW_AUDIT = "audit:view"
PERM_EXPORT_DATA = "data:export"
PERM_MANAGE_USERS = "user:manage"
PERM_VIEW_USAGE = "usage:view"
PERM_MANAGE_QUOTA = "quota:manage"

# 角色权限映射
ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "admin": [  # 租户管理员（分行科技岗）
        PERM_CHAT,
        PERM_CREATE_AGENT,
        PERM_EDIT_AGENT,
        PERM_DELETE_AGENT,
        PERM_VIEW_AGENTS,
        PERM_MANAGE_TENANT,
        PERM_VIEW_AUDIT,
        PERM_EXPORT_DATA,
        PERM_MANAGE_USERS,
        PERM_VIEW_USAGE,
        PERM_MANAGE_QUOTA,
    ],
    "manager": [  # 部门经理
        PERM_CHAT,
        PERM_CREATE_AGENT,
        PERM_EDIT_AGENT,
        PERM_VIEW_AGENTS,
        PERM_VIEW_AUDIT,
        PERM_EXPORT_DATA,
        PERM_VIEW_USAGE,
    ],
    "operator": [  # 客户经理（普通用户）
        PERM_CHAT,
        PERM_VIEW_AGENTS,
    ],
    "viewer": [  # 只读用户
        PERM_VIEW_AGENTS,
        PERM_VIEW_USAGE,
    ],
    "auditor": [  # 审计员（合规岗）
        PERM_VIEW_AUDIT,
        PERM_EXPORT_DATA,
    ],
}


# ============================================================
# RBAC 管理器
# ============================================================

class RBACdManager:
    """RBAC 权限管理器"""

    def __init__(self):
        self.role_permissions: Dict[str, Set[str]] = {
            role: set(perms) for role, perms in ROLE_PERMISSIONS.items()
        }

    def get_permissions(self, role: str) -> Set[str]:
        """获取角色权限"""
        return self.role_permissions.get(role, set())

    def has_permission(self, role: str, permission: str) -> bool:
        """检查角色是否有某权限"""
        return permission in self.get_permissions(role)

    def add_permission(self, role: str, permission: str):
        """为角色添加权限"""
        if role not in self.role_permissions:
            self.role_permissions[role] = set()
        self.role_permissions[role].add(permission)

    def remove_permission(self, role: str, permission: str):
        """移除角色权限"""
        if role in self.role_permissions:
            self.role_permissions[role].discard(permission)

    def add_custom_role(self, role: str, permissions: List[str]):
        """添加自定义角色"""
        self.role_permissions[role] = set(permissions)


# 全局 RBAC 管理器
rbac_manager = RBACdManager()


# ============================================================
# 权限检查装饰器
# ============================================================

def require_permission(permission: str):
    """权限检查装饰器"""
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            # 从 kwargs 中获取 current_user
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=401, detail="Not authenticated")

            if not rbac_manager.has_permission(current_user.role, permission):
                raise HTTPException(
                    status_code=403,
                    detail=f"Permission denied: {permission} required"
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_any_permission(*permissions: str):
    """要求任意权限"""
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(status_code=401, detail="Not authenticated")

            has_any = any(
                rbac_manager.has_permission(current_user.role, perm)
                for perm in permissions
            )

            if not has_any:
                raise HTTPException(
                    status_code=403,
                    detail=f"Permission denied: one of {permissions} required"
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_admin(func: Callable) -> Callable:
    """要求 admin 角色"""
    return require_permission(PERM_MANAGE_TENANT)(func)


# ============================================================
# FastAPI 依赖注入
# ============================================================

async def get_current_user(request: Request, db: AsyncSession) -> User:
    """获取当前用户（FastAPI 依赖）"""
    # TODO: 从 JWT Token 或 SSO 中获取用户 ID
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    return user


async def require_perm(permission: str):
    """FastAPI 依赖：检查权限"""
    async def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if not rbac_manager.has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {permission} required"
            )
        return current_user
    return dependency


# ============================================================
# 数据隔离
# ============================================================

def filter_by_tenant(query, model, tenant_id: str):
    """为多租户查询添加租户过滤"""
    if hasattr(model, "tenant_id"):
        return query.where(model.tenant_id == tenant_id)
    return query


async def check_resource_access(
    db: AsyncSession,
    user: User,
    resource_type: str,
    resource_id: str,
) -> bool:
    """
    检查用户是否有权访问资源
    多级隔离：
    1. 租户隔离：只能访问本租户资源
    2. 用户隔离：只能访问自己的会话（除非 manager+）
    3. 共享资源：允许访问 is_shared=True 的资源
    """
    if resource_type == "session":
        result = await db.execute(
            select(Session).where(Session.id == resource_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return False

        # 租户隔离
        if session.tenant_id != user.tenant_id:
            return False

        # 用户隔离（operator 只能看自己的）
        if user.role == "operator":
            return session.user_id == user.id or session.is_shared

        return True

    return False


# ============================================================
# 审计日志集成
# ============================================================

async def log_permission_check(
    db: AsyncSession,
    user: User,
    permission: str,
    resource_type: str,
    resource_id: str,
    granted: bool,
):
    """记录权限检查审计"""
    audit_log = AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="permission_check",
        resource_type=resource_type,
        resource_id=resource_id,
        status="success" if granted else "denied",
        changes={"permission": permission},
    )
    db.add(audit_log)
    await db.flush()
