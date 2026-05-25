# Bank Hermes QClaw - 企业级部署文档

## 📋 部署前检查清单

### 1. 环境要求
- [ ] Linux 服务器 (推荐: Ubuntu 22.04 LTS / CentOS 8+)
- [ ] Python 3.11+
- [ ] PostgreSQL 14+ (生产环境)
- [ ] Redis 7+ (缓存 + 会话)
- [ ] Docker 24+ & Docker Compose (容器化部署)
- [ ] Nginx 1.24+ (反向代理)
- [ ] SSL 证书 (HTTPS 必须)

### 2. 网络要求
- [ ] 开放端口: 80 (HTTP), 443 (HTTPS), 8000 (API), 3000 (Web)
- [ ] 出站访问: GitHub (代码拉取), LLM API (模型调用)
- [ ] 内网访问: 数据库、Redis、SSO 服务器

### 3. 安全配置
- [ ] 防火墙规则配置
- [ ] SSL/TLS 证书安装
- [ ] 数据库密码强度策略
- [ ] JWT Secret 密钥生成 (≥64字符)
- [ ] SSO 配置 (如启用)

### 4. 合规要求 (银行场景)
- [ ] 审计日志保留策略 (≥7年)
- [ ] 数据备份策略 (每日全量 + 每小时增量)
- [ ] 灾备方案 (主备机房)
- [ ] 渗透测试报告
- [ ] 等保三级认证 (如适用)

---

## 🚀 部署架构

### 生产环境架构图

```
                    ┌──────────────┐
                    │    用户端     │
                    └──────┬───────┘
                           │ HTTPS (443)
                    ┌──────▼───────┐
                    │   Nginx      │ (负载均衡 + SSL终止)
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌──▼────┐ ┌───▼────┐
        │  Frontend  │ │  API   │ │  Agent │
        │  (React)  │ │(FastAPI)│ │ Runtime│
        │  :3000     │ │ :8000  │ │ :8001  │
        └─────┬─────┘ └──┬─────┘ └───┬────┘
              │            │             │
              └────────────┼─────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌──▼────┐ ┌───▼────┐
        │ PostgreSQL  │ │ Redis  │ │ Vector  │
        │  :5432     │ │ :6379  │ │ Database│
        │  (主从)    │ │(集群) │ │ (Milvus)│
        └─────────────┘ └───────┘ └─────────┘
```

### 高可用配置
- **API 节点**: 3台 (负载均衡)
- **数据库**: 主从复制 (1主2从)
- **Redis**: Sentinel 模式 (1主2从3哨兵)
- **前端**: 静态资源 CDN 加速

---

## 📦 方式一：Docker Compose 部署 (推荐)

### 1. 克隆代码

```bash
# 克隆仓库
git clone https://github.com/zhukefucn/bank-hermes-qclaw.git
cd bank-hermes-qclaw

# 切换到稳定版本
git checkout v1.0.0  # 或最新 tag
```

### 2. 配置环境变量

创建 `.env` 文件：

```bash
# ============ 基础配置 ============
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=your-super-secret-key-min-64-chars-change-this-now

# ============ 数据库配置 ============
DATABASE_URL=postgresql://hermes_user:strong_password@postgres:5432/hermes_enterprise

# ============ Redis 配置 ============
REDIS_URL=redis://:redis_password@redis:6379/0

# ============ LLM 配置 ============
LLM_PROVIDER=deepseek  # deepseek/openai/azure
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com

# ============ 企业级配置 ============
MULTI_TENANT_ENABLED=true
SSO_ENABLED=false  # 生产环境建议启用
AUDIT_ENABLED=true
AUDIT_LOG_SENSITIVE=true
AUDIT_REQUIRE_REVIEW=true
AUDIT_RETENTION_DAYS=2555  # 7年 (银行合规)

RBAC_ENABLED=true
RBAC_DEFAULT_ROLE=operator

MASKING_ENABLED=true
MASKING_BUILTIN_RULES=true
MASKING_AUDIT_LOG=true

QUOTA_ENABLED=true
QUOTA_DEFAULT_DAILY=100000
QUOTA_DEFAULT_MONTHLY=1000000
QUOTA_DEFAULT_CONCURRENT=10

SESSION_POOL_ENABLED=true
SESSION_POOL_MAX_MESSAGES=1000
SESSION_POOL_MAX_AGE_DAYS=90

# ============ 银行特定配置 ============
BANK_MODE=true  # 增强合规
BANK_COMPLIANCE_LOG=true
BANK_DATA_RETENTION_DAYS=2555

# ============ 安全配置 ============
SECURITY_PASSWORD_MIN_LENGTH=12
SECURITY_MFA_REQUIRED=true
SECURITY_IP_WHITELIST=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
SECURITY_RATE_LIMIT_PER_MINUTE=30

# ============ CORS 配置 ============
CORS_ORIGINS=https://your-domain.com,https://admin.your-domain.com

# ============ SSO 配置 (可选) ============
# SSO_PROVIDER=saml  # saml/oauth2/ldap/wechat_work
# SSO_CONFIG={"entity_id": "...", "sso_url": "...", ...}
```

