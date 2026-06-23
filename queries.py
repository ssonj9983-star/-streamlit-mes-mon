"""
queries.py
----------
모든 SQL 쿼리를 한 곳에서 관리합니다.

[핵심 테이블 관계 — 실제 MES/POP 구조]
─────────────────────────────────────────────────────────
 pop_sil  (a)          : 생산실적 헤더 (시작/종료시간, WGBN, LINE_NO …)
   ↕  a.REFYMD = b.YMD  AND  a.REFSEQ = b.SEQ
 pop_sil_select  (b)   : 작업지시 선택 현황 (PNO, PNAME, JISIYMD, JISISEQ …)
   ↕  b.JISIYMD+JISISEQ = pop_work_order.JISIYMD+JISISEQ

 OK qty   ← pop_lot_info   (mill_cd, line_no, silymd, silseq, silcnt=a.cnt,
                              refymd=b.ymd, refseq=b.seq, refcnt=b.cnt)
 NG qty   ← pop_badno      (mill_cd, line_no,
                              refymd=b.JISIYMD, refseq=b.JISISEQ, time window)
 생산수량 ← pop_sil_manual  (IFNULL(editqty, silqty), actgbn='A')
 작업장명 ← pop_code        (MAIN_CODE='WRKCTR', SUB_CODE=LINE_NO)
─────────────────────────────────────────────────────────
"""

import os
import logging
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import text

from database import get_connection, get_mill_cd

logger = logging.getLogger(__name__)
CACHE_TTL = int(os.getenv("CACHE_TTL_SEC", 9))


# ═══════════════════════════════════════════════════════════════
# 헬퍼
# ═══════════════════════════════════════════════════════════════

def _query_to_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    """SQL 실행 후 DataFrame 반환. 오류 시 빈 DataFrame."""
    try:
        with get_connection() as conn:
            result = conn.execute(text(sql), params or {})
            rows   = result.fetchall()
            cols   = list(result.keys())
            return pd.DataFrame(rows, columns=cols)
    except Exception as e:
        logger.error(f"쿼리 실행 오류: {e}\nSQL: {sql[:200]}")
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════
# 공통 LEFT JOIN 서브쿼리 블록 (재사용)
# ═══════════════════════════════════════════════════════════════
# 아래 블록들은 각 쿼리에 인라인으로 삽입합니다.
# ─────────────────────────────────────────────────────────────
# [LOT_OK]  pop_lot_info → 양품수량 (inqty 합계)
_LOT_OK_SUB = """
    LEFT JOIN (
        SELECT mill_cd, line_no, silymd, silseq, silcnt,
               refymd, refseq, refcnt,
               SUM(inqty) AS ok_qty
          FROM pop_lot_info
         GROUP BY mill_cd, line_no, silymd, silseq, silcnt,
                  refymd, refseq, refcnt
    ) lot
      ON  lot.mill_cd = a.mill_cd
      AND lot.line_no = a.line_no
      AND lot.silymd  = a.silymd
      AND lot.silseq  = a.silseq
      AND lot.silcnt  = a.cnt
      AND lot.refymd  = b.ymd
      AND lot.refseq  = b.seq
      AND lot.refcnt  = b.cnt
"""

# [BAD_NG]  pop_badno → 불량수량 (badqty 합계, 일별 지시 기준 집계)
#  ※ 시간필터(frtime~totime)는 대시보드 집계 레벨에서 단순화
_BAD_NG_SUB = """
    LEFT JOIN (
        SELECT mill_cd, line_no, refymd, refseq,
               SUM(badqty) AS ng_qty
          FROM pop_badno
         GROUP BY mill_cd, line_no, refymd, refseq
    ) bad
      ON  bad.mill_cd = b.mill_cd
      AND bad.line_no = b.line_no
      AND bad.refymd  = b.jisiymd
      AND bad.refseq  = b.jisiseq
"""

