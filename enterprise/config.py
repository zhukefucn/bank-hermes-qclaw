"""
企业级配置管理
支持多租户配置、SSO 配置、审计配置等
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)


# ============================================================
# 企业级配置类
# ============================================================

class EnterpriseConfig:
    """企业级配置"""

    def __init__(self):
        # 多租户配置
        self.MULTI_TENANT_ENABLED: bool = self._get_bool("MULTI_TENANT_ENABLED", True)
        self.DEFAULT_TENANT_QUOTA_TOKENS: int = self._get_int("DEFAULT_TENANT_QUOTA_TOKENS", 1000000)
        self.DEFAULT_TENANT_QUOTA_API_CALLS: int = self._get_int("DEFAULT_TENANT_QUOTA_API_CALLS", 10000)

        # SSO 配置
        self.SSO_ENABLED: bool = self._get_bool("SSO_ENABLED", False)
        self.SSO_PROVIDER: Optional[str] = self._get("SSO_PROVIDER")  # saml/oauth2/ldap/wechat_work
        self.SSO_CONFIG: Dict[str, Any] = self._get_json("SSO_CONFIG", {})

        # 审计配置
        self.AUDIT_ENABLED: bool = self._get_bool("AUDIT_ENABLED", True)
        self.AUDIT_LOG_SENSITIVE: bool = self._get_bool("AUDIT_LOG_SENSITIVE", True)
        self.AUDIT_REQUIRE_REVIEW: bool = self._get_bool("AUDIT_REQUIRE_REVIEW", True)
        self.AUDIT_RETENTION_DAYS: int = self._get_int("AUDIT_RETENTION_DAYS", 365)

        # RBAC 配置
        self.RBAC_ENABLED: bool = self._get_bool("RBAC_ENABLED", True)
        self.RBAC_DEFAULT_ROLE: str = self._get("RBAC_DEFAULT_ROLE", "operator")
        self.RBAC_CUSTOM_ROLES_ENABLED: bool = self._get_bool("RBAC_CUSTOM_ROLES_ENABLED", True)

        # 数据脱敏配置
        self.MASKING_ENABLED: bool = self._get_bool("MASKING_ENABLED", True)
        self.MASKING_BUILTIN_RULES: bool = self._get_bool("MASKING_BUILTIN_RULES", True)
        self.MASKING_AUDIT_LOG: bool = self._get_bool("MASKING_AUDIT_LOG", True)

        # API 配额配置
        self.QUOTA_ENABLED: bool = self._get_bool("QUOTA_ENABLED", True)
        self.QUOTA_DEFAULT_DAILY: int = self._get_int("QUOTA_DEFAULT_DAILY", 100000)
        self.QUOTA_DEFAULT_MONTHLY: int = self._get_int("QUOTA_DEFAULT_MONTHLY", 1000000)
        self.QUOTA_DEFAULT_CONCURRENT: int = self._get_int("QUOTA_DEFAULT_CONCURRENT", 10)

        # 会话池配置
        self.SESSION_POOL_ENABLED: bool = self._get_bool("SESSION_POOL_ENABLED", True)
        self.SESSION_POOL_MAX_MESSAGES: int = self._get_int("SESSION_POOL_MAX_MESSAGES", 1000)
        self.SESSION_POOL_MAX_AGE_DAYS: int = self._get_int("SESSION_POOL_MAX_AGE_DAYS", 90)

        # 银行特定配置
        self.BANK_MODE: bool = self._get_bool("BANK_MODE", True)  # 银行模式（增强合规）
        self.BANK_COMPLIANCE_LOG: bool = self._get_bool("BANK_COMPLIANCE_LOG", True)
        self.BANK_DATA_RETENTION_DAYS: int = self._get_int("BANK_DATA_RETENTION_DAYS", 2555)  # 7年

        # 安全配置
        self.SECURITY_PASSWORD_MIN_LENGTH: int = self._get_int("SECURITY_PASSWORD_MIN_LENGTH", 8)
        self.SECURITY_MFA_REQUIRED: bool = self._get_bool("SECURITY_MFA_REQUIRED", True)
        self.SECURITY_IP_WHITELIST: list[str] = self._get_json("SECURITY_IP_WHITELIST", [])
        self.SECURITY_RATE_LIMIT_PER_MINUTE: int = self._get_int("SECURITY_RATE_LIMIT_PER_MINUTE", 60)

        # 数据库配置（企业级）
        self.DB_POOL_SIZE: int = self._get_int("DB_POOL_SIZE", 20)
        self.DB_MAX_OVERFLOW: int = self._get_int("DB_MAX_OVERFLOW", 40)
        self.DB_POOL_TIMEOUT: int = self._get_int("DB_POOL_TIMEOUT", 30)

        logger.info("Enterprise config loaded")

    def _get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """获取环境变量"""
        return os.environ.get(key, default)

    def _get_bool(self, key: str, default: bool) -> bool:
        """获取布尔类型环境变量"""
        val = os.environ.get(key)
        if val is None:
            return default
        return val.lower() in ("true", "1", "yes", "on")

    def _get_int(self, key: str, default: int) -> int:
        """获取整数类型环境变量"""
        val = os.environ.get(key)
        if val is None:
            return default
        try:
            return int(val)
        except ValueError:
            logger.warning(f"Invalid int value for {key}: {val}, using default {default}")
            return default

    def _get_json(self, key: str, default: Any) -> Any:
        """获取 JSON 类型环境变量"""
        val = os.environ.get(key)
        if val is None:
            return default
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON value for {key}: {val}, using default")
            return default

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 API 响应）"""
        return {
            "multi_tenant_enabled": self.MULTI_TENANT_ENABLED,
            "sso_enabled": self.SSO_ENABLED,
            "sso_provider": self.SSO_PROVIDER,
            "audit_enabled": self.AUDIT_ENABLED,
            "audit_retention_days": self.AUDIT_RETENTION_DAYS,
            "rbac_enabled": self.RBAC_ENABLED,
            "masking_enabled": self.MASKING_ENABLED,
            "quota_enabled": self.QUOTA_ENABLED,
            "session_pool_enabled": self.SESSION_POOL_ENABLED,
            "bank_mode": self.BANK_MODE,
            "security_mfa_required": self.SECURITY_MFA_REQUIRED,
        }

    def validate(self) -> list[str]:
        """验证配置，返回错误列表"""
        errors = []

        if self.SSO_ENABLED and not self.SSO_PROVIDER:
            errors.append("SSO_ENABLED=True but SSO_PROVIDER not set")

        if self.MULTI_TENANT_ENABLED:
            if self.DEFAULT_TENANT_QUOTA_TOKENS <= 0:
                errors.append("DEFAULT_TENANT_QUOTA_TOKENS must be positive")

        if self.QUOTA_ENABLED:
            if self.QUOTA_DEFAULT_DAILY <= 0:
                errors.append("QUOTA_DEFAULT_DAILY must be positive")

        if self.BANK_MODE:
            if not self.AUDIT_ENABLED:
                errors.append("BANK_MODE requires AUDIT_ENABLED=True")
            if not self.MASKING_ENABLED:
                errors.append("BANK_MODE requires MASKING_ENABLED=True")

        return errors


# ============================================================
# 租户配置类（每个租户可以有不同的配置）
# ============================================================

class TenantConfig:
    """租户级配置（存储在 database）"""

    def __init__(self, tenant_id: str, settings: Dict[str, Any]):
        self.tenant_id = tenant_id
        self.settings = settings

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self.settings.get(key, default)

    def set(self, key: str, value: Any):
        """设置配置值"""
        self.settings[key] = value

    @classmethod
    def from_db(cls, tenant_id: str, db_settings: Dict[str, Any]) -> "TenantConfig":
        """从数据库加载配置"""
        return cls(tenant_id, db_settings)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tenant_id": self.tenant_id,
            "settings": self.settings,
        }


# ============================================================
# 全局配置实例
# ============================================================

@lru_cache()
def get_enterprise_config() -> EnterpriseConfig:
    """获取企业配置（单例）"""
    return EnterpriseConfig()