### 3. 构建并启动服务

```bash
# 构建镜像
docker-compose -f docker-compose.enterprise.yml build

# 启动数据库
docker-compose -f docker-compose.enterprise.yml up -d postgres redis

# 等待数据库就绪 (约10秒)
sleep 10

# 运行数据库迁移
docker-compose -f docker-compose.enterprise.yml run --rm api python -m enterprise.migrate

# 启动所有服务
docker-compose -f docker-compose.enterprise.yml up -d

# 查看日志
docker-compose -f docker-compose.enterprise.yml logs -f
```

### 4. 验证部署

```bash
# 检查服务状态
docker-compose -f docker-compose.enterprise.yml ps

# 测试 API 健康检查
curl http://localhost:8000/health

# 测试前端访问
curl http://localhost:3000/

# 创建超级管理员 (首次部署)
docker-compose -f docker-compose.enterprise.yml run --rm api \
  python -m enterprise.create_superuser \
  --username admin \
  --email admin@bank.com \
  --password "StrongPass123!"
```

---

## 🔧 方式二：手动部署 (定制化场景)

### 1. 安装依赖

```bash
# 系统依赖 (Ubuntu/Debian)
sudo apt update
sudo apt install -y python3.11 python3-pip postgresql-14 redis-server nginx

# Python 虚拟环境
python3.11 -m venv venv
source venv/bin/activate

# Python 依赖
pip install -r requirements.txt
pip install -r requirements-enterprise.txt  # 企业级依赖
```

### 2. 配置数据库

```bash
# 创建数据库用户
sudo -u postgres psql

CREATE USER hermes_user WITH PASSWORD 'strong_password';
CREATE DATABASE hermes_enterprise OWNER hermes_user;
GRANT ALL PRIVILEGES ON DATABASE hermes_enterprise TO hermes_user;

# 启用扩展
\c hermes_enterprise
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;  # 用于模糊搜索

# 退出
\q
```

### 3. 运行迁移

```bash
# 设置环境变量
export DATABASE_URL="postgresql://hermes_user:strong_password@localhost:5432/hermes_enterprise"
export REDIS_URL="redis://localhost:6379/0"

# 运行迁移
python -m enterprise.migrate

# 创建超级管理员
python -m enterprise.create_superuser \
  --username admin \
  --email admin@bank.com \
  --password "StrongPass123!"
```

### 4. 启动服务

#### 方式 A：使用 systemd (推荐)

创建 `/etc/systemd/system/hermes-api.service`：

```ini
[Unit]
Description=Hermes Enterprise API
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=hermes
Group=hermes
WorkingDirectory=/opt/bank-hermes-qclaw
Environment="PATH=/opt/bank-hermes-qclaw/venv/bin"
ExecStart=/opt/bank-hermes-qclaw/venv/bin/uvicorn enterprise.api:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes-api
sudo systemctl start hermes-api
sudo systemctl status hermes-api
```

#### 方式 B：使用 Gunicorn

```bash
gunicorn -w 4 \
  -k uvicorn.workers.UvicornWorker \
  -b 0.0.0.0:8000 \
  --access-logfile /var/log/hermes/access.log \
  --error-logfile /var/log/hermes/error.log \
  enterprise.api:app
```

