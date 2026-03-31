"""
data_processor.py
-----------------
쿼리 결과 DataFrame을 차트/UI 용으로 가공하는 전처리 레이어.
- 단위 변환, 결측값 처리, 레이블 포맷 등을 담당합니다.
"""

import os
import pandas as pd
import numpy as np

BAD_RATE_WARNING = float(os.getenv("BAD_RATE_WARNING", 3.0))
BAD_RATE_DANGER  = float(os.getenv("BAD_RATE_DANGER",  5.0))
UTIL_WARNING     = float(os.getenv("UTIL_RATE_WARNING", 70.0))
UTIL_DANGER      = float(os.getenv("UTIL_RATE_DANGER",  50.0))


# ─── 색상 유틸 ────────────────────────────────────────────────

def bad_rate_color(rate: float) -> str:
    """불량률에 따른 신호등 색상 반환."""
    if rate >= BAD_RATE_DANGER:
        return "#FF4B4B"   # 위험 — 빨강
    elif rate >= BAD_RATE_WARNING:
        return "#FFA500"   # 경고 — 주황
    return "#00C49F"       # 정상 — 초록


def util_rate_color(rate: float) -> str:
    """가동률에 따른 신호등 색상 반환."""
    if rate <= UTIL_DANGER:
        return "#FF4B4B"
    elif rate <= UTIL_WARNING:
        return "#FFA500"
    return "#00C49F"


def util_rate_status(rate: float) -> str:
    """가동률 상태 텍스트."""
    if rate <= UTIL_DANGER:
        return "🔴 위험"
    elif rate <= UTIL_WARNING:
        return "🟡 경고"
    return "🟢 정상"


def achieve_rate_color(rate: float) -> str:
    """달성률에 따른 색상."""
    if rate >= 100:
        return "#00C49F"
    elif rate >= 80:
        return "#FFA500"
    return "#FF4B4B"


# ─── 시간대별 생산 전처리 ─────────────────────────────────────

def process_hourly_production(df: pd.DataFrame) -> pd.DataFrame:
    """시간대별 생산 데이터 결측 시간 채우기 및 포맷."""
    if df.empty:
        return df

    df = df.copy()
    df["hour"]      = df["hour"].astype(int)
    df["ok_qty"]    = df["ok_qty"].fillna(0).astype(int)
    df["ng_qty"]    = df["ng_qty"].fillna(0).astype(int)
    df["prod_qty"] = df["prod_qty"].fillna(0).astype(int)

    # 0~23시 전체 채우기 (데이터 없는 시간대는 0)
    all_hours = pd.DataFrame({"hour": range(24)})
    df = all_hours.merge(df, on="hour", how="left").fillna(0)
    df["hour_label"] = df["hour"].apply(lambda h: f"{int(h):02d}:00")

    # 시간대별 불량률
    df["bad_rate"] = np.where(
        df["prod_qty"] > 0,
        (df["ng_qty"] / df["prod_qty"] * 100).round(2),
        0.0
    )
    return df


# ─── 라인별 생산 전처리 ───────────────────────────────────────

def process_line_production(df: pd.DataFrame) -> pd.DataFrame:
    """라인별 생산 데이터 포맷 및 색상 추가."""
    if df.empty:
        return df

    df = df.copy()
    df["ok_qty"]    = df["ok_qty"].fillna(0).astype(int)
    df["ng_qty"]    = df["ng_qty"].fillna(0).astype(int)
    df["prod_qty"] = df["prod_qty"].fillna(0).astype(int)
    df["bad_rate"]  = df["bad_rate"].fillna(0.0).astype(float)
    df["bar_color"] = df["bad_rate"].apply(bad_rate_color)
    return df


# ─── 불량 유형 전처리 ─────────────────────────────────────────

def process_defect_types(df: pd.DataFrame) -> pd.DataFrame:
    """불량 유형 데이터 정제."""
    if df.empty:
        return df

    df = df.copy()
    df["bad_qty"]  = df["bad_qty"].fillna(0).astype(int)
    df["bad_name"] = df["bad_name"].fillna("미분류")
    # 수량 0인 항목 제거
    df = df[df["bad_qty"] > 0].reset_index(drop=True)
    return df


# ─── 비가동 전처리 ────────────────────────────────────────────

def process_downtime(df: pd.DataFrame) -> pd.DataFrame:
    """비가동 데이터 정제."""
    if df.empty:
        return df

    df = df.copy()
    df["down_min"]  = df["down_min"].fillna(0).astype(float)
    df["biga_name"] = df["biga_name"].fillna("미분류")
    df = df[df["down_min"] > 0].reset_index(drop=True)
    return df


# ─── 주간 추이 전처리 ─────────────────────────────────────────

def process_weekly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """최근 7일 추이 데이터 날짜 포맷 정제."""
    if df.empty:
        return df

    df = df.copy()
    df["ymd"]       = pd.to_datetime(df["ymd"], format="%Y-%m-%d", errors="coerce")
    df["date_label"] = df["ymd"].dt.strftime("%m/%d")
    df["ok_qty"]    = df["ok_qty"].fillna(0).astype(int)
    df["ng_qty"]    = df["ng_qty"].fillna(0).astype(int)
    df["prod_qty"] = df["prod_qty"].fillna(0).astype(int)
    df["bad_rate"]  = df["bad_rate"].fillna(0.0).astype(float)
    return df


# ─── 작업지시 전처리 ──────────────────────────────────────────

def process_work_orders(df: pd.DataFrame) -> pd.DataFrame:
    """작업지시 DataFrame 정제 및 달성률 계산."""
    if df.empty:
        return df

    df = df.copy()
    df["지시수량"]      = df["지시수량"].fillna(0).astype(float)
    df["생산확인수량"]  = df["생산확인수량"].fillna(0).astype(float)
    df["달성률(%)"]     = np.where(
        df["지시수량"] > 0,
        (df["생산확인수량"] / df["지시수량"] * 100).round(1),
        0.0
    )
    df["긴급여부"] = df["긴급여부"].apply(
        lambda x: "🚨 긴급" if x == "1" else ""
    )
    return df


# ─── 가동률 시계열 전처리 ─────────────────────────────────────

def process_utilization_ts(df: pd.DataFrame) -> pd.DataFrame:
    """가동률 시계열 데이터 정제."""
    if df.empty:
        return df

    df = df.copy()
    df["GDATE"] = pd.to_datetime(df["GDATE"], errors="coerce")
    df["RATE"]  = df["RATE"].fillna(0).astype(float)
    df["ARATE"] = df["ARATE"].fillna(0).astype(float)
    df["RCNT"]  = df["RCNT"].fillna(0).astype(int)
    df["BCNT"]  = df["BCNT"].fillna(0).astype(int)
    return df
