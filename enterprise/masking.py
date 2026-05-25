"""
数据脱敏模块
自动识别并脱敏敏感数据：身份证、手机号、银行卡号、金额等
符合银行数据安全规范
"""

import re
import logging
from typing import Dict, List, Optional, Pattern
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from enterprise.models import DataMaskingRule, Tenant, Message, AuditLog

logger = logging.getLogger(__name__)


# ============================================================
# 内置脱敏规则
# ============================================================

# 身份证号（18位或15位）
PATTERN_ID_CARD = r"\b[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b"

# 手机号（中国）
PATTERN_PHONE = r"\b(1[3-9]\d{9})\b"

# 银行卡号（16-19位）
PATTERN_BANK_CARD = r"\b(4\d{12,18}|5[1-5]\d{14}|3[47]\d{13}|3[0,6,8]\d{12}|6(?:011|5\d{2})\d{12}|(?:2131|1800)\d{11})\b"

# 邮箱
PATTERN_EMAIL = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

# 金额（人民币）
PATTERN_AMOUNT_CNY = r"￥?\s*\d+(?:\.\d{1,2})?\s*(?:元|万元|亿)?"

# 金额（美元）
PATTERN_AMOUNT_USD = r"\$\s*\d+(?:\.\d{1,2})?\s*(?:USD|usd)?"

# 地址（简化）
PATTERN_ADDRESS = r"[省請市区县][^，。]{5,50}"


# ============================================================
# 脱敏处理器
# ============================================================

class MaskingProcessor:
    """数据脱敏处理器"""

    def __init__(self, tenant_id: str, db: Optional[AsyncSession] = None):
        self.tenant_id = tenant_id
        self.db = db
        self.rules: List[DataMaskingRule] = []
        self.compiled_rules: List[tuple] = []  # (pattern, replacement)

    async def load_rules(self):
        """加载租户脱敏规则"""
        if not self.db:
            return

        result = await self.db.execute(
            select(DataMaskingRule)
            .where(
                DataMaskingRule.tenant_id == self.tenant_id,
                DataMaskingRule.is_active == True,
            )
            .order_by(DataMaskingRule.priority)
        )
        self.rules = result.scalars().all()

        # 编译正则表达式
        for rule in self.rules:
            try:
                pattern = re.compile(rule.pattern)
                self.compiled_rules.append((pattern, rule.replacement))
            except re.error as e:
                logger.error(f"Invalid regex pattern in rule {rule.name}: {e}")

        # 添加内置规则（低优先级）
        self._add_builtin_rules()

    def _add_builtin_rules(self):
        """添加内置脱敏规则"""
        builtin_rules = [
            (PATTERN_ID_CARD, "[身份证号]"),
            (PATTERN_PHONE, "[手机号]"),
            (PATTERN_BANK_CARD, "[银行卡号]"),
            (PATTERN_EMAIL, "[邮箱]"),
            (PATTERN_AMOUNT_CNY, "[金额]"),
            (PATTERN_AMOUNT_USD, "[金额(USD)]"),
        ]

        for pattern_str, replacement in builtin_rules:
            try:
                pattern = re.compile(pattern_str)
                # 内置规则优先级最低（1000）
                self.compiled_rules.append((pattern, replacement))
            except re.error:
                pass

    def mask(self, text: str, apply_to_input: bool = True) -> str:
        """
        脱敏文本
        """
        if not text:
            return text

        masked_text = text

        for pattern, replacement in self.compiled_rules:
            # 检查是否应用此规则
            # TODO: 根据 apply_to_input/apply_to_output 过滤

            masked_text = pattern.sub(replacement, masked_text)

        return masked_text

    def mask_json(self, data: Dict, fields_to_mask: List[str]) -> Dict:
        """脱敏 JSON 数据中的指定字段"""
        import copy
        masked_data = copy.deepcopy(data)

        for field in fields_to_mask:
            if field in masked_data:
                if isinstance(masked_data[field], str):
                    masked_data[field] = self.mask(masked_data[field])
                elif isinstance(masked_data[field], list):
                    masked_data[field] = [
                        self.mask(item) if isinstance(item, str) else item
                        for item in masked_data[field]
                    ]

        return masked_data

    async def log_masking(
        self,
        db: AsyncSession,
        session_id: str,
        original_content: str,
        masked_content: str,
        user_id: str,
    ):
        """记录脱敏操作审计"""
        audit_log = AuditLog(
            tenant_id=self.tenant_id,
            user_id=user_id,
            action="data_masking",
            resource_type="message",
            resource_id=session_id,
            status="success",
            changes={
                "original_length": len(original_content),
                "masked_length": len(masked_content),
                "rules_applied": len(self.compiled_rules),
            },
        )
        db.add(audit_log)
        await db.flush()


