"""
API 配额管理模块
支持多维度配额：租户级、用户级、接口级
支持每日/每月配额 + 并发控制
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_
from sqlalchemy.exc import IntegrityError

from enterprise.models import ApiQuota, Tenant, User, AuditLog

logger = logging.getLogger(__name__)


# ============================================================
# 配额管理器
# ============================================================

class QuotaManager:
    """配额管理器（单例）"""

    def __init__(self):
        self._cache: Dict[str, Dict] = {}  # tenant_id -> quota info
        self._concurrent_tracker: Dict[str, int] = {}  # tenant_id -> concurrent count

    async def check_quota(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: Optional[str] = None,
        quota_type: str = "token",
        amount: int = 1,
    ) -> Tuple[bool, str]:
        """
        检查配额是否充足
        返回：(allowed, reason)
        """
        # 1. 检查租户级配额
        tenant_quota = await self._get_tenant_quota(db, tenant_id, quota_type)

        if tenant_quota:
            # 检查每日配额
            if tenant_quota.limit_daily:
                if tenant_quota.used_daily + amount > tenant_quota.limit_daily:
                    await self._log_quota_exceeded(db, tenant_id, user_id, quota_type, "daily")
                    return False, f"Daily {quota_type} quota exceeded"

            # 检查每月配额
            if tenant_quota.limit_monthly:
                if tenant_quota.used_monthly + amount > tenant_quota.limit_monthly:
                    await self._log_quota_exceeded(db, tenant_id, user_id, quota_type, "monthly")
                    return False, f"Monthly {quota_type} quota exceeded"

            # 检查并发配额
            if tenant_quota.limit_concurrent:
                concurrent_key = f"{tenant_id}:{quota_type}"
                current_concurrent = self._concurrent_tracker.get(concurrent_key, 0)
                if current_concurrent >= tenant_quota.limit_concurrent:
                    return False, f"Concurrent {quota_type} limit reached"
                self._concurrent_tracker[concurrent_key] = current_concurrent + 1

        # 2. 检查用户级配额（如果有）
        if user_id:
            user_quota = await self._get_user_quota(db, tenant_id, user_id, quota_type)
            if user_quota:
                if user_quota.limit_daily and user_quota.used_daily + amount > user_quota.limit_daily:
                    return False, f"User daily {quota_type} quota exceeded"

        return True, ""

    async def consume_quota(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: Optional[str] = None,
        quota_type: str = "token",
        amount: int = 1,
    ) -> bool:
        """消费配额"""
        try:
            # 更新租户级配额
            result = await db.execute(
                select(ApiQuota).where(
                    and_(
                        ApiQuota.tenant_id == tenant_id,
                        ApiQuota.user_id.is_(None),
                        ApiQuota.quota_type == quota_type,
                    )
                )
            )
            quota = result.scalar_one_or_none()

            if quota:
                quota.used_daily += amount
                quota.used_monthly += amount

                # 重置检查
                await self._check_and_reset_quota(db, quota)

            # 更新用户级配额
            if user_id:
                result = await db.execute(
                    select(ApiQuota).where(
                        and_(
                            ApiQuota.tenant_id == tenant_id,
                            ApiQuota.user_id == user_id,
                            ApiQuota.quota_type == quota_type,
                        )
                    )
                )
                user_quota = result.scalar_one_or_none()

                if user_quota:
                    user_quota.used_daily += amount
                    user_quota.used_monthly += amount
                    await self._check_and_reset_quota(db, user_quota)

            await db.flush()
            return True

        except Exception as e:
            logger.error(f"Failed to consume quota: {e}")
            return False

    async def release_concurrent(
        self,
        tenant_id: str,
        quota_type: str = "token",
    ):
        """释放并发配额"""
        concurrent_key = f"{tenant_id}:{quota_type}"
        if concurrent_key in self._concurrent_tracker:
            self._concurrent_tracker[concurrent_key] = max(
                0, self._concurrent_tracker[concurrent_key] - 1
            )

    async def get_quota_status(
        self,
        db: AsyncSession,
        tenant_id: str,
        quota_type: str = "token",
    ) -> Dict:
        """获取配额状态"""
        result = await db.execute(
            select(ApiQuota).where(
                and_(
                    ApiQuota.tenant_id == tenant_id,
                    ApiQuota.user_id.is_(None),
                    ApiQuota.quota_type == quota_type,
                )
            )
        )
        quota = result.scalar_one_or_none()

        if not quota:
            return {
                "quota_type": quota_type,
                "limit_daily": None,
                "limit_monthly": None,
                "used_daily": 0,
                "used_monthly": 0,
                "remaining_daily": None,
                "remaining_monthly": None,
                "usage_percent_daily": 0,
                "usage_percent_monthly": 0,
            }

        return {
            "quota_type": quota_type,
            "limit_daily": quota.limit_daily,
            "limit_monthly": quota.limit_monthly,
            "used_daily": quota.used_daily,
            "used_monthly": quota.used_monthly,
            "remaining_daily": (quota.limit_daily - quota.used_daily) if quota.limit_daily else None,
            "remaining_monthly": (quota.limit_monthly - quota.used_monthly) if quota.limit_monthly else None,
            "usage_percent_daily": round(quota.used_daily / quota.limit_daily * 100, 2) if quota.limit_daily else 0,
            "usage_percent_monthly": round(quota.used_monthly / quota.limit_monthly * 100, 2) if quota.limit_monthly else 0,
        }

    # ============================================================
    # 内部方法
    # ============================================================

    async def _get_tenant_quota(
        self,
        db: AsyncSession,
        tenant_id: str,
        quota_type: str,
    ) -> Optional[ApiQuota]:
        """获取租户配额"""
        result = await db.execute(
            select(ApiQuota).where(
                and_(
                    ApiQuota.tenant_id == tenant_id,
                    ApiQuota.user_id.is_(None),
                    ApiQuota.quota_type == quota_type,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _get_user_quota(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        quota_type: str,
    ) -> Optional[ApiQuota]:
        """获取用户配额"""
        result = await db.execute(
            select(ApiQuota).where(
                and_(
                    ApiQuota.tenant_id == tenant_id,
                    ApiQuota.user_id == user_id,
                    ApiQuota.quota_type == quota_type,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _check_and_reset_quota(self, db: AsyncSession, quota: ApiQuota):
        """检查并重置配额（每日/每月）"""
        now = datetime.utcnow()

        # 每日重置
        if quota.last_daily_reset.date() < now.date():
            quota.used_daily = 0
            quota.last_daily_reset = now

        # 每月重置
        if quota.last_monthly_reset.month != now.month or quota.last_monthly_reset.year != now.year:
            quota.used_monthly = 0
            quota.last_monthly_reset = now

    async def _log_quota_exceeded(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: Optional[str],
        quota_type: str,
        period: str,  # daily/monthly
    ):
        """记录配额超限审计"""
        audit_log = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="quota_exceeded",
            resource_type="quota",
            status="failure",
            error_message=f"{quota_type} quota exceeded ({period})",
            created_at=datetime.utcnow(),
        )
        db.add(audit_log)
        await db.flush()


# 全局配额管理器实例
quota_manager = QuotaManager()


# ============================================================
# 配额装饰器
# ============================================================

def require_quota(quota_type: str = "token", amount: int = 1):
    """配额检查装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 从 kwargs 获取 db, tenant_id, user_id
            db = kwargs.get("db")
            tenant_id = kwargs.get("tenant_id")
            user_id = kwargs.get("user_id")

            if not db or not tenant_id:
                raise ValueError("db and tenant_id required for quota check")

            # 检查配额
            allowed, reason = await quota_manager.check_quota(
                db, tenant_id, user_id, quota_type, amount
            )

            if not allowed:
                raise PermissionError(f"Quota exceeded: {reason}")

            # 消费配额
            await quota_manager.consume_quota(
                db, tenant_id, user_id, quota_type, amount
            )

            try:
                return await func(*args, **kwargs)
            finally:
                # 释放并发配额
                await quota_manager.release_concurrent(tenant_id, quota_type)

        return wrapper
    return decorator


# ============================================================
# 初始化租户配额
# ============================================================

async def init_tenant_quota(
    db: AsyncSession,
    tenant_id: str,
    token_quota_daily: int = 100000,
    token_quota_monthly: int = 1000000,
    api_call_quota_daily: int = 1000,
    api_call_quota_monthly: int = 10000,
    concurrent_limit: int = 10,
):
    """为租户初始化配额"""
    # Token 配额
    token_quota = ApiQuota(
        tenant_id=tenant_id,
        quota_type="token",
        limit_daily=token_quota_daily,
        limit_monthly=token_quota_monthly,
        limit_concurrent=concurrent_limit,
        used_daily=0,
        used_monthly=0,
        concurrent_count=0,
    )
    db.add(token_quota)

    # API 调用配额
    api_call_quota = ApiQuota(
        tenant_id=tenant_id,
        quota_type="api_call",
        limit_daily=api_call_quota_daily,
        limit_monthly=api_call_quota_monthly,
        used_daily=0,
        used_monthly=0,
    )
    db.add(api_call_quota)

    await db.flush()
    logger.info(f"Initialized quota for tenant {tenant_id}")
