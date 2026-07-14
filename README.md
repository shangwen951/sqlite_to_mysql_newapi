# New API SQLite 转 MySQL 工具

用于将 New API 使用的 SQLite 数据库导出为可导入 MySQL 的 SQL 文件。

脚本会读取 SQLite 数据库中的普通表，生成 MySQL 建表语句和批量 `INSERT` 语句，适合把 New API 从 SQLite 迁移到 MySQL。

## 适用场景

- New API 当前使用 SQLite 数据库
- 需要迁移到 MySQL / MariaDB
- 希望先导出 SQL 文件，再手动导入目标数据库

## 数据库表说明

当前 `one-api.db` 中共有 31 张普通业务表：

| 表名 | 说明 |
| --- | --- |
| `abilities` | 模型、分组和渠道能力配置 |
| `authz_roles` | 权限角色配置 |
| `casbin_rule` | Casbin 权限规则 |
| `channels` | 上游渠道和模型代理配置 |
| `checkins` | 用户签到和奖励记录 |
| `custom_oauth_providers` | 自定义 OAuth 登录提供商配置 |
| `logs` | 请求日志和用量日志 |
| `midjourneys` | Midjourney 任务记录 |
| `models` | 模型列表和模型元数据 |
| `options` | 系统配置项 |
| `passkey_credentials` | Passkey / WebAuthn 凭据 |
| `perf_metrics` | 模型请求性能统计 |
| `prefill_groups` | 预填分组配置 |
| `quota_data` | 用户、模型、渠道等维度的额度统计 |
| `redemptions` | 兑换码和兑换记录 |
| `setups` | 系统初始化和版本记录 |
| `subscription_orders` | 订阅订单记录 |
| `subscription_plans` | 订阅套餐配置 |
| `subscription_pre_consume_records` | 订阅额度预扣记录 |
| `system_instances` | 系统节点实例状态 |
| `system_task_locks` | 系统任务锁 |
| `system_tasks` | 系统异步任务记录 |
| `tasks` | 绘图、异步请求等任务记录 |
| `tokens` | 用户 API Token 配置和用量 |
| `top_ups` | 充值订单记录 |
| `two_fa_backup_codes` | 二步验证备用码 |
| `two_fas` | 用户二步验证配置 |
| `user_oauth_bindings` | 用户 OAuth 账号绑定关系 |
| `user_subscriptions` | 用户订阅记录 |
| `users` | 用户账号、额度和登录信息 |
| `vendors` | 模型供应商配置 |

## 环境要求

- Python 3.9 或更高版本
- MySQL 5.7 / 8.0 或 MariaDB
- 不需要安装第三方 Python 依赖

## 迁移步骤

### 1. 停止 New API

迁移前建议先停止 New API 服务，避免迁移过程中 SQLite 数据库继续写入。

如果你使用 Docker Compose：

```bash
docker compose down
```

如果你使用其他方式部署，请按你的部署方式停止 New API 进程。

### 2. 备份 SQLite 数据库

先备份 New API 当前使用的 SQLite 数据库文件。

示例：

```bash
cp one-api.db one-api.db.bak
```

实际文件名和路径以你的部署环境为准。

### 3. 导出 MySQL SQL 文件

运行脚本，把 SQLite 数据库导出为 MySQL SQL 文件：

```bash
python sqlite_to_mysql_newapi.py
```

如果数据量较大，可以调大每条 `INSERT` 的行数：

```bash
python sqlite_to_mysql_newapi.py one-api.db one-api.sql --batch-size 1000
```

### 4. 创建 MySQL 数据库

登录 MySQL 后创建数据库：

```sql
CREATE DATABASE new_api DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5. 导入 SQL 文件

```bash
mysql -u root -p new_api < one-api.sql
```

如果 SQL 文件较大，建议使用命令行导入，不建议通过 Web 管理工具上传。

### 6. 修改 New API 数据库配置

导入完成后，将 New API 的数据库连接改为 MySQL。

示例 SQL_DSN：

```text
root:password@tcp(127.0.0.1:3306)/new_api?charset=utf8mb4&parseTime=True&loc=Local
```

请把用户名、密码、主机、端口和数据库名替换为你的实际配置。

配置完成后重新启动 New API，并确认服务能正常访问。

## 参数说明

```text
python sqlite_to_mysql_newapi.py [sqlite_db] [output_sql] [--batch-size BATCH_SIZE]
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `sqlite_db` | `one-api.db` | SQLite 数据库文件路径 |
| `output_sql` | `one-api.sql` | 导出的 MySQL SQL 文件路径 |
| `--batch-size` | `500` | 每条批量 `INSERT` 语句包含的行数 |

如果你的 SQLite 数据库文件不叫 `one-api.db`，请显式指定输入和输出文件：

```bash
python sqlite_to_mysql_newapi.py /path/to/one-api.db one-api.sql
```

查看命令帮助：

```bash
python sqlite_to_mysql_newapi.py --help
```

## 导出内容

脚本会导出：

- SQLite 中的普通表
- 表结构
- 表数据
- 主键
- 常见字段类型转换

脚本不会导出：

- SQLite 内部表，例如 `sqlite_sequence`
- 索引
- 视图
- 触发器
- 外键约束

## 类型转换说明

常见 SQLite 类型会转换为 MySQL 类型，例如：

| SQLite 类型 | MySQL 类型 |
| --- | --- |
| `INTEGER` | `BIGINT` |
| `REAL` / `FLOAT` / `DOUBLE` | `DOUBLE` |
| `TEXT` | `LONGTEXT` |
| `BLOB` | `LONGBLOB` |
| `BOOLEAN` / `NUMERIC` | `DECIMAL(20,6)` |
| `DATE` / `TIME` / `DATETIME` | `DATETIME` |

单列整型主键会导出为 `AUTO_INCREMENT`。

## 注意事项

- 迁移前一定要备份 SQLite 数据库。
- 导出期间会以只读方式打开 SQLite 数据库。
- 导出的 SQL 会使用 `utf8mb4` 字符集。
- 导出的 SQL 会先 `DROP TABLE IF EXISTS`，再重新创建表。
- 导入前请确认目标 MySQL 数据库中没有需要保留的同名表。

## 完整示例

```bash
python sqlite_to_mysql_newapi.py
mysql -u root -p new_api < one-api.sql
```
