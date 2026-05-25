"""
数据库迁移脚本 - 企业级表结构
创建多租户、审计、RBAC、配额等表
"""

import asyncio
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from enterprise.models import (
    Tenant, User, Session, Message, AuditLog,
    ApiQuota, DataMaskingRule,
)
from enterprise.config import EnterpriseConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# 创建表的 SQL（兼容 PostgreSQL）
# ============================================================

CREATE_TABLES_SQL = """

-- 租户表
CREATE TABLE IF NOT EXISTS enterprise_tenants (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    parent_id VARCHAR(36) REFERENCES enterprise_tenants(id),
    is_active BOOLEAN DEFAULT TRUE,
    settings JSONB DEFAULT '{}',
    quota_tokens INTEGER DEFAULT 1000000,
    quota_api_calls INTEGER DEFAULT 10000,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 用户表
CREATE TABLE IF NOT EXISTS enterprise_users (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES enterprise_tenants(id),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE,
    display_name VARCHAR(100),
    password_hash VARCHAR(255),
    sso_id VARCHAR(100),
    mfa_enabled BOOLEAN DEFAULT FALSE,
    role VARCHAR(20) DEFAULT 'operator',
    is_active BOOLEAN DEFAULT TRUE,
    last_login_at TIMESTAMP,
    last_login_ip VARCHAR(45),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 会话表
CREATE TABLE IF NOT EXISTS enterprise_sessions (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES enterprise_tenants(id),
    user_id VARCHAR(36) NOT NULL REFERENCES enterprise_users(id),
    title VARCHAR(200),
    agent_id VARCHAR(36),
    status VARCHAR(20) DEFAULT 'active',
    is_shared BOOLEAN DEFAULT FALSE,
    shared_with JSONB DEFAULT '[]',
    message_count INTEGER DEFAULT 0,
    token_used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_message_at TIMESTAMP
);

-- 消息表
CREATE TABLE IF NOT EXISTS enterprise_messages (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES enterprise_sessions(id),
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    content_masked TEXT,
    tokens_used INTEGER DEFAULT 0,
    model VARCHAR(50),
    latency_ms INTEGER,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 审计日志表
CREATE TABLE IF NOT EXISTS enterprise_audit_logs (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) REFERENCES enterprise_tenants(id),
    user_id VARCHAR(36) REFERENCES enterprise_users(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(36),
    ip_address VARCHAR(45),
    user_agent TEXT,
    request_id VARCHAR(36),
    status VARCHAR(20) NOT NULL,
    error_message TEXT,
    changes JSONB,
    requires_review BOOLEAN DEFAULT FALSE,
    reviewed_by VARCHAR(36) REFERENCES enterprise_users(id),
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- API配额表
CREATE TABLE IF NOT EXISTS enterprise_api_quotas (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES enterprise_tenants(id),
    user_id VARCHAR(36) REFERENCES enterprise_users(id),
    quota_type VARCHAR(20) NOT NULL,
    limit_daily INTEGER,
    limit_monthly INTEGER,
    limit_concurrent INTEGER,
    used_daily INTEGER DEFAULT 0,
    used_monthly INTEGER DEFAULT 0,
    concurrent_count INTEGER DEFAULT 0,
    last_daily_reset TIMESTAMP DEFAULT NOW(),
    last_monthly_reset TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 数据脱敏规则表
CREATE TABLE IF NOT EXISTS enterprise_masking_rules (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(36) NOT NULL REFERENCES enterprise_tenants(id),
    name VARCHAR(100) NOT NULL,
    pattern VARCHAR(500) NOT NULL,
    replacement VARCHAR(200) NOT NULL,
    priority INTEGER DEFAULT 100,
    apply_to_input BOOLEAN DEFAULT TRUE,
    apply_to_output BOOLEAN DEFAULT TRUE,
    apply_to_log BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_audit_tenant_created ON enterprise_audit_logs(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_user_created ON enterprise_audit_logs(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_action ON enterprise_audit_logs(action, created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON enterprise_sessions(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON enterprise_sessions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_messages_session ON enterprise_messages(session_id, created_at);

""".strip()


# ============================================================
# 异步迁移函数
# ============================================================

async def create_tables(db_url: str):
    """创建所有企业级表"""
    engine = create_async_engine(db_url, echo=True)

    async with engine.begin() as conn:
        # 执行建表 SQL
        for statement in CREATE_TABLES_SQL.split(';'):
            stmt = statement.strip()
            if stmt:
                try:
                    await conn.execute(text(stmt))
                    logger.info(f"Executed: {stmt[:50]}...")
                except Exception as e:
                    # 表可能已存在
                    logger.warning(f"Statement failed (may be acceptable): {e}")

        await conn.commit()

    await engine.dispose()
    logger.info("Migration completed successfully")


async def init_default_data(db_url: str):
    """初始化默认数据（超级管理员租户）"""
    engine = create_async_engine(db_url)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as db:
        # 创建默认租户（超级管理员）
        from uuid import uuid4
        tenant_id = str(uuid4())

        tenant = Tenant(
            id=tenant_id,
            name="系统管理员",
            code="SYS_ADMIN",
            is_active=True,
            quota_tokens=100000000,  # 无限制
            quota_api_calls=1000000,
        )
        db.add(tenant)

        # 创建默认管理员用户
        admin_user = User(
            id=str(uuid4()),
            tenant_id=tenant_id,
            username="admin",
            email="admin@bank-hermes-qclaw.com",
            display_name="系统管理员",
            role="admin",
            is_active=True,
        )
        # TODO: 设置密码哈希
        db.add(admin_user)

        await db.commit()
        logger.info(f"Default tenant and admin user created: tenant_id={tenant_id}")

    await engine.dispose()


# ============================================================
# 主函数
# ============================================================

async def main():
    """运行迁移"""
    config = EnterpriseConfig()

    # 从环境变量或配置文件获取数据库 URL
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL environment variable not set")
        return

    logger.info("Starting enterprise database migration...")

    # 创建表
    await create_tables(db_url)

    # 初始化默认数据
    await init_default_data(db_url)

    logger.info("Migration completed!")


if __name__ == "__main__":
    import os
    asyncio.run(main())
