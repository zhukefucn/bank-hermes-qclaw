"""
企业级启动器
集成企业适配层到 Hermes Agent
"""

import logging
import os
from pathlib import Path

from hermes_constants import DEFAULT_PROFILE, PROFILES_DIR
from hermes_state import HermesState
from enterprise.config import get_enterprise_config
from enterprise.sso import sso_manager
from enterprise.audit import AuditLogger, audit_middleware
from enterprise.rbac import rbac_manager
from enterprise.masking import masking_manager
from enterprise.quota import quota_manager
from enterprise.session_pool import session_pool

logger = logging.getLogger(__name__)


# ============================================================
# 企业级 Hermes 启动器
# ============================================================

class EnterpriseHermesLauncher:
    """企业级 Hermes 启动器"""

    def __init__(self, profile_name: str = DEFAULT_PROFILE):
        self.profile_name = profile_name
        self.config = get_enterprise_config()
        self.state = None
        self._init_enterprise_features()

    def _init_enterprise_features(self):
        """初始化企业级功能"""
        logger.info("Initializing enterprise features...")

        # 1. 多租户支持
        if self.config.MULTI_TENANT_ENABLED:
            logger.info("✓ Multi-tenant support enabled")

        # 2. SSO 集成
        if self.config.SSO_ENABLED:
            self._init_sso()
            logger.info(f"✓ SSO integration enabled (provider: {self.config.SSO_PROVIDER})")

        # 3. 审计日志
        if self.config.AUDIT_ENABLED:
            logger.info("✓ Audit logging enabled")

        # 4. RBAC
        if self.config.RBAC_ENABLED:
            logger.info(f"✓ RBAC enabled (default role: {self.config.RBAC_DEFAULT_ROLE})")

        # 5. 数据脱敏
        if self.config.MASKING_ENABLED:
            logger.info("✓ Data masking enabled")

        # 6. API 配额
        if self.config.QUOTA_ENABLED:
            logger.info(f"✓ API quota management enabled (default daily: {self.config.QUOTA_DEFAULT_DAILY})")

        # 7. 会话池
        if self.config.SESSION_POOL_ENABLED:
            logger.info(f"✓ Session pool enabled (max messages: {self.config.SESSION_POOL_MAX_MESSAGES})")

        # 8. 银行模式
        if self.config.BANK_MODE:
            logger.info("✓ Bank mode enabled (enhanced compliance)")

        logger.info("Enterprise features initialized successfully")

    def _init_sso(self):
        """初始化 SSO 提供者"""
        if not self.config.SSO_PROVIDER:
            logger.warning("SSO enabled but no provider specified")
            return

        provider_name = self.config.SSO_PROVIDER.lower()

        if provider_name == "saml":
            from enterprise.sso import SAMLProvider
            provider = SAMLProvider(self.config.SSO_CONFIG)
            sso_manager.register_provider("saml", provider)

        elif provider_name == "oauth2":
            from enterprise.sso import OAuth2Provider
            provider = OAuth2Provider(self.config.SSO_CONFIG)
            sso_manager.register_provider("oauth2", provider)

        elif provider_name == "ldap":
            from enterprise.sso import LDAPProvider
            provider = LDAPProvider(self.config.SSO_CONFIG)
            sso_manager.register_provider("ldap", provider)

        elif provider_name == "wechat_work":
            from enterprise.sso import WeChatWorkProvider
            provider = WeChatWorkProvider(self.config.SSO_CONFIG)
            sso_manager.register_provider("wechat_work", provider)

        else:
            logger.error(f"Unknown SSO provider: {provider_name}")

    def launch(self):
        """启动 Hermes（企业版）"""
        logger.info("Launching Hermes Agent (Enterprise Edition)...")

        # 验证配置
        errors = self.config.validate()
        if errors:
            for err in errors:
                logger.error(f"Config validation error: {err}")
            raise ValueError("Enterprise config validation failed")

        # 加载 Hermes 状态
        self.state = HermesState(self.profile_name)

        # TODO: 集成 FastAPI 应用
        #  - 添加企业级中间件
        #  - 注册企业级路由
        #  - 配置 SSO
        #  - 启用审计日志

        logger.info("Hermes Agent (Enterprise Edition) launched successfully!")
        logger.info(f"Profile: {self.profile_name}")
        logger.info(f"Bank mode: {self.config.BANK_MODE}")

        return self.state

    def get_enterprise_info(self) -> dict:
        """获取企业级功能信息"""
        return {
            "version": "1.0.0",
            "bank_mode": self.config.BANK_MODE,
            "features": {
                "multi_tenant": self.config.MULTI_TENANT_ENABLED,
                "sso": self.config.SSO_ENABLED,
                "audit": self.config.AUDIT_ENABLED,
                "rbac": self.config.RBAC_ENABLED,
                "masking": self.config.MASKING_ENABLED,
                "quota": self.config.QUOTA_ENABLED,
                "session_pool": self.config.SESSION_POOL_ENABLED,
            },
            "compliance": {
                "audit_retention_days": self.config.AUDIT_RETENTION_DAYS,
                "data_retention_days": self.config.BANK_DATA_RETENTION_DAYS,
                "mfa_required": self.config.SECURITY_MFA_REQUIRED,
            }
        }