# [MAN_PROD]  pop_sil_manual → 실적(생산)수량 IFNULL(editqty, silqty)
_MAN_PROD_SUB = """
    LEFT JOIN (
        SELECT mill_cd, line_no, silymd, silseq, silcnt,
               refymd, refseq, refcnt,
               SUM(IFNULL(editqty, silqty)) AS prod_qty
          FROM pop_sil_manual
         WHERE actgbn = 'A'
         GROUP BY mill_cd, line_no, silymd, silseq, silcnt,
                  refymd, refseq, refcnt
    ) man
      ON  man.mill_cd = a.mill_cd
      AND man.line_no = a.line_no
      AND man.silymd  = a.silymd
      AND man.silseq  = a.silseq
      AND man.silcnt  = a.cnt
      AND man.refymd  = b.ymd
      AND man.refseq  = b.seq
      AND man.refcnt  = b.cnt
"""

# [WRKCTR]  pop_code → 작업장(라인) 한글명
_WRKCTR_JOIN = """
    LEFT JOIN pop_code z
      ON  z.mill_cd   = a.mill_cd
      AND z.main_code = 'WRKCTR'
      AND z.sub_code  = a.line_no
"""


# ═══════════════════════════════════════════════════════════════
# 1. 오늘의 생산실적 KPI 집계
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_today_production_kpi(target_date: str | None = None) -> dict:
    """
    오늘(또는 지정일) 총 양품·불량·생산수량, 불량률, 운영 라인 수 반환.

    관련 테이블:
      pop_sil  →  pop_sil_select  →  pop_lot_info (okqty)
                                  →  pop_badno    (ngqty)
                                  →  pop_sil_manual (prodqty)
    """
    ymd      = target_date or date.today().strftime("%Y-%m-%d")
    mill_cd  = get_mill_cd()

    sql = f"""
        SELECT
            COALESCE(SUM(lot.ok_qty),   0) AS total_ok,
            COALESCE(SUM(bad.ng_qty),   0) AS total_ng,
            COALESCE(SUM(man.prod_qty), 0) AS total_prod,
            COUNT(DISTINCT a.line_no)       AS line_count
          FROM pop_sil a
          JOIN pop_sil_select b
            ON  a.mill_cd = b.mill_cd
            AND a.refymd  = b.ymd
            AND a.refseq  = b.seq
        {_LOT_OK_SUB}
        {_BAD_NG_SUB}
        {_MAN_PROD_SUB}
         WHERE a.mill_cd = :mill_cd
           AND a.silymd  = :ymd
           AND a.wgbn    = 'W'
           AND a.actgbn  = 'A'
    """
    df = _query_to_df(sql, {"mill_cd": mill_cd, "ymd": ymd})
    if df.empty:
        return {"total_ok": 0, "total_ng": 0, "total_prod": 0,
                "bad_rate": 0.0, "line_count": 0}

    row        = df.iloc[0]
    total_ok   = int(row["total_ok"]   or 0)
    total_ng   = int(row["total_ng"]   or 0)
    total_prod = int(row["total_prod"] or 0)

    # 생산수량이 0이면 ok+ng 합산으로 fallback
    if total_prod == 0:
        total_prod = total_ok + total_ng

    bad_rate = round(total_ng / total_prod * 100, 2) if total_prod > 0 else 0.0
    return {
        "total_ok":   total_ok,
        "total_ng":   total_ng,
        "total_prod": total_prod,
        "bad_rate":   bad_rate,
        "line_count": int(row["line_count"] or 0),
    }


