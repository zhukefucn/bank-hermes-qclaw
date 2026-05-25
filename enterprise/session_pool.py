"""
会话池管理模块
支持会话共享、迁移、负载均衡
适用于多租户、多用户场景
"""

import logging
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_
from sqlalchemy.orm import relationship

from enterprise.models import Session, Message, User, Tenant, AuditLog

logger = logging.getLogger(__name__)


# ============================================================
# 会话池管理器
# ============================================================

class SessionPoolManager:
    """会话池管理器（单例）"""

    def __init__(self):
        self.active_sessions: Dict[str, Dict] = {}  # session_id -> session info
        self.user_sessions: Dict[str, List[str]] = {}  # user_id -> [session_ids]
        self.tenant_sessions: Dict[str, List[str]] = {}  # tenant_id -> [session_ids]

    async def create_session(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        title: Optional[str] = None,
        agent_id: Optional[str] = None,
        is_shared: bool = False,
    ) -> Session:
        """创建新会话"""
        session = Session(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            title=title or f"会话 {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
            agent_id=agent_id,
            status="active",
            is_shared=is_shared,
            message_count=0,
            token_used=0,
        )
        db.add(session)
        await db.flush()

        # 更新内存缓存
        self._update_cache(session)

        logger.info(f"Session created: {session.id} for user {user_id}")
        return session

    async def get_session(
        self,
        db: AsyncSession,
        session_id: str,
        user: Optional[User] = None,
    ) -> Optional[Session]:
        """获取会话（带权限检查）"""
        result = await db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            return None

        # 权限检查
        if user:
            if not await self._check_session_access(session, user):
                logger.warning(f"Access denied: user {user.id} to session {session_id}")
                return None

        # 更新缓存
        self._update_cache(session)

        return session

    async def list_user_sessions(
        self,
        db: AsyncSession,
        user: User,
        include_shared: bool = True,
    ) -> List[Session]:
        """列出用户的会话"""
        query = select(Session).where(
            Session.user_id == user.id,
            Session.status == "active",
        )

        if include_shared and user.role in ["manager", "admin"]:
            # 管理员可以看到共享会话
            query = select(Session).where(
                or_(
                    Session.user_id == user.id,
                    and_(Session.is_shared == True, Session.tenant_id == user.tenant_id),
                ),
                Session.status == "active",
            )

        query = query.order_by(Session.last_message.desc())
        result = await db.execute(query)
        return result.scalars().all()

    async def share_session(
        self,
        db: AsyncSession,
        session_id: str,
        shared_with: List[str],  # user IDs
        user: User,
    ) -> bool:
        """共享会话给指定用户"""
        session = await self.get_session(db, session_id, user)
        if not session:
            return False

        # 只有会话所有者或管理员可以共享
        if session.user_id != user.id and user.role not in ["admin", "manager"]:
            return False

        session.is_shared = True
        session.shared_with = shared_with
        await db.flush()

        # 记录审计日志
        audit_log = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="session_share",
            resource_type="session",
            resource_id=session_id,
            changes={"shared_with": shared_with},
        )
        db.add(audit_log)

        logger.info(f"Session {session_id} shared with {len(shared_with)} users")
        return True

    async def archive_session(
        self,
        db: AsyncSession,
        session_id: str,
        user: User,
    ) -> bool:
        """归档会话（软删除）"""
        session = await self.get_session(db, session_id, user)
        if not session:
            return False

        # 权限检查：只能归档自己的会话（管理员除外）
        if session.user_id != user.id and user.role not in ["admin", "manager"]:
            return False

        session.status = "archived"
        await db.flush()

        # 记录审计日志
        audit_log = AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="session_archive",
            resource_type="session",
            resource_id=session_id,
        )
        db.add(audit_log)

        # 更新缓存
        self._remove_from_cache(session.id)

        logger.info(f"Session {session_id} archived")
        return True

    async def add_message(
        self,
        db: AsyncSession,
        session_id: str,
        role: str,
        content: str,
        user: Optional[User] = None,
        tokens_used: int = 0,
        model: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Message:
        """添加消息到会话"""
        session = await self.get_session(db, session_id, user)
        if not session:
            raise ValueError(f"Session not found or access denied: {session_id}")

        # 数据脱敏（如果启用）
        content_masked = content
        # TODO: 调用 masking module

        message = Message(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            content_masked=content_masked,
            tokens_used=tokens_used,
            model=model,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(message)

        # 更新会话统计
        session.message_count += 1
        session.token_used += tokens_used
        session.last_message = datetime.utcnow()

        await db.flush()

        # 更新缓存
        self._update_cache(session)

        return message

    async def get_session_messages(
        self,
        db: AsyncSession,
        session_id: str,
        user: Optional[User] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Message]:
        """获取会话消息历史"""
        session = await self.get_session(db, session_id, user)
        if not session:
            return []

        query = (
            select(Message)
           .where(Message.session_id == session_id)
           .order_by(Message.created_at.asc())
           .limit(limit)
           .offset(offset)
        )
        result = await db.execute(query)
        return result.scalars().all()

    async def search_sessions(
        self,
        db: AsyncSession,
        user: User,
        keyword: Optional[str] = None,
        agent_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Session]:
        """搜索会话"""
        query = select(Session).where(
            Session.tenant_id == user.tenant_id,
            Session.status == "active",
        )

        # 权限过滤
        if user.role == "operator":
            query = query.where(
                or_(
                    Session.user_id == user.id,
                    Session.is_shared == True,
                )
            )
        elif user.role in ["manager", "admin"]:
            # 管理员可以看到所有租户会话
            pass

        # 关键词搜索（在消息内容中搜索）
        if keyword:
            # TODO: 实现全文搜索（可以使用 FTS 或向量搜索）
            pass

        if agent_id:
            query = query.where(Session.agent_id == agent_id)

        if start_time:
            query = query.where(Session.created_at >= start_time)
        if end_time:
            query = query.where(Session.created_at <= end_time)

        query = query.order_by(Session.last_message.desc())
        query = query.limit(limit).offset(offset)

        result = await db.execute(query)
        return result.scalars().all()

    # ============================================================
    # 会话迁移（负载均衡）
    # ============================================================

    async def migrate_session(
        self,
        db: AsyncSession,
        session_id: str,
        target_user_id: str,
        admin: User,
    ) -> bool:
        """迁移会话到另一个用户（管理员操作）"""
        if admin.role not in ["admin", "manager"]:
            return False

        session = await self.get_session(db, session_id, admin)
        if not session:
            return False

        # 验证目标用户存在且在同一租户
        result = await db.execute(
            select(User).where(
                User.id == target_user_id,
                User.tenant_id == admin.tenant_id,
            )
        )
        target_user = result.scalar_one_or_none()
        if not target_user:
            return False

        # 迁移
        old_user_id = session.user_id
        session.user_id = target_user_id

        # 记录审计日志
        audit_log = AuditLog(
            tenant_id=admin.tenant_id,
            user_id=admin.id,
            action="session_migrate",
            resource_type="session",
            resource_id=session_id,
            changes={
                "from_user": old_user_id,
                "to_user": target_user_id,
            },
            requires_review=True,  # 敏感操作需要复核
        )
        db.add(audit_log)

        await db.flush()
        self._update_cache(session)

        logger.info(f"Session {session_id} migrated from {old_user_id} to {target_user_id}")
        return True

    # ============================================================
    # 缓存管理
    # ============================================================

    def _update_cache(self, session: Session):
        """更新会话缓存"""
        self.active_sessions[session.id] = {
            "tenant_id": session.tenant_id,
            "user_id": session.user_id,
            "status": session.status,
            "message_count": session.message_count,
            "last_message": session.last_message,
        }

        # 更新用户会话索引
        if session.user_id not in self.user_sessions:
            self.user_sessions[session.user_id] = []
        if session.id not in self.user_sessions[session.user_id]:
            self.user_sessions[session.user_id].append(session.id)

        # 更新租户会话索引
        if session.tenant_id not in self.tenant_sessions:
            self.tenant_sessions[session.tenant_id] = []
        if session.id not in self.tenant_sessions[session.tenant_id]:
            self.tenant_sessions[session.tenant_id].append(session.id)

    def _remove_from_cache(self, session_id: str):
        """从缓存中移除会话"""
        if session_id in self.active_sessions:
            session_info = self.active_sessions[session_id]
            user_id = session_info.get("user_id")
            tenant_id = session_info.get("tenant_id")

            if user_id and user_id in self.user_sessions:
                self.user_sessions[user_id] = [
                    sid for sid in self.user_sessions[user_id] if sid != session_id
                ]

            if tenant_id and tenant_id in self.tenant_sessions:
                self.tenant_sessions[tenant_id] = [
                    sid for sid in self.tenant_sessions[tenant_id] if sid != session_id
                ]

            del self.active_sessions[session_id]

    async def _check_session_access(
        self,
        session: Session,
        user: User,
    ) -> bool:
        """检查用户是否有权访问会话"""
        # Admin 可以访问所有租户会话
        if user.role == "admin":
            return session.tenant_id == user.tenant_id

        # Manager 可以访问租户内所有会话
        if user.role == "manager":
            return session.tenant_id == user.tenant_id

        # Operator 只能访问自己的会话或共享会话
        if user.role == "operator":
            return (
                session.user_id == user.id
                or session.is_shared
                or (session.shared_with and user.id in (session.shared_with or []))
            )

        return False


# 全局会话池管理器实例
session_pool = SessionPoolManager()


# ============================================================
# 便捷函数
# ============================================================

async def create_session(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    title: Optional[str] = None,
    agent_id: Optional[str] = None,
    is_shared: bool = False,
) -> Session:
    """创建会话（便捷函数）"""
    return await session_pool.create_session(
        db, tenant_id, user_id, title, agent_id, is_shared
    )


async def get_session(
    db: AsyncSession,
    session_id: str,
    user: Optional[User] = None,
) -> Optional[Session]:
    """获取会话（便捷函数）"""
    return await session_pool.get_session(db, session_id, user)


async def add_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    user: Optional[User] = None,
    tokens_used: int = 0,
    model: Optional[str] = None,
) -> Message:
    """添加消息（便捷函数）"""
    return await session_pool.add_message(
        db, session_id, role, content, user, tokens_used, model
    )
