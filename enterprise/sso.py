"""
SSO 集成模块
支持：
- SAML 2.0 (银行常用)
- OAuth 2.0 / OpenID Connect
- LDAP/Active Directory
- 企业微信/飞书 （内网场景）
"""

import json
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from enterprise.models import User, Tenant, AuditLog

logger = logging.getLogger(__name__)


# ============================================================
# SSO 提供者抽象
# ============================================================

class SSOProvider:
    """SSO 提供者基类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    async def authenticate(self, token: str) -> Optional[Dict[str, Any]]:
        """验证 SSO Token，返回用户信息"""
        raise NotImplementedError

    async def get_user_info(self, sso_id: str) -> Optional[Dict[str, Any]]:
        """通过 SSO ID 获取用户信息"""
        raise NotImplementedError


class SAMLProvider(SSOProvider):
    """SAML 2.0 提供者（银行常用）"""

    async def authenticate(self, saml_response: str) -> Optional[Dict[str, Any]]:
        """
        验证 SAML Response
        （生产环境应使用 python3-saml 或 similar 库）
        """
        # TODO: 实现 SAML 验证
        # 1. 验证签名
        # 2. 检查时间戳
        # 3. 提取用户属性
        logger.info("SAML authentication attempted")
        return None


class OAuth2Provider(SSOProvider):
    """OAuth 2.0 / OpenID Connect 提供者"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client_id = config["client_id"]
        self.client_secret = config["client_secret"]
        self.issuer_url = config["issuer_url"]
        self.redirect_uri = config["redirect_uri"]

    async def authenticate(self, code: str) -> Optional[Dict[str, Any]]:
        """使用授权码获取用户信息"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. 交换 Token
            token_resp = await client.post(
                f"{self.issuer_url}/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                }
            )
            if token_resp.status_code != 200:
                logger.error(f"Token exchange failed: {token_resp.text}")
                return None

            tokens = token_resp.json()
            access_token = tokens["access_token"]
            id_token = tokens.get("id_token")

            # 2. 验证 ID Token (OpenID Connect)
            if id_token:
                user_info = self._decode_id_token(id_token)
                return user_info

            # 3. 获取用户信息 (OAuth 2.0)
            user_resp = await client.get(
                f"{self.issuer_url}/oauth/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if user_resp.status_code != 200:
                return None

            return user_resp.json()

    def _decode_id_token(self, id_token: str) -> Dict[str, Any]:
        """解码 ID Token (简化版，生产环境需验证签名)"""
        # JWT 解码（生产环境应使用 jwt 库并验证签名）
        parts = id_token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid ID token")
        payload = json.loads(base64.b64decode(parts[1] + "=="))
        return payload


class LDAPProvider(SSOProvider):
    """LDAP/Active Directory 提供者"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.server = config["server"]
        self.bind_dn = config["bind_dn"]
        self.bind_password = config["bind_password"]
        self.base_dn = config["base_dn"]
        self.user_filter = config.get("user_filter", "(sAMAccountName={username})")

    async def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """LDAP 绑定认证"""
        # TODO: 实现 LDAP 认证
        # 使用 ldap3 库
        logger.info(f"LDAP authentication attempted for {username}")
        return None


class WeChatWorkProvider(SSOProvider):
    """企业微信 SSO"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.corpid = config["corpid"]
        self.corpsecret = config["corpsecret"]
        self.agentid = config["agentid"]

    async def authenticate(self, code: str) -> Optional[Dict[str, Any]]:
        """通过企业微信 OAuth 认证"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. 获取 access_token
            token_resp = await client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                params={
                    "corpid": self.corpid,
                    "corpsecret": self.corpsecret,
                }
            )
            if token_resp.status_code != 200:
                return None
            access_token = token_resp.json()["access_token"]

            # 2. 获取用户身份
            user_resp = await client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo",
                params={"access_token": access_token, "code": code}
            )
            if user_resp.status_code != 200:
                return None

            user_info = user_resp.json()
            return {
                "sso_id": user_info.get("userid"),
                "username": user_info.get("userid"),
                "display_name": user_info.get("name"),
            }


# ============================================================
# SSO 管理器
# ============================================================

class SSOdManager:
    """SSO 管理器 - 统一入口"""

    def __init__(self):
        self.providers: Dict[str, SSOProvider] = {}

    def register_provider(self, name: str, provider: SSOProvider):
        """注册 SSO 提供者"""
        self.providers[name] = provider
        logger.info(f"SSO provider registered: {name}")

    async def authenticate(self, provider_name: str, credentials: Any) -> Optional[Dict[str, Any]]:
        """统一认证入口"""
        provider = self.providers.get(provider_name)
        if not provider:
            raise ValueError(f"SSO provider not found: {provider_name}")

        user_info = await provider.authenticate(credentials)

        if user_info:
            # 记录审计日志
            await self._log_sso_auth(provider_name, user_info)

        return user_info

    async def _log_sso_auth(self, provider_name: str, user_info: Dict[str, Any]):
        """记录 SSO 认证审计日志"""
        # TODO: 实现审计日志记录
        logger.info(f"SSO authentication success: provider={provider_name}, user={user_info.get('username')}")

    async def sync_user(self, db: AsyncSession, tenant_id: str, sso_user_info: Dict[str, Any]) -> User:
        """
        SSO 用户同步
        如果用户不存在则自动创建
        """
        sso_id = sso_user_info.get("sso_id") or sso_user_info.get("sub")
        username = sso_user_info.get("username") or sso_user_info.get("preferred_username")
        email = sso_user_info.get("email")
        display_name = sso_user_info.get("display_name") or sso_user_info.get("name")

        # 查找现有用户
        result = await db.execute(
            select(User).where(
                (User.sso_id == sso_id) | (User.username == username)
            )
        )
        user = result.scalar_one_or_none()

        if user:
            # 更新用户信息
            user.email = email or user.email
            user.display_name = display_name or user.display_name
            user.last_login_at = datetime.utcnow()
        else:
            # 创建新用户
            user = User(
                tenant_id=tenant_id,
                username=username,
                email=email,
                display_name=display_name,
                sso_id=sso_id,
                role="operator",  # 默认角色
                is_active=True,
            )
            db.add(user)

        await db.flush()
        return user


# 全局 SSO 管理器实例
sso_manager = SSOdManager()