# ═══════════════════════════════════════════════════════════════
# 2. 오늘의 작업지시 대비 달성률
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_today_achievement_rate(target_date: str | None = None) -> dict:
    """
    pop_work_order 지시량 vs pop_lot_info 실적 양품 비교.
    작업지시의 JISIYMD 기준이므로 ymd8(YYYYMMDD) 포맷 사용.
    """
    ymd     = target_date or date.today().strftime("%Y-%m-%d")
    ymd8    = ymd.replace("-", "")
    mill_cd = get_mill_cd()

    # 오늘 작업지시 총 지시량
    sql_order = """
        SELECT COALESCE(SUM(QTY), 0) AS order_qty
          FROM pop_work_order
         WHERE MILL_CD  = :mill_cd
           AND JISIYMD  = :ymd8
           AND ACTGBN   = 'A'
    """
    df_ord    = _query_to_df(sql_order, {"mill_cd": mill_cd, "ymd8": ymd8})
    order_qty = float(df_ord.iloc[0]["order_qty"]) if not df_ord.empty else 0.0

    # 오늘 실적 양품 합계 (pop_lot_info 기준)
    sql_ok = f"""
        SELECT COALESCE(SUM(lot.ok_qty), 0) AS prod_ok
          FROM pop_sil a
          JOIN pop_sil_select b
            ON  a.mill_cd = b.mill_cd
            AND a.refymd  = b.ymd
            AND a.refseq  = b.seq
        {_LOT_OK_SUB}
         WHERE a.mill_cd = :mill_cd
           AND a.silymd  = :ymd
           AND a.wgbn    = 'W'
           AND a.actgbn  = 'A'
    """
    df_ok    = _query_to_df(sql_ok, {"mill_cd": mill_cd, "ymd": ymd})
    prod_qty = float(df_ok.iloc[0]["prod_ok"]) if not df_ok.empty else 0.0

    achieve_rate = round(prod_qty / order_qty * 100, 1) if order_qty > 0 else 0.0
    return {
        "order_qty":    order_qty,
        "prod_qty":     prod_qty,
        "achieve_rate": achieve_rate,
    }


# ═══════════════════════════════════════════════════════════════
# 3. 공장 가동률 (최신값)
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_factory_utilization(target_date: str | None = None) -> dict:
    """pop_factory_utilization 에서 오늘 가장 최근 수집 레코드."""
    ymd     = target_date or date.today().strftime("%Y%m%d")
    mill_cd = get_mill_cd()

    sql = """
        SELECT ACNT, RCNT, BCNT, NCNT, RATE, ARATE, GDATE
          FROM pop_factory_utilization
         WHERE MILL_CD = :mill_cd
           AND YMD     = :ymd
         ORDER BY SEQ DESC
         LIMIT 1
    """
    df = _query_to_df(sql, {"mill_cd": mill_cd, "ymd": ymd})
    if df.empty:
        return {"acnt": 0, "rcnt": 0, "bcnt": 0, "ncnt": 0,
                "rate": 0.0, "arate": 0.0, "gdate": None}
    row = df.iloc[0]
    return {
        "acnt":  int(row["ACNT"]  or 0),
        "rcnt":  int(row["RCNT"]  or 0),
        "bcnt":  int(row["BCNT"]  or 0),
        "ncnt":  int(row["NCNT"]  or 0),
        "rate":  float(row["RATE"]  or 0.0),
        "arate": float(row["ARATE"] or 0.0),
        "gdate": row["GDATE"],
    }


# ═══════════════════════════════════════════════════════════════
# 4. 시간대별 생산량 추이 (오늘)
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_hourly_production(target_date: str | None = None) -> pd.DataFrame:
    """
    pop_sil TOTIME 기준 시간대(HOUR)별 양품·불량·생산수량 집계.
    OK → pop_lot_info / NG → pop_badno / PROD → pop_sil_manual
    """
    ymd     = target_date or date.today().strftime("%Y-%m-%d")
    mill_cd = get_mill_cd()

    sql = f""" 
        SELECT
            HOUR(a.totime)               AS hour,
            COALESCE(SUM(lot.ok_qty),  0) AS ok_qty,
            COALESCE(SUM(bad.ng_qty),  0) AS ng_qty,
            COALESCE(SUM(man.prod_qty),0) AS prod_qty
          FROM pop_sil a
          JOIN pop_sil_select b
            ON  a.mill_cd = b.mill_cd
            AND a.refymd  = b.ymd
            AND a.refseq  = b.seq
        {_LOT_OK_SUB}
        {_BAD_NG_SUB}
        {_MAN_PROD_SUB}
         WHERE a.mill_cd  = :mill_cd
           AND a.silymd   = :ymd
           AND a.wgbn     = 'W'
           AND a.actgbn   = 'A'
           AND a.totime  IS NOT NULL
         GROUP BY HOUR(a.totime)
         ORDER BY hour
    """
    return _query_to_df(sql, {"mill_cd": mill_cd, "ymd": ymd})