### 5. 配置 Nginx 反向代理

创建 `/etc/nginx/sites-available/hermes`：

```nginx
upstream hermes_api {
    server 127.0.0.1:8000;
    server 127.0.0.1:8001;  # 多实例负载均衡
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;  # 强制 HTTPS
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL 配置
    ssl_certificate /etc/ssl/certs/hermes.crt;
    ssl_certificate_key /etc/ssl/private/hermes.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # 前端静态文件
    location / {
        root /opt/bank-hermes-qclaw/frontend/build;
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理
    location /api/ {
        proxy_pass http://hermes_api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 企业级 API
    location /enterprise/ {
        proxy_pass http://hermes_api/enterprise/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket 支持 (会话实时通信)
    location /ws/ {
        proxy_pass http://hermes_api/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/hermes /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 🛡️ 安全加固

### 1. 数据库安全

```bash
# PostgreSQL 配置文件: /etc/postgresql/14/main/postgresql.conf
listen_addresses = 'localhost'  # 仅本地访问
port = 5432
ssl = on
ssl_cert_file = '/etc/ssl/certs/postgresql.crt'
ssl_key_file = '/etc/ssl/private/postgresql.key'

# 访问控制: /etc/postgresql/14/main/pg_hba.conf
# 仅允许本地连接
local   all   all                 scram-sha-256
host    all   all   127.0.0.1/32  scram-sha-256
```

### 2. Redis 安全

```bash
# Redis 配置文件: /etc/redis/redis.conf
bind 127.0.0.1
port 6379
requirepass strong_redis_password
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command SHUTDOWN SHUTDOWN_SECRET_KEY
```

### 3. 应用安全

```bash
# 生成强密钥
python -c "import secrets; print(secrets.token_urlsafe(64))"

# 配置防火墙
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable

# 禁用 root SSH 登录
# /etc/ssh/sshd_config
PermitRootLogin no
PasswordAuthentication no
```

### 4. 审计日志加密 (可选)

```bash
# 审计日志表加密 (PostgreSQL TDE)
# 需要 PostgreSQL 企业版或 pgcrypto 扩展

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 加密敏感字段
UPDATE enterprise_audit_logs
SET changes = pgp_pub_encrypt(changes::text, dearmor('-----BEGIN PGP PUBLIC KEY...'))
WHERE requires_review = true;
```

---

## 📊 监控与运维

### 1. 日志管理

```bash
# 应用日志路径
/var/log/hermes/api.log
/var/log/hermes/audit.log
/var/log/nginx/access.log
/var/log/nginx/error.log