# ============================================================
# 与 Hermes 主程序集成
# ============================================================

def integrate_enterprise_with_hermes(app):
    """
    将企业级功能集成到 Hermes FastAPI 应用
    使用方法：
        from enterprise.launcher import integrate_enterprise_with_hermes
        app = FastAPI()
        integrate_enterprise_with_hermes(app)
    """
    config = get_enterprise_config()

    # 1. 添加审计中间件
    if config.AUDIT_ENABLED:
        app.add_middleware(AuditMiddleware)
        logger.info("✓ Audit middleware added")

    # 2. 注册企业级 API 路由
    from enterprise.api import router as enterprise_router
    app.include_router(enterprise_router)
    logger.info("✓ Enterprise API routes registered")

    # 3. 配置 CORS（企业级安全）
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("✓ CORS middleware configured")

    # 4. 添加启动事件
    @app.on_event("startup")
    async def startup_enterprise():
        logger.info("Enterprise startup tasks...")
        # TODO: 初始化数据库连接池
        # TODO: 加载 SSO 配置
        # TODO: 预热缓存
        logger.info("Enterprise startup completed")

    # 5. 添加关闭事件
    @app.on_event("shutdown")
    async def shutdown_enterprise():
        logger.info("Enterprise shutdown tasks...")
        # TODO: 关闭数据库连接池
        # TODO: 保存会话状态
        logger.info("Enterprise shutdown completed")

    logger.info("Enterprise integration completed successfully!")


# ============================================================
# 命令行入口
# ============================================================

def main():
    """企业级启动命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Bank Hermes QClaw - Enterprise Agent Platform")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Profile name")
    parser.add_argument("--bank-mode", action="store_true", help="Enable bank mode (enhanced compliance)")
    parser.add_argument("--sso-provider", help="SSO provider (saml/oauth2/ldap/wechat_work)")
    parser.add_argument("--info", action="store_true", help="Show enterprise info")
    args = parser.parse_args()

    # 设置环境变量
    if args.bank_mode:
        os.environ["BANK_MODE"] = "true"
    if args.sso_provider:
        os.environ["SSO_PROVIDER"] = args.sso_provider

    # 创建启动器
    launcher = EnterpriseHermesLauncher(args.profile)

    if args.info:
        # 显示企业级功能信息
        info = launcher.get_enterprise_info()
        print("\n=== Bank Hermes QClaw - Enterprise Edition ===")
        print(f"Version: {info['version']}")
        print(f"Bank Mode: {info['bank_mode']}")
        print("\nFeatures:")
        for feature, enabled in info['features'].items():
            print(f"  - {feature}: {'✓' if enabled else '✗'}")
        print(f"\nCompliance:")
        print(f"  - Audit retention: {info['compliance']['audit_retention_days']} days")
        print(f"  - Data retention: {info['compliance']['data_retention_days']} days")
        print(f"  - MFA required: {info['compliance']['mfa_required']}")
        print()
        return

    # 启动
    launcher.launch()


if __name__ == "__main__":
    main()