# ═══════════════════════════════════════════════════════════════
# 5. 라인별 생산현황 (오늘)
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_line_production(target_date: str | None = None) -> pd.DataFrame:
    """
    라인(LINE_NO)별 양품·불량·생산수량, 불량률.
    작업장 한글명은 pop_code MAIN_CODE='WRKCTR' 에서 조회.
    """
    ymd     = target_date or date.today().strftime("%Y-%m-%d")
    mill_cd = get_mill_cd()

    sql = f"""
        SELECT
            a.line_no,
            COALESCE(z.code_name, a.line_no)  AS wrkctr_name,
            COALESCE(SUM(lot.ok_qty),   0)    AS ok_qty,
            COALESCE(SUM(bad.ng_qty),   0)    AS ng_qty,
            COALESCE(SUM(man.prod_qty), 0)    AS prod_qty,
            ROUND(
                COALESCE(SUM(bad.ng_qty), 0)
                / NULLIF(COALESCE(SUM(man.prod_qty), 0)
                         + COALESCE(SUM(bad.ng_qty), 0), 0)
                * 100, 2
            )                                  AS bad_rate
          FROM pop_sil a
          JOIN pop_sil_select b
            ON  a.mill_cd = b.mill_cd
            AND a.refymd  = b.ymd
            AND a.refseq  = b.seq
        {_LOT_OK_SUB}
        {_BAD_NG_SUB}
        {_MAN_PROD_SUB}
        {_WRKCTR_JOIN}
         WHERE a.mill_cd = :mill_cd
           AND a.silymd  = :ymd
           AND a.wgbn    = 'W'
           AND a.actgbn  = 'A'
         GROUP BY a.line_no, z.code_name
         ORDER BY prod_qty DESC
    """
    return _query_to_df(sql, {"mill_cd": mill_cd, "ymd": ymd})


# ═══════════════════════════════════════════════════════════════
# 6. 불량 유형별 현황 (오늘)
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_defect_by_type(target_date: str | None = None) -> pd.DataFrame:
    """
    오늘 발생한 불량을 BADNO(불량코드)별로 집계.
    불량 기록의 ADDYMD 날짜 기준으로 필터링하며,
    불량코드 명칭은 pop_code MAIN_CODE='BADCD' 에서 JOIN.

    pop_badno 조인 방식:
      pop_badno.REFYMD  = pop_sil_select.JISIYMD  (작업지시일)
      pop_badno.REFSEQ  = pop_sil_select.JISISEQ  (작업지시순번)
      pop_badno.LINE_NO = pop_sil_select.LINE_NO
    """
    ymd     =  target_date or date.today().strftime("%Y-%m-%d")
    mill_cd = get_mill_cd()

    sql = """
        SELECT
            bd.badno,
            COALESCE(c.code_name, bd.badno)  AS bad_name,
            SUM(bd.badqty)                   AS bad_qty
          FROM pop_badno bd
          -- 당일 실적에 연결된 불량만 조회
          JOIN pop_sil_select b
            ON  b.mill_cd  = bd.mill_cd
            AND b.jisiymd  = bd.refymd
            AND b.jisiseq  = bd.refseq
            AND b.line_no  = bd.line_no
          JOIN pop_sil a
            ON  a.mill_cd  = b.mill_cd
            AND a.refymd   = b.ymd
            AND a.refseq   = b.seq
            AND a.silymd   = :ymd
            AND a.wgbn     = 'W'
            AND a.actgbn   = 'A'
          LEFT JOIN pop_code c
            ON  c.mill_cd   = bd.mill_cd
            AND c.main_code = 'BADCD'
            AND c.sub_code  = bd.badno
         WHERE bd.mill_cd = :mill_cd
         GROUP BY bd.badno, bad_name
         ORDER BY bad_qty DESC
         LIMIT 10
    """
    return _query_to_df(sql, {"mill_cd": mill_cd, "ymd": ymd})