# ============================================================
# 全局脱敏管理器
# ============================================================

class MaskingManager:
    """全局脱敏管理器（缓存处理器）"""

    def __init__(self):
        self.processors: Dict[str, MaskingProcessor] = {}

    async def get_processor(
        self,
        tenant_id: str,
        db: AsyncSession,
    ) -> MaskingProcessor:
        """获取或创建脱敏处理器（带缓存）"""
        if tenant_id not in self.processors:
            processor = MaskingProcessor(tenant_id, db)
            await processor.load_rules()
            self.processors[tenant_id] = processor

        return self.processors[tenant_id]

    async def refresh_tenant(self, tenant_id: str):
        """刷新租户规则缓存"""
        if tenant_id in self.processors:
            del self.processors[tenant_id]

    def mask_for_audit(self, text: str) -> str:
        """
        审计日志脱敏（使用通用规则，不依赖租户）
        用于审计日志中的敏感数据脱敏
        """
        if not text:
            return text

        # 使用内置规则脱敏
        masked = text
        builtin_rules = [
            (PATTERN_ID_CARD, "[身份证号]"),
            (PATTERN_PHONE, "[手机号]"),
            (PATTERN_BANK_CARD, "[银行卡号]"),
            (PATTERN_EMAIL, "[邮箱]"),
        ]

        for pattern_str, replacement in builtin_rules:
            masked = re.sub(pattern_str, replacement, masked)

        return masked


# 全局脱敏管理器实例
masking_manager = MaskingManager()


# ============================================================
# 便捷函数
# ============================================================

async def mask_message(
    db: AsyncSession,
    tenant_id: str,
    content: str,
    apply_to_input: bool = True,
) -> str:
    """脱敏消息内容"""
    processor = await masking_manager.get_processor(tenant_id, db)
    return processor.mask(content, apply_to_input)


async def mask_for_log(content: str) -> str:
    """审计日志脱敏"""
    return masking_manager.mask_for_audit(content)


# ============================================================
# 初始化默认脱敏规则
# ============================================================

async def init_default_masking_rules(db: AsyncSession, tenant_id: str):
    """为租户初始化默认脱敏规则"""
    default_rules = [
        {
            "name": "身份证号脱敏",
            "pattern": PATTERN_ID_CARD,
            "replacement": "[身份证号]",
            "priority": 10,
            "apply_to_input": True,
            "apply_to_output": True,
            "apply_to_log": True,
        },
        {
            "name": "手机号脱敏",
            "pattern": PATTERN_PHONE,
            "replacement": "[手机号]",
            "priority": 20,
            "apply_to_input": True,
            "apply_to_output": True,
            "apply_to_log": True,
        },
        {
            "name": "银行卡号脱敏",
            "pattern": PATTERN_BANK_CARD,
            "replacement": "[银行卡号]",
            "priority": 30,
            "apply_to_input": True,
            "apply_to_output": True,
            "apply_to_log": True,
        },
        {
            "name": "邮箱脱敏",
            "pattern": PATTERN_EMAIL,
            "replacement": "[邮箱]",
            "priority": 40,
            "apply_to_input": True,
            "apply_to_output": False,  # 输出可以保留邮箱（按需）
            "apply_to_log": True,
        },
    ]

    for rule_data in default_rules:
        rule = DataMaskingRule(
            tenant_id=tenant_id,
            name=rule_data["name"],
            pattern=rule_data["pattern"],
            replacement=rule_data["replacement"],
            priority=rule_data["priority"],
            apply_to_input=rule_data["apply_to_input"],
            apply_to_output=rule_data["apply_to_output"],
            apply_to_log=rule_data["apply_to_log"],
            is_active=True,
        )
        db.add(rule)

    await db.flush()
    logger.info(f"Initialized default masking rules for tenant {tenant_id}")
