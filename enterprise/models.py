"""
企业级数据模型
支持多租户、RBAC、审计日志、API配额
"""

from sqlalchemy import (
    Column, String, DateTime, Boolean, Text, Integer,
    ForeignKey, Index, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid


def generate_id() -> str:
    return str(uuid.uuid4())


# ============================================================
# 多租户模型
# ============================================================

class Tenant:
    """租户（银行分支机构/部门）"""
    __tablename__ = "enterprise_tenants"

    id = Column(String(36), primary_key=True, default=generate_id)
    name = Column(String(100), nullable=False)  # 分支行名称
    code = Column(String(50), unique=True, nullable=False)  # 机构代码
    parent_id = Column(String(36), ForeignKey("enterprise_tenants.id"))  # 上级机构

    # 配置
    is_active = Column(Boolean, default=True)
    settings = Column(JSON, default=dict)  # 自定义配置
    quota_tokens = Column(Integer, default=1000000)  # Token配额
    quota_api_calls = Column(Integer, default=10000)  # API调用配额

    # 审计
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关系
    users = relationship("User", back_populates="tenant")
    sessions = relationship("Session", back_populates="tenant")


class User:
    """用户（客户经理/管理员）"""
    __tablename__ = "enterprise_users"

    id = Column(String(36), primary_key=True, default=generate_id)
    tenant_id = Column(String(36), ForeignKey("enterprise_tenants.id"), nullable=False)

    # 身份信息
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True)
    display_name = Column(String(100))

    # 认证
    password_hash = Column(String(255))
    sso_id = Column(String(100))  # SSO唯一标识
    mfa_enabled = Column(Boolean, default=False)

    # 角色
    role = Column(String(20), default="operator")  # admin/manager/operator/viewer
    is_active = Column(Boolean, default=True)

    # 审计
    last_login_at = Column(DateTime)
    last_login_ip = Column(String(45))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关系
    tenant = relationship("Tenant", back_populates="users")
    sessions = relationship("Session", back_populates="user")


# ============================================================
# 会话池模型
# ============================================================

class Session:
    """会话池 - 支持会话共享和迁移"""
    __tablename__ = "enterprise_sessions"

    id = Column(String(36), primary_key=True, default=generate_id)
    tenant_id = Column(String(36), ForeignKey("enterprise_tenants.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("enterprise_users.id"), nullable=False)

    # 会话信息
    title = Column(String(200))
    agent_id = Column(String(36))  # 关联的Agent
    status = Column(String(20), default="active")  # active/archived/deleted

    # 共享
    is_shared = Column(Boolean, default=False)  # 是否团队共享
    shared_with = Column(JSON, default=list)  # 共享用户列表

    # 审计
    message_count = Column(Integer, default=0)
    token_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_message_at = Column(DateTime)

    # 关系
    tenant = relationship("Tenant", back_populates="sessions")
    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session")


class Message:
    """消息（支持审计和数据脱敏）"""
    __tablename__ = "enterprise_messages"

    id = Column(String(36), primary_key=True, default=generate_id)
    session_id = Column(String(36), ForeignKey("enterprise_sessions.id"), nullable=False)

    # 消息内容
    role = Column(String(20), nullable=False)  # user/assistant/system
    content = Column(Text, nullable=False)
    content_masked = Column(Text)  # 脱敏后的内容（用于审计日志）

    # 元数据
    tokens_used = Column(Integer, default=0)
    model = Column(String(50))
    latency_ms = Column(Integer)

    # 审计
    ip_address = Column(String(45))
    user_agent = Column(Text)
    created_at = Column(DateTime, default=func.now())

    # 关系
    session = relationship("Session", back_populates="messages")


# ============================================================
# 审计日志模型
# ============================================================

class AuditLog:
    """审计日志 - 符合银行合规要求"""
    __tablename__ = "enterprise_audit_logs"

    id = Column(String(36), primary_key=True, default=generate_id)
    tenant_id = Column(String(36), ForeignKey("enterprise_tenants.id"))
    user_id = Column(String(36), ForeignKey("enterprise_users.id"))

    # 操作信息
    action = Column(String(100), nullable=False)  # login/logout/chat/create_agent/...
    resource_type = Column(String(50))  # session/message/agent/user/tenant
    resource_id = Column(String(36))

    # 请求信息
    ip_address = Column(String(45))
    user_agent = Column(Text)
    request_id = Column(String(36))  # 链路追踪ID

    # 结果
    status = Column(String(20), nullable=False)  # success/failure/error
    error_message = Column(Text)

    # 数据变更（JSON Patch格式）
    changes = Column(JSON)

    # 敏感操作需要复核
    requires_review = Column(Boolean, default=False)
    reviewed_by = Column(String(36), ForeignKey("enterprise_users.id"))
    reviewed_at = Column(DateTime)

    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("idx_audit_tenant_created", "tenant_id", "created_at"),
        Index("idx_audit_user_created", "user_id", "created_at"),
        Index("idx_audit_action", "action", "created_at"),
    )


# ============================================================
# API配额管理模型
# ============================================================

class ApiQuota:
    """API配额管理"""
    __tablename__ = "enterprise_api_quotas"

    id = Column(String(36), primary_key=True, default=generate_id)
    tenant_id = Column(String(36), ForeignKey("enterprise_tenants.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("enterprise_users.id"))  # 可选，用户级配额

    # 配额类型
    quota_type = Column(String(20), nullable=False)  # token/api_call/tps

    # 限制
    limit_daily = Column(Integer)  # 每日限制
    limit_monthly = Column(Integer)  # 每月限制
    limit_concurrent = Column(Integer)  # 并发限制

    # 当前用量
    used_daily = Column(Integer, default=0)
    used_monthly = Column(Integer, default=0)
    concurrent_count = Column(Integer, default=0)

    # 重置时间
    last_daily_reset = Column(DateTime, default=func.now())
    last_monthly_reset = Column(DateTime, default=func.now())

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


# ============================================================
# 数据脱敏规则模型
# ============================================================

class DataMaskingRule:
    """数据脱敏规则"""
    __tablename__ = "enterprise_masking_rules"

    id = Column(String(36), primary_key=True, default=generate_id)
    tenant_id = Column(String(36), ForeignKey("enterprise_tenants.id"), nullable=False)

    # 规则定义
    name = Column(String(100), nullable=False)
    pattern = Column(String(500), nullable=False)  # 正则表达式
    replacement = Column(String(200), nullable=False)  # 替换模板
    priority = Column(Integer, default=100)  # 优先级（数字越小优先级越高）

    # 适用范围
    apply_to_input = Column(Boolean, default=True)  # 用户输入
    apply_to_output = Column(Boolean, default=True)  # AI输出
    apply_to_log = Column(Boolean, default=True)  # 审计日志

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