# ═══════════════════════════════════════════════════════════════
# 7. 비가동 현황 (오늘)
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_downtime_summary(target_date: str | None = None) -> pd.DataFrame:
    """
    pop_bigadong 에서 라인·비가동코드별 비가동시간(분) 집계.
    비가동코드 명칭은 pop_code MAIN_CODE='NOTWORKCD' 에서 JOIN.
    """
    ymd     = target_date or date.today().strftime("%Y-%m-%d")
    mill_cd = get_mill_cd()

    sql = """
        SELECT
            bg.line_no,
            bg.bigacd,
            COALESCE(c.code_name, bg.bigacd)          AS biga_name,
            ROUND(SUM(CAST(bg.bigatime AS UNSIGNED))
                  / 60.0, 1)                           AS down_min
          FROM pop_bigadong bg
          LEFT JOIN pop_code c
            ON  c.mill_cd   = bg.mill_cd
            AND c.main_code = 'NOTWORKCD'
            AND c.sub_code  = bg.bigacd
         WHERE bg.mill_cd = :mill_cd
           AND bg.ymd     = :ymd
         GROUP BY bg.line_no, bg.bigacd, biga_name
         ORDER BY down_min DESC
         LIMIT 20
    """
    return _query_to_df(sql, {"mill_cd": mill_cd, "ymd": ymd})


# ═══════════════════════════════════════════════════════════════
# 8. 현재 진행 중인 작업지시 현황
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_active_work_orders(target_date: str | None = None) -> pd.DataFrame:
    """
    오늘 지시된 작업지시 목록 + 실적 양품수량(pop_lot_info 기준) JOIN.
    달성률 = 실적 양품수량 / 지시수량.
    """
    ymd8    = target_date or date.today().strftime("%Y%m%d")
    mill_cd = get_mill_cd()

    sql = """
        SELECT
            w.line_no                            AS 작업장,
            COALESCE(z.code_name, w.line_no)     AS 작업장명,
            w.jisiymd                            AS 지시일자,
            w.jisiseq                            AS 지시번호,
            w.pno                                AS 품번,
            COALESCE(i.pname, w.pno)             AS 품명,
            COALESCE(w.qty, 0)                   AS 지시수량,
            COALESCE(ok.ok_qty, 0)               AS 생산확인수량,
            CASE w.stategbn
                WHEN '완료' THEN '✅ 완료'
                WHEN 'C'    THEN '✅ 완료'
                WHEN 'W'    THEN '🔄 진행중'
                ELSE             '⏳ 대기'
            END                                  AS 상태표시,
            w.urgent_yn                          AS 긴급여부
          FROM pop_work_order w
          -- 작업장 한글명
          LEFT JOIN pop_code z
            ON  z.mill_cd   = w.mill_cd
            AND z.main_code = 'ROUTE'
            AND z.sub_code  = w.line_no
          -- 품명
          LEFT JOIN pop_item i
            ON  i.mill_cd = w.mill_cd
            AND i.pno     = w.pno
          -- 실적 양품수량: 해당 작업지시에 연결된 lot_info 합계
          LEFT JOIN (
              SELECT
                  b2.mill_cd, b2.jisiymd, b2.jisiseq,
                  SUM(li.inqty) AS ok_qty
                FROM pop_sil_select b2
                JOIN pop_sil a2
                  ON  a2.mill_cd = b2.mill_cd
                  AND a2.refymd  = b2.ymd
                  AND a2.refseq  = b2.seq
                  AND a2.wgbn    = 'W'
                  AND a2.actgbn  = 'A'
                JOIN pop_lot_info li
                  ON  li.mill_cd = a2.mill_cd 
                  AND li.line_no = a2.line_no
                  AND li.silymd  = a2.silymd
                  AND li.silseq  = a2.silseq
                  AND li.silcnt  = a2.cnt
                  AND li.refymd  = b2.ymd
                  AND li.refseq  = b2.seq
                  AND li.refcnt  = b2.cnt
                  AND li.silymd = :ymd8
               GROUP BY b2.mill_cd, b2.jisiymd, b2.jisiseq
          ) ok
            ON  ok.mill_cd  = w.mill_cd
            AND ok.jisiymd  = w.jisiymd
            AND ok.jisiseq  = w.jisiseq
         WHERE w.mill_cd = :mill_cd
           AND w.frymd = :ymd8
           AND w.actgbn  = 'A'
         ORDER BY w.sort_no, w.jisiseq
    """
    return _query_to_df(sql, {"mill_cd": mill_cd, "ymd8": ymd8})


