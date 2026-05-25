# Bank Hermes QClaw - API 文档

> **Base URL**: `http://localhost:8000` (开发) / `https://api.your-bank.com` (生产)
>
> **认证方式**: Bearer Token (JWT)
>
> **Content-Type**: `application/json`

---

## 目录

1. [认证接口](#认证接口)
2. [租户管理](#租户管理)
3. [用户管理](#用户管理)
4. [审计日志](#审计日志)
5. [配额管理](#配额管理)
6. [数据脱敏](#数据脱敏)
7. [SSO 配置](#sso-配置)
8. [错误处理](#错误处理)
9. [示例场景](#示例场景)

---

## 认证接口

所有 API 请求需要在 Header 中携带 JWT Token：

```http
Authorization: Bearer <your-jwt-token>
```

### 登录

**接口**: `POST /api/v1/auth/login`

**请求体**:
```json
{
  "username": "manager_zhang",
  "password": "SecurePass123!"
}
```

**响应** (200):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

**错误响应** (401):
```json
{
  "detail": "Incorrect username or password"
}
```

### 注册

**接口**: `POST /api/v1/auth/register`

**请求体**:
```json
{
  "username": "manager_zhang",
  "email": "zhang@bank.com",
  "password": "SecurePass123!",
  "role": "operator"
}
```

**响应** (200):
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "username": "manager_zhang",
  "email": "zhang@bank.com",
  "role": "operator"
}
```

### 获取当前用户

**接口**: `GET /api/v1/auth/me`

**Headers**:
```http
Authorization: Bearer <token>
```

**响应** (200):
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "username": "manager_zhang",
  "email": "zhang@bank.com",
  "role": "operator",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## 租户管理

> **权限要求**: `manage_tenant` (仅 admin)

### 列出租户

**接口**: `GET /enterprise/tenants`

**cURL 示例**:
```bash
curl -X GET "http://localhost:8000/enterprise/tenants" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

**响应** (200):
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "北京分行",
    "code": "BJ_BRANCH",
    "is_active": true,
    "quota_tokens": 1000000,
    "quota_api_calls": 10000,
    "created_at": "2026-05-25T12:00:00Z"
  }
]
```

### 创建租户

**接口**: `POST /enterprise/tenants`

**请求体**:
```json
{
  "name": "上海分行",
  "code": "SH_BRANCH"
}
```

**cURL 示例**:
```bash
curl -X POST "http://localhost:8000/enterprise/tenants" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "上海分行",
    "code": "SH_BRANCH"
  }'
```

**响应** (200):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "name": "上海分行",
  "code": "SH_BRANCH",
  "message": "Tenant created successfully"
}
```

**错误响应** (400):
```json
{
  "detail": "Tenant code already exists"
}
```

---

## 用户管理

### 列出用户

**接口**: `GET /enterprise/users`

**权限要求**: `manage_users`

**cURL 示例**:
```bash
curl -X GET "http://localhost:8000/enterprise/users" \
  -H "Authorization: Bearer <token>"
```

**响应** (200):
```json
[
  {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "username": "manager_zhang",
    "email": "zhang@bank.com",
    "display_name": "张三",
    "role": "operator",
    "is_active": true,
    "last_login_at": "2026-05-25T10:00:00Z"
  }
]
```

### 更新用户角色

**接口**: `PUT /enterprise/users/{user_id}/role`

**权限要求**: `manage_users`

**请求体**:
```json
{
  "new_role": "manager"
}
```

**可选角色**:
- `admin` - 租户管理员
- `manager` - 部门经理
- `operator` - 客户经理（普通用户）
- `viewer` - 只读用户
- `auditor` - 审计员

**cURL 示例**:
```bash
curl -X PUT "http://localhost:8000/enterprise/users/660e8400-e29b-41d4-a716-446655440001/role" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"new_role": "manager"}'
```

**响应** (200):
```json
{
  "message": "User role updated to manager"
}
```

**错误响应** (400):
```json
{
  "detail": "Invalid role. Must be one of ['admin', 'manager', 'operator', 'viewer', 'auditor']"
}
```

---

## 审计日志

### 查询审计日志

**接口**: `GET /enterprise/audit/logs`

**权限要求**: `view_audit`

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | string | 否 | 操作类型（如 `user_login`） |
| `resource_type` | string | 否 | 资源类型（如 `user`） |
| `status` | string | 否 | 状态 (`success`/`failure`) |
| `start_time` | datetime | 否 | 开始时间 |
| `end_time` | datetime | 否 | 结束时间 |
| `limit` | int | 否 | 返回记录数 (1-1000, 默认100) |
| `offset` | int | 否 | 分页偏移量 |

**cURL 示例**:
```bash
curl -X GET "http://localhost:8000/enterprise/audit/logs?action=user_login&limit=10" \
  -H "Authorization: Bearer <token>"
```

**响应** (200):
```json
[
  {
    "id": "770e8400-e29b-41d4-a716-446655440002",
    "action": "user_login",
    "resource_type": "user",
    "resource_id": "660e8400-e29b-41d4-a716-446655440001",
    "user_id": "660e8400-e29b-41d4-a716-446655440001",
    "status": "success",
    "ip_address": "10.0.0.1",
    "created_at": "2026-05-25T10:00:00Z",
    "requires_review": false
  }
]
```

### 生成合规报告

**接口**: `GET /enterprise/audit/compliance-report`

**权限要求**: `view_audit`

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `start_time` | datetime | ✅ | 开始时间 |
| `end_time` | datetime | ✅ | 结束时间 |

**cURL 示例**:
```bash
curl -X GET "http://localhost:8000/enterprise/audit/compliance-report?start_time=2026-05-01T00:00:00Z&end_time=2026-05-31T23:59:59Z" \
  -H "Authorization: Bearer <token>"
```

**响应** (200):
```json
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
  },
  "by_user": {
    "660e8400-e29b-41d4-a716-446655440001": 5000,
    "660e8400-e29b-41d4-a716-446655440002": 3000
  },
  "by_ip": {
    "10.0.0.1": 8000,
    "10.0.0.2": 7234
  }
}
```

---

## 配额管理

### 获取配额状态

**接口**: `GET /enterprise/quota/status`

**权限要求**: `view_usage`

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `quota_type` | string | 否 | 配额类型 (`token`/`api_call`, 默认 `token`) |

**cURL 示例**:
```bash
curl -X GET "http://localhost:8000/enterprise/quota/status?quota_type=token" \
  -H "Authorization: Bearer <token>"
```

**响应** (200):
```json
{
  "quota_type": "token",
  "limit_daily": 100000,
  "limit_monthly": 1000000,
  "used_daily": 15000,
  "used_monthly": 250000,
  "remaining_daily": 85000,
  "remaining_monthly": 750000,
  "usage_percent_daily": 15.0,
  "usage_percent_monthly": 25.0
}
```

### 更新配额

**接口**: `PUT /enterprise/quota/update`

**权限要求**: `manage_quota`

**请求体**:
```json
{
  "quota_type": "token",
  "limit_daily": 150000,
  "limit_monthly": 1500000,
  "limit_concurrent": 15
}
```

**cURL 示例**:
```bash
curl -X PUT "http://localhost:8000/enterprise/quota/update" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "quota_type": "token",
    "limit_daily": 150000,
    "limit_monthly": 1500000,
    "limit_concurrent": 15
  }'
```

**响应** (200):
```json
{
  "message": "Quota updated successfully"
}
```

---

## 数据脱敏

### 列出脱敏规则

**接口**: `GET /enterprise/masking/rules`

**权限要求**: `manage_tenant`

**cURL 示例**:
```bash
curl -X GET "http://localhost:8000/enterprise/masking/rules" \
  -H "Authorization: Bearer <token>"
```

**响应** (200):
```json
[
  {
    "id": "880e8400-e29b-41d4-a716-446655440003",
    "name": "身份证号脱敏",
    "pattern": "\\d{17}[0-9X]",
    "replacement": "[身份证号]",
    "priority": 100,
    "apply_to_input": true,
    "apply_to_output": true,
    "apply_to_log": true,
    "is_active": true
  }
]
```

### 创建脱敏规则

**接口**: `POST /enterprise/masking/rules`

**权限要求**: `manage_tenant`

**请求体**:
```json
{
  "name": "手机号脱敏",
  "pattern": "1[3-9]\\d{9}",
  "replacement": "[手机号]",
  "priority": 90,
  "apply_to_input": true,
  "apply_to_output": true,
  "apply_to_log": true
}
```

**cURL 示例**:
```bash
curl -X POST "http://localhost:8000/enterprise/masking/rules" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "手机号脱敏",
    "pattern": "1[3-9]\\\\d{9}",
    "replacement": "[手机号]",
    "priority": 90
  }'
```

**响应** (200):
```json
{
  "id": "880e8400-e29b-41d4-a716-446655440004",
  "message": "Masking rule created successfully"
}
```

---

## SSO 配置

### 获取 SSO 配置

**接口**: `GET /enterprise/sso/config`

**权限要求**: `manage_tenant`

**cURL 示例**:
```bash
curl -X GET "http://localhost:8000/enterprise/sso/config" \
  -H "Authorization: Bearer <token>"
```

**响应** (200):
```json
{
  "sso_enabled": true,
  "sso_provider": "saml",
  "sso_config": {
    "entity_id": "https://idp.bank.com/entity",
    "sso_url": "https://idp.bank.com/sso",
    "client_secret": "***masked***"
  }
}
```

### 测试 SSO 连接

**接口**: `POST /enterprise/sso/test`

**权限要求**: `manage_tenant`

**请求体**:
```json
{
  "provider_name": "saml"
}
```

**cURL 示例**:
```bash
curl -X POST "http://localhost:8000/enterprise/sso/test" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"provider_name": "saml"}'
```

**响应** (200):
```json
{
  "provider": "saml",
  "status": "test_not_implemented"
}
```

---

## 错误处理

### 标准错误响应格式

```json
{
  "detail": "错误描述信息"
}
```

### 常见错误码

| 状态码 | 说明 | 可能原因 |
|--------|------|----------|
| 400 | Bad Request | 请求参数错误、角色无效 |
| 401 | Unauthorized | Token 缺失或过期 |
| 403 | Forbidden | 权限不足 |
| 404 | Not Found | 资源不存在（用户/租户/配额） |
| 405 | Method Not Allowed | HTTP 方法错误 |
| 422 | Unprocessable Entity | 请求体验证失败 |
| 429 | Too Many Requests | 配额超限 |
| 500 | Internal Server Error | 服务器内部错误 |

### 配额超限错误示例 (429)

```json
{
  "detail": "Quota exceeded: Daily token quota exceeded"
}
```

---

## 示例场景

### 场景 1：多分行部署

#### 1. 创建分行租户

```bash
# Admin 登录
TOKEN=$(curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"AdminPass123!"}' \
  | jq -r '.access_token')

# 创建北京分行租户
curl -X POST "http://localhost:8000/enterprise/tenants" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "北京分行",
    "code": "BJ_BRANCH"
  }'
```

#### 2. 创建客户经理用户

```bash
# 注册客户经理
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "manager_zhang",
    "email": "zhang@bank.com",
    "password": "SecurePass123!",
    "role": "operator"
  }'
```

#### 3. 客户经理使用 Agent

```bash
# 客户经理登录
USER_TOKEN=$(curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"manager_zhang","password":"SecurePass123!"}' \
  | jq -r '.access_token')

# 发送消息（自动脱敏）
curl -X POST "http://localhost:8000/api/v1/agents/chat" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_123",
    "message": "帮我查询客户 138****1234 的账户余额"
  }'
# 响应中手机号自动脱敏为 [手机号]
```

### 场景 2：审计合规

```bash
# 生成月度合规报告
curl -X GET "http://localhost:8000/enterprise/audit/compliance-report?start_time=2026-05-01T00:00:00Z&end_time=2026-05-31T23:59:59Z" \
  -H "Authorization: Bearer $TOKEN"
```

**响应**:
```json
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

```bash
# 查看当前配额状态
curl -X GET "http://localhost:8000/enterprise/quota/status?quota_type=token" \
  -H "Authorization: Bearer $TOKEN"

# 更新配额（Admin 操作）
curl -X PUT "http://localhost:8000/enterprise/quota/update" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "quota_type": "token",
    "limit_daily": 150000,
    "limit_monthly": 1500000
  }'
```

---

## Postman Collection

导入以下 JSON 到 Postman：

```json
{
  "info": {
    "name": "Bank Hermes QClaw - Enterprise API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "variable": [
    {
      "key": "base_url",
      "value": "http://localhost:8000"
    },
    {
      "key": "token",
      "value": ""
    }
  ],
  "item": [
    {
      "name": "Auth",
      "item": [
        {
          "name": "Login",
          "request": {
            "method": "POST",
            "url": "{{base_url}}/api/v1/auth/login",
            "body": {
              "mode": "raw",
              "raw": "{\"username\":\"admin\",\"password\":\"AdminPass123!\"}"
            }
          }
        }
      ]
    },
    {
      "name": "Enterprise",
      "item": [
        {
          "name": "List Tenants",
          "request": {
            "method": "GET",
            "url": "{{base_url}}/enterprise/tenants",
            "header": [
              {"key": "Authorization", "value": "Bearer {{token}}"}
            ]
          }
        }
      ]
    }
  ]
}
```

---

## 相关链接

- **项目主页**: https://github.com/zhukefucn/bank-hermes-qclaw
- **在线 API 文档**: http://localhost:8000/docs (Swagger UI)
- **ReDoc 文档**: http://localhost:8000/redoc
- **OpenAPI YAML**: http://localhost:8000/openapi.yaml

---

**⚠️ 注意**:
1. 所有 API 请求需要在 Header 中携带 `Authorization: Bearer <token>`
2. 生产环境**必须**使用 HTTPS
3. 敏感操作（如数据导出、角色变更）会记录审计日志
4. 配额超限会返回 `429 Too Many Requests`

---

**文档版本**: v1.0.0
**更新时间**: 2026-05-25
**维护者**: Bank Hermes QClaw Team
