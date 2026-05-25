# Bank Hermes QClaw - 企业级 Agent 中台

基于 [Hermes Agent](https://github.com/NanoGPT/hermes-agent) 改造的企业级 Agent 中台，专为银行场景设计。

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────┐
│           企业适配层 (Enterprise Layer)              │
├─────────────────────────────────────────────────────┤
│  SSO集成  │  审计日志  │  RBAC  │  数据脱敏  │
│  Session池 │  API配额  │  多租户 │  合规报告  │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│              Hermes Agent 核心层                    │
│  • Agent运行时  • MCP工具  • 多渠道网关           │
└─────────────────────────────────────────────────────┘
```

## ✨ 核心功能

### 1. 多租户架构 (Multi-Tenancy)
- 支持多个银行分支机构/部门独立使用
- 数据物理隔离（不同 Schema）或逻辑隔离（tenant_id）
- 每个租户独立的配额、配置、用户管理

### 2. SSO 集成
支持多种企业级身份认证：
- **SAML 2.0**（银行常用）
- **OAuth 2.0 / OpenID Connect**
- **LDAP/Active Directory**
- **企业微信/飞书**（内网场景）

### 3. 审计日志 (Audit Logging)
符合银行合规要求：
- 所有操作可追溯、不可篡改
- 记录操作人、IP、时间、结果
- 支持数据变更追踪（JSON Patch 格式）
- 敏感操作需要复核（二级审批）
- 审计日志保留 7 年（可配置）

### 4. RBAC (角色权限控制)
预置角色：
- **admin** - 租户管理员（分行科技岗）
- **manager** - 部门经理
- **operator** - 客户经理（普通用户）
- **viewer** - 只读用户
- **auditor** - 审计员（合规岗）

权限粒度：
- `chat` - 对话权限
- `agent:create/edit/delete` - Agent 管理
- `tenant:manage` - 租户管理
- `audit:view` - 审计日志查看
- `data:export` - 数据导出（需复核）
- `user:manage` - 用户管理
- `quota:manage` - 配额管理

### 5. 数据脱敏 (Data Masking)
自动识别并脱敏敏感数据：
- 身份证号
- 手机号
- 银行卡号
- 邮箱
- 金额
- 地址

支持自定义脱敏规则（正则表达式）。

### 6. API 配额管理
多维度配额控制：
- **租户级配额** - 限制整个租户的用量
- **用户级配额** - 限制单个用户的用量
- **每日/每月配额** - 时间维度限制
- **并发控制** - 限制同时进行的请求数

### 7. 会话池管理 (Session Pool)
- 支持会话共享（团队协作）
- 会话迁移（负载均衡）
- 会话归档（软删除）
- 会话搜索（全文检索）

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```bash
# 数据库
DATABASE_URL=postgresql://user:pass@localhost:5432/bank_hermes

# 企业级配置
MULTI_TENANT_ENABLED=true
SSO_ENABLED=false
AUDIT_ENABLED=true
RBAC_ENABLED=true
MASKING_ENABLED=true
QUOTA_ENABLED=true
BANK_MODE=true

# SSO 配置（可选）
# SSO_PROVIDER=oauth2
# SSO_CONFIG={"client_id": "...", "client_secret": "...", ...}
```

### 3. 运行数据库迁移

```bash
python -m enterprise.migrate
```

### 4. 启动服务

```bash
# 开发模式
python enterprise/launcher.py --bank-mode

# 生产模式（使用 gunicorn）
gunicorn -w 4 -k uvicorn.workers.UvicornWorker enterprise.api:app
```

## 📚 API 文档

启动后访问：http://localhost:8000/docs

### 主要接口

#### 认证
- `POST /api/v1/auth/login` - 登录
- `POST /api/v1/auth/register` - 注册
- `GET /api/v1/auth/me` - 当前用户信息

#### 企业级接口（需权限）
- `GET /enterprise/tenants` - 列出租户（admin）
- `POST /enterprise/tenants` - 创建租户（admin）
- `GET /enterprise/users` - 列出用户
- `PUT /enterprise/users/{id}/role` - 更新用户角色
- `GET /enterprise/audit/logs` - 查询审计日志
- `GET /enterprise/audit/compliance-report` - 生成合规报告
- `GET /enterprise/quota/status` - 查询配额状态
- `PUT /enterprise/quota/update` - 更新配额（admin）
- `GET /enterprise/masking/rules` - 列出脱敏规则
- `POST /enterprise/masking/rules` - 创建脱敏规则

## 🐳 Docker 部署

```bash
# 构建镜像
docker build -t bank-hermes-qclaw:latest .

# 使用 docker-compose 启动
docker-compose -f docker-compose.enterprise.yml up -d
```

## 🏦 银行场景使用示例

### 场景 1：多分行部署

```python
# 创建分行租户
POST /enterprise/tenants
{
  "name": "北京分行",
  "code": "BJ_BRANCH"
}

# 创建客户经理用户
POST /api/v1/auth/register
{
  "username": "manager_zhang",
  "email": "zhang@bank.com",
  "password": "SecurePass123!",
  "role": "operator"
}

# 客户经理使用 Agent
POST /api/v1/agents/chat
{
  "agent_id": "agent_123",
  "message": "帮我查询客户 138****1234 的账户余额"
}
# 自动脱敏：手机号显示为 [手机号]
```

### 场景 2：审计合规

```python
# 生成月度合规报告
GET /enterprise/audit/compliance-report?start_time=2026-05-01&end_time=2026-05-31

# 返回：
{
  "summary": {
    "total_operations": 15234,
    "failed_operations": 23,
    "sensitive_operations": 156,
    "failure_rate": "0.15%"
  },
  "by_action": {
    "login": 1234,
    "chat": 12340,
    "data_export": 156
  }
}
```

### 场景 3：API 配额控制

```python
# 为分行设置配额
PUT /enterprise/quota/update
{
  "quota_type": "token",
  "limit_daily": 100000,
  "limit_monthly": 1000000,
  "limit_concurrent": 10
}

# 客户经理调用时自动检查配额
# 超出配额返回 403 Quota exceeded
```

## 📊 性能优化

### 缓存策略
- **脱敏规则缓存** - 租户级缓存，避免每次加载
- **会话池缓存** - 热点会话内存缓存
- **配额计数缓存** - Redis 缓存，减少数据库访问

### 数据库优化
- **索引** - 审计日志、会话、消息表均有索引
- **分区** - 审计日志按月份分区（可选）
- **读写分离** - 审计日志写入主库，查询走从库

## 🔒 安全最佳实践

1. **启用 MFA** - 敏感操作需要二次验证
2. **IP 白名单** - 限制访问来源
3. **速率限制** - 防止暴力破解
4. **数据加密** - 敏感数据（密码、Token）加密存储
5. **审计日志** - 所有操作留痕
6. **定期备份** - 数据库每日备份，保留 7 年

## 📝 开发文档

### 项目结构

```
bank-hermes-qclaw/
├── enterprise/              # 企业适配层
│   ├── __init__.py        # 包初始化
│   ├── models.py          # 数据模型
│   ├── sso.py             # SSO 集成
│   ├── audit.py           # 审计日志
│   ├── rbac.py            # 权限控制
│   ├── masking.py         # 数据脱敏
│   ├── quota.py           # 配额管理
│   ├── session_pool.py    # 会话池
│   ├── config.py          # 配置管理
│   ├── api.py             # FastAPI 接口
│   ├── migrate.py         # 数据库迁移
│   └── launcher.py        # 启动器
├── hermes/                # Hermes 核心（上游）
├── docker/                # Docker 配置
├── docs/                  # 文档
├── tests/                 # 测试
├── requirements.txt       # 依赖
└── README.md             # 本文件
```

### 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

## 📄 许可证

MIT License

## 🙏 致谢

- [Hermes Agent](https://github.com/NanoGPT/hermes-agent) - 原始项目
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架
- [SQLAlchemy](https://www.sqlalchemy.org/) - ORM

## 📧 联系方式

- 项目地址：https://github.com/zhukefucn/bank-hermes-qclaw
- Issue Tracker：https://github.com/zhukefucn/bank-hermes-qclaw/issues

---

**⚠️ 警告**：本项目包含敏感数据处理功能，部署前请确保：
1. 已启用审计日志
2. 已配置数据脱敏规则
3. 已设置合理的配额限制
4. 已进行安全渗透测试
