"""
database.py
-----------
MariaDB 커넥션 관리 모듈.
- python-dotenv 로 .env 에서 접속 정보를 로드합니다.
- SQLAlchemy + PyMySQL 드라이버를 사용합니다.
- 커넥션 풀(pool_size=5)로 DB 과부하를 방지합니다.
"""

import os
import logging
from contextlib import contextmanager

import pymysql
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

# .env 로드 (프로젝트 루트 기준)
load_dotenv()

logger = logging.getLogger(__name__)

# ─── 환경변수 읽기 ────────────────────────────────────────────
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", 3306))
DB_NAME     = os.getenv("DB_NAME", "kkimesdb")
DB_USER     = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
MILL_CD     = os.getenv("MILL_CD", "0001")


def _build_engine():
    """SQLAlchemy Engine 생성 (커넥션 풀 포함)."""
    url = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        f"?charset=utf8mb4"
    )
    engine = create_engine(
        url,
        poolclass=QueuePool,
        pool_size=5,           # 동시 커넥션 수
        max_overflow=2,        # 초과 허용 커넥션
        pool_recycle=1800,     # 30분마다 커넥션 재생성 (MariaDB wait_timeout 대응)
        pool_pre_ping=True,    # 사용 전 커넥션 유효성 검사
        echo=False,
    )
    return engine


# 싱글톤 엔진 — 애플리케이션 생명주기 동안 하나만 생성
try:
    _engine = _build_engine()
except Exception as e:
    logger.error(f"DB Engine 생성 실패: {e}")
    _engine = None


@contextmanager
def get_connection():
    """컨텍스트 매니저 방식의 DB 커넥션 제공."""
    if _engine is None:
        raise RuntimeError("DB Engine이 초기화되지 않았습니다. .env 설정을 확인하세요.")
    with _engine.connect() as conn:
        yield conn


def test_connection() -> bool:
    """DB 연결 테스트. 성공 시 True 반환."""
    try:
        with get_connection() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"DB 연결 테스트 실패: {e}")
        return False


def get_mill_cd() -> str:
    """환경변수에서 사업장 코드 반환."""
    return MILL_CD
