# sqlite_to_mysql_newapi
用于将 New API 使用的 SQLite 数据库导出为可导入 MySQL 的 SQL 文件。 脚本会读取 SQLite 数据库中的普通表，生成 MySQL 建表语句和批量 `INSERT` 语句，适合把 New API 从 SQLite 迁移到 MySQL。