# ═══════════════════════════════════════════════════════════════
# 9. 최근 7일 일별 생산 추이
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_weekly_production_trend() -> pd.DataFrame:
    """
    최근 7일간 일별 생산수량(pop_sil_manual)·양품(pop_lot_info)·
    불량(pop_badno) 추이.
    """
    mill_cd = get_mill_cd()

    sql = f"""
        SELECT
            a.silymd                             AS ymd,
            COALESCE(SUM(lot.ok_qty),   0)       AS ok_qty,
            COALESCE(SUM(bad.ng_qty),   0)       AS ng_qty,
            COALESCE(SUM(man.prod_qty), 0)       AS prod_qty,
            ROUND(
                COALESCE(SUM(bad.ng_qty), 0)
                / NULLIF(COALESCE(SUM(man.prod_qty), 0)
                         + COALESCE(SUM(bad.ng_qty),  0), 0)
                * 100, 2
            )                                    AS bad_rate
          FROM pop_sil a
          JOIN pop_sil_select b
            ON  a.mill_cd = b.mill_cd
            AND a.refymd  = b.ymd
            AND a.refseq  = b.seq
        {_LOT_OK_SUB}
        {_BAD_NG_SUB}
        {_MAN_PROD_SUB}
         WHERE a.mill_cd = :mill_cd
           AND a.silymd  >= DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 6 DAY), '%Y%m%d') 
           AND a.wgbn    = 'W'
           AND a.actgbn  = 'A'
         GROUP BY a.silymd
         ORDER BY a.silymd
    """
    return _query_to_df(sql, {"mill_cd": mill_cd})


# ═══════════════════════════════════════════════════════════════
# 10. 공장가동률 시계열 (오늘)
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_utilization_timeseries(target_date: str | None = None) -> pd.DataFrame:
    """pop_factory_utilization 오늘 시계열 가동률 데이터."""
    ymd     = target_date or date.today().strftime("%Y%m%d")
    mill_cd = get_mill_cd()

    sql = """
        SELECT GDATE, RATE, ARATE, RCNT, BCNT
          FROM pop_factory_utilization
         WHERE MILL_CD = :mill_cd
           AND YMD     = :ymd
         ORDER BY SEQ
    """
    return _query_to_df(sql, {"mill_cd": mill_cd, "ymd": ymd})