# 日志轮转配置: /etc/logrotate.d/hermes
/var/log/hermes/*.log {
    daily
    rotate 3650  # 保留 10 年 (银行合规)
    compress
    delaycompress
    missingok
    notifempty
    create 0640 hermes hermes
    sharedscripts
    postrotate
        systemctl reload hermes-api
    endscript
}
```

### 2. 监控指标

使用 **Prometheus + Grafana** 监控：

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'hermes-api'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

关键指标：
- **API 请求量** (QPS)
- **响应时间** (P50/P95/P99)
- **错误率** (4xx/5xx)
- **Token 消耗** (每日/每月)
- **并发会话数**
- **数据库连接池** (活跃/空闲)
- **Redis 内存使用**

### 3. 告警规则

```yaml
# alertmanager.yml
groups:
  - name: hermes_alerts
    rules:
      - alert: APIHighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "API 错误率过高 ({{ $value }}%)"

      - alert: DatabaseConnectionPoolExhausted
        expr: pg_stat_activity_count / pg_max_connections > 0.8
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "数据库连接池即将耗尽"

      - alert: QuotaExceeded
        expr: quota_usage_percent > 90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "租户 {{ $labels.tenant_id }} 配额即将用尽"
```

### 4. 备份策略

```bash
# 数据库备份脚本: /opt/backup/db_backup.sh
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/postgres"

# 全量备份
pg_dump -U hermes_user -d hermes_enterprise | gzip > $BACKUP_DIR/full_$DATE.sql.gz

# 保留30天
find $BACKUP_DIR -name "full_*.sql.gz" -mtime +30 -delete

# 上传到对象存储 (可选)
aws s3 cp $BACKUP_DIR/full_$DATE.sql.gz s3://your-bucket/backups/

# 定时任务 (每日凌晨2点)
# crontab -e
0 2 * * * /opt/backup/db_backup.sh
```

---

## 🔍 故障排查

### 常见问题

#### 1. API 启动失败

```bash
# 查看日志
journalctl -u hermes-api -f

# 检查端口占用
sudo netstat -tulpn | grep 8000

# 检查数据库连接
psql -U hermes_user -d hermes_enterprise -c "SELECT 1;"
```

#### 2. 数据库迁移失败

```bash
# 检查迁移版本
python -m alembic history

# 回滚迁移
python -m alembic downgrade -1

# 重新运行迁移
python -m enterprise.migrate
```

#### 3. SSO 登录失败

```bash
# 启用 SSO 调试日志
export SSO_DEBUG=true
export LOG_LEVEL=DEBUG

# 查看 SSO 日志
tail -f /var/log/hermes/audit.log | grep sso
```

#### 4. 审计日志写入失败

```bash
# 检查磁盘空间
df -h /var/lib/postgresql

# 检查表权限
psql -U hermes_user -d hermes_enterprise -c "\dp enterprise_audit_logs"

# 手动插入测试数据
INSERT INTO enterprise_audit_logs (...) VALUES (...);
```

---

## 📈 性能优化

### 1. 数据库优化

```sql
-- 创建索引 (如未创建)
CREATE INDEX CONCURRENTLY idx_audit_tenant_created ON enterprise_audit_logs(tenant_id, created_at);
CREATE INDEX CONCURRENTLY idx_sessions_tenant ON enterprise_sessions(tenant_id, status);
CREATE INDEX CONCURRENTLY idx_messages_session ON enterprise_messages(session_id, created_at);

-- 分区 (审计日志按月分区)
CREATE TABLE enterprise_audit_logs_2026_05 PARTITION OF enterprise_audit_logs
FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
```

### 2. Redis 缓存优化

```bash
# redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
save 900 1   # 15分钟内有至少1次写入则保存
save 300 10  # 5分钟内有至少10次写入则保存
```

### 3. API 性能优化

```python
# 启用响应压缩
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 启用缓存
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
FastAPICache.init(RedisBackend(redis), prefix="hermes-cache")
```

---

## 📞 技术支持

- **项目地址**: https://github.com/zhukefucn/bank-hermes-qclaw
- **Issue Tracker**: https://github.com/zhukefucn/bank-hermes-qclaw/issues
- **文档**: https://bank-hermes-qclaw.readthedocs.io/

---

## 📝 部署检查表

完成部署后，请确认：

- [ ] 所有服务正常运行 (`docker-compose ps` 或 `systemctl status`)
- [ ] API 健康检查通过 (`curl http://localhost:8000/health`)
- [ ] 前端页面正常访问 (`curl http://localhost:3000/`)
- [ ] 数据库连接正常 (`psql -U hermes_user -d hermes_enterprise -c "SELECT 1;"`)
- [ ] Redis 连接正常 (`redis-cli ping`)
- [ ] 审计日志正常写入 (`tail -f /var/log/hermes/audit.log`)
- [ ] SSO 登录正常 (如启用)
- [ ] 数据脱敏规则生效
- [ ] 配额控制生效
- [ ] HTTPS 访问正常 (`curl https://your-domain.com/`)
- [ ] 备份脚本正常运行
- [ ] 监控告警配置完成

---

**⚠️ 重要提醒**：
1. 首次部署后，**立即修改默认管理员密码**
2. 生产环境**必须启用 HTTPS**
3. 定期**更新依赖包** (`pip install -U -r requirements.txt`)
4. 定期**检查审计日志** (合规要求)
5. **不要**在公网暴露数据库端口

---

**部署完成后，请运行安全扫描工具 (如 OWASP ZAP) 进行渗透测试。**
