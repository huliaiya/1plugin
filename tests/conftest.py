"""tests conftest - 共享 fixture（MySQL 集成测试）"""

import os
import uuid

import pytest

# MySQL 测试配置（可通过环境变量覆盖）
MYSQL_TEST_HOST = os.environ.get("MYSQL_TEST_HOST", "127.0.0.1")
MYSQL_TEST_PORT = int(os.environ.get("MYSQL_TEST_PORT", "3306"))
MYSQL_TEST_USER = os.environ.get("MYSQL_TEST_USER", "root")
MYSQL_TEST_PASSWORD = os.environ.get("MYSQL_TEST_PASSWORD", "")
MYSQL_TEST_DB_PREFIX = os.environ.get("MYSQL_TEST_DB_PREFIX", "fox_toolbox_test")


async def _ensure_mysql_available():
    """检查 MySQL 是否可用，不可用则抛出 RuntimeError"""
    import aiomysql
    try:
        conn = await aiomysql.connect(
            host=MYSQL_TEST_HOST,
            port=MYSQL_TEST_PORT,
            user=MYSQL_TEST_USER,
            password=MYSQL_TEST_PASSWORD,
            autocommit=True,
        )
        conn.close()
        await conn.ensure_closed()
    except Exception as e:
        raise RuntimeError(f"MySQL 不可用: {e}")


async def _create_test_database(db_name: str):
    """创建测试数据库"""
    import aiomysql
    conn = await aiomysql.connect(
        host=MYSQL_TEST_HOST,
        port=MYSQL_TEST_PORT,
        user=MYSQL_TEST_USER,
        password=MYSQL_TEST_PASSWORD,
        autocommit=True,
    )
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
            )
    finally:
        conn.close()
        await conn.ensure_closed()


async def _drop_test_database(db_name: str):
    """删除测试数据库"""
    import aiomysql
    conn = await aiomysql.connect(
        host=MYSQL_TEST_HOST,
        port=MYSQL_TEST_PORT,
        user=MYSQL_TEST_USER,
        password=MYSQL_TEST_PASSWORD,
        autocommit=True,
    )
    try:
        async with conn.cursor() as cur:
            await cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
    finally:
        conn.close()
        await conn.ensure_closed()


@pytest.fixture
async def mysql_db():
    """创建一个独立的 MySQL 测试数据库并返回已初始化的 Database 实例。

    如果 MySQL 不可用，自动跳过测试。
    """
    try:
        await _ensure_mysql_available()
    except RuntimeError as e:
        pytest.skip(f"MySQL 集成测试跳过: {e}")

    from astrbot_plugin_fox_toolbox.fox_toolbox.database import Database

    db_name = f"{MYSQL_TEST_DB_PREFIX}_{uuid.uuid4().hex[:8]}"
    await _create_test_database(db_name)

    mysql_config = {
        "host": MYSQL_TEST_HOST,
        "port": MYSQL_TEST_PORT,
        "user": MYSQL_TEST_USER,
        "password": MYSQL_TEST_PASSWORD,
        "database": db_name,
    }

    database = Database("test_plugin", mysql_config)
    await database.init()

    yield database

    await database.close()
    await _drop_test_database(db_name)