# ═══════════════════════════════════════════════════════════════
# 11. 실적상세 현황 (상세 조회 — 원본 쿼리 기반)
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def get_sil_detail(target_date: str | None = None,
                   line_no: str = "%") -> pd.DataFrame:
    """
    실제 MES/POP 실적상세현황 쿼리 구조 그대로 구현.
    - silno       : 실적번호 (YYMMDD-SEQ-CNT)
    - wrkctr      : 작업장 한글명 (pop_code WRKCTR)
    - pno/pname   : 품번/품명 (pop_sil_select)
    - shift       : 근무조 (pop_code SHIFT)
    - frtime/totime, timegap(h)
    - silqty      : 생산수량 (pop_sil_manual)
    - okqty       : 양품수량 (pop_lot_info)
    - ngqty       : 불량수량 (pop_badno, 시간필터 적용)
    - jisino      : 지시번호
    """
    ymd     = target_date or date.today().strftime("%Y-%m-%d")
    mill_cd = get_mill_cd()

    sql = """
        SELECT
            a.mill_cd,
            DATE_FORMAT(a.silymd, '%Y-%m-%d')         AS silymd,
            CONCAT(
                IFNULL(SUBSTR(a.silymd, 3, 6), ''), '-',
                IFNULL(SUBSTR(a.silseq, 4, 3), ''), '-',
                IFNULL(a.cnt, '')
            )                                          AS silno,
            a.silseq,
            a.cnt,
            COALESCE(z.code_name, a.line_no)           AS wrkctr,
            a.line_no,
            b.pno,
            b.pname,
            (SELECT code_name FROM pop_code
              WHERE mill_cd   = a.mill_cd
                AND main_code = 'SHIFT'
                AND sub_code  = a.shift)               AS shift_name,
            DATE_FORMAT(a.frtime, '%Y-%m-%d %H:%i:%s') AS frtime,
            DATE_FORMAT(a.totime, '%Y-%m-%d %H:%i:%s') AS totime,
            TRUNCATE(
                TIMESTAMPDIFF(MINUTE, a.frtime,
                              IFNULL(a.totime, NOW())) / 60, 2
            )                                          AS timegap_h,
            TIMESTAMPDIFF(MINUTE, a.frtime,
                          IFNULL(a.totime, NOW()))     AS timegap_min,
            (SELECT SUM(IFNULL(editqty, silqty))
               FROM pop_sil_manual x
              WHERE x.mill_cd = a.mill_cd
                AND x.line_no = a.line_no
                AND x.silymd  = a.silymd
                AND x.silseq  = a.silseq
                AND x.silcnt  = a.cnt
                AND x.refymd  = b.ymd
                AND x.refseq  = b.seq
                AND x.refcnt  = b.cnt
                AND x.actgbn  = 'A')                   AS silqty,
            (SELECT SUM(inqty)
               FROM pop_lot_info x
              WHERE x.mill_cd = a.mill_cd
                AND x.line_no = a.line_no
                AND x.silymd  = a.silymd
                AND x.silseq  = a.silseq
                AND x.silcnt  = a.cnt
                AND x.refymd  = b.ymd
                AND x.refseq  = b.seq
                AND x.refcnt  = b.cnt)                 AS okqty,
            (SELECT SUM(badqty)
               FROM pop_badno x
              WHERE x.mill_cd = b.mill_cd
                AND x.line_no = b.line_no
                AND x.refymd  = b.jisiymd
                AND x.refseq  = b.jisiseq
                AND x.addymd >= a.frtime
                AND x.addymd <= IFNULL(a.totime, NOW())) AS ngqty,
            a.macqty,
            CONCAT(IFNULL(b.jisiymd, ''), '-',
                   IFNULL(b.jisiseq, ''))              AS jisino
          FROM pop_sil a
          JOIN pop_sil_select b
            ON  a.mill_cd = b.mill_cd
            AND a.refymd  = b.ymd
            AND a.refseq  = b.seq
          LEFT JOIN pop_code z
            ON  z.mill_cd   = a.mill_cd
            AND z.main_code = 'WRKCTR'
            AND z.sub_code  = a.line_no
         WHERE a.mill_cd  = :mill_cd
           AND a.silymd   = :ymd
           AND a.line_no LIKE :line_no
           AND a.wgbn     = 'W'
           AND a.actgbn   = 'A'
         ORDER BY z.code_name, a.silymd, a.shift, a.frtime
    """
    return _query_to_df(sql, {
        "mill_cd": mill_cd,
        "ymd":     ymd,
        "line_no": line_no,
    })
