"""
ui_components.py
----------------
Plotly 차트 및 Streamlit UI 컴포넌트 렌더링 모듈.

[수정 이력]
- total_qty → prod_qty 컬럼명 통일 (queries.py 변경 반영)
- LINE_NO → line_no / wrkctr_name 소문자 통일
- 라인 차트 전체 shape='spline' 적용 (곡선 표현)
- make_scrolling_ecg_chart() : ECG 심전도 스타일 스크롤링 차트 추가
"""

import os
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data_processor import (
    bad_rate_color, util_rate_color, util_rate_status,
    achieve_rate_color,
    BAD_RATE_WARNING, BAD_RATE_DANGER,
    UTIL_WARNING, UTIL_DANGER,
)

# ─── 공통 Plotly 레이아웃 기본값 ─────────────────────────────
# margin 은 각 함수에서 개별 지정 (중복 키 오류 방지)

_LAYOUT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Malgun Gothic, Apple SD Gothic Neo, sans-serif",
              color="#E0E0E0"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                xanchor="right", x=1),
)

_MARGIN_DEFAULT = dict(l=10, r=10, t=40, b=10)
_MARGIN_GAUGE   = dict(l=20, r=20, t=50, b=10)


# ═══════════════════════════════════════════════════════════════
# 1. KPI 헤더 — st.metric 카드
# ═══════════════════════════════════════════════════════════════

def render_kpi_header(kpi: dict, achievement: dict, utilization: dict) -> None:
    """상단 KPI 카드 5개를 한 줄로 렌더링."""
    total_prod   = kpi.get("total_prod", 0)
    total_ok     = kpi.get("total_ok",   0)
    bad_rate     = kpi.get("bad_rate",   0.0)
    line_count   = kpi.get("line_count", 0)
    achieve_rate = achievement.get("achieve_rate", 0.0)
    util_rate    = utilization.get("rate", 0.0)

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            label="📦 총 생산량",
            value=f"{total_prod:,} EA",
            delta=f"양품 {total_ok:,} EA",
        )
    with col2:
        st.metric(
            label="🎯 목표 달성률",
            value=f"{achieve_rate:.1f} %",
            delta=f"지시 {achievement.get('order_qty', 0):,.0f} / "
                  f"실적 {achievement.get('prod_qty', 0):,.0f}",
            delta_color="off",
        )
    with col3:
        st.metric(
            label="⚠️ 불량률",
            value=f"{bad_rate:.2f} %",
            delta=f"불량 {kpi.get('total_ng', 0):,} EA",
            delta_color="inverse",
        )
    with col4:
        st.metric(
            label="🏭 공장 가동률",
            value=f"{util_rate:.1f} %",
            delta=f"가동 {utilization.get('rcnt', 0)} / "
                  f"전체 {utilization.get('acnt', 0)} 설비",
            delta_color="off",
        )
    with col5:
        st.metric(
            label="🔧 운영 라인 수",
            value=f"{line_count} 개",
            delta=f"비가동 {utilization.get('bcnt', 0)} 설비",
            delta_color="inverse",
        )


# ═══════════════════════════════════════════════════════════════
# 2. 가동률 Gauge 차트
# ═══════════════════════════════════════════════════════════════

def make_utilization_gauge(rate: float) -> go.Figure:
    """가동률 Gauge 차트 (상태에 따라 색상 변경)."""
    color  = util_rate_color(rate)
    status = util_rate_status(rate)

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=rate,
        number={"suffix": "%", "font": {"size": 36, "color": color}},
        delta={"reference": UTIL_WARNING,
               "increasing": {"color": "#00C49F"},
               "decreasing": {"color": "#FF4B4B"}},
        title={"text": f"공장 가동률  {status}", "font": {"size": 16}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1,
                     "tickcolor": "#888", "dtick": 10},
            "bar": {"color": color, "thickness": 0.25},
            "bgcolor": "#1E1E2E",
            "borderwidth": 0,
            "steps": [
                {"range": [0,           UTIL_DANGER],   "color": "#3D1A1A"},
                {"range": [UTIL_DANGER, UTIL_WARNING],  "color": "#3D2D00"},
                {"range": [UTIL_WARNING, 100],          "color": "#1A3D2E"},
            ],
            "threshold": {
                "line": {"color": "#FFFFFF", "width": 3},
                "thickness": 0.75,
                "value": rate,
            },
        },
    ))
    fig.update_layout(**_LAYOUT_BASE, height=260, margin=_MARGIN_GAUGE)
    return fig


# ═══════════════════════════════════════════════════════════════
# 3. 달성률 Gauge 차트
# ═══════════════════════════════════════════════════════════════

def make_achievement_gauge(rate: float) -> go.Figure:
    """목표 달성률 Gauge 차트."""
    color        = achieve_rate_color(rate)
    display_rate = min(rate, 100.0)

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=display_rate,
        number={"suffix": "%", "valueformat": ".1f",
                "font": {"size": 36, "color": color}},
        title={"text": "목표 달성률", "font": {"size": 16}},
        gauge={
            "axis": {"range": [0, 100], "dtick": 20,
                     "tickcolor": "#888"},
            "bar": {"color": color, "thickness": 0.25},
            "bgcolor": "#1E1E2E",
            "borderwidth": 0,
            "steps": [
                {"range": [0,  80],  "color": "#3D1A1A"},
                {"range": [80, 100], "color": "#3D2D00"},
            ],
        },
    ))
    fig.update_layout(**_LAYOUT_BASE, height=260, margin=_MARGIN_GAUGE)
    return fig


# ═══════════════════════════════════════════════════════════════
# 4. 시간대별 생산량 — 스택 막대 + 스플라인 불량률 라인
# ═══════════════════════════════════════════════════════════════

def make_hourly_chart(df: pd.DataFrame) -> go.Figure:
    """시간대별 양품·불량 스택 막대 + 불량률 스플라인 라인 오버레이."""
    if df.empty:
        return _empty_fig("시간대별 생산 데이터가 없습니다")

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df["hour_label"],
        y=df["ok_qty"],
        name="양품",
        marker_color="#4C9BE8",
        hovertemplate="<b>%{x}</b><br>양품: %{y:,} EA<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=df["hour_label"],
        y=df["ng_qty"],
        name="불량",
        marker_color="#FF6B6B",
        hovertemplate="<b>%{x}</b><br>불량: %{y:,} EA<extra></extra>",
    ))
    # 불량률 — 스플라인 곡선 (보조 Y축)
    fig.add_trace(go.Scatter(
        x=df["hour_label"],
        y=df["bad_rate"],
        name="불량률(%)",
        mode="lines+markers",
        line=dict(color="#FFD700", width=2.5, shape="spline",
                  smoothing=1.3, dash="dot"),
        marker=dict(size=6, symbol="circle"),
        yaxis="y2",
        hovertemplate="<b>%{x}</b><br>불량률: %{y:.2f}%<extra></extra>",
    ))

    bad_max = df["bad_rate"].max() if not df["bad_rate"].empty else 0
    fig.update_layout(
        **_LAYOUT_BASE,
        title="⏱️ 시간대별 생산 현황",
        barmode="stack",
        margin=_MARGIN_DEFAULT,
        xaxis=dict(title="시간대", showgrid=False, tickangle=-30),
        yaxis=dict(title="수량 (EA)", showgrid=True, gridcolor="#333344"),
        yaxis2=dict(title="불량률 (%)", overlaying="y", side="right",
                    showgrid=False,
                    range=[0, max(bad_max * 2, 10)]),
        height=340,
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# 5. 라인별 생산현황 — 수평 막대
#    컬럼: line_no, wrkctr_name, ok_qty, ng_qty, prod_qty, bad_rate
# ═══════════════════════════════════════════════════════════════

def make_line_bar_chart(df: pd.DataFrame) -> go.Figure:
    """라인별 양품·불량 수평 누적 막대 차트."""
    if df.empty:
        return _empty_fig("라인별 생산 데이터가 없습니다")

    # wrkctr_name(한글명) 우선, 없으면 line_no 사용
    label_col = "wrkctr_name" if "wrkctr_name" in df.columns else "line_no"

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=df[label_col],
        x=df["ok_qty"],
        name="양품",
        orientation="h",
        marker_color="#4C9BE8",
        hovertemplate="<b>%{y}</b><br>양품: %{x:,} EA<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=df[label_col],
        x=df["ng_qty"],
        name="불량",
        orientation="h",
        marker_color="#FF6B6B",
        hovertemplate=(
            "<b>%{y}</b><br>불량: %{x:,} EA<br>"
            "불량률: %{customdata:.2f}%<extra></extra>"
        ),
        customdata=df["bad_rate"],
    ))

    fig.update_layout(
        **_LAYOUT_BASE,
        title="🏗️ 라인별 생산 현황",
        barmode="stack",
        margin=_MARGIN_DEFAULT,
        xaxis=dict(title="수량 (EA)", showgrid=True, gridcolor="#333344"),
        yaxis=dict(title="작업장", autorange="reversed"),
        height=max(300, len(df) * 55),
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# 6. 불량 유형 도넛 차트
# ═══════════════════════════════════════════════════════════════

def make_defect_pie(df: pd.DataFrame) -> go.Figure:
    """불량 유형별 도넛 차트."""
    if df.empty:
        return _empty_fig("불량 데이터가 없습니다 👍")

    COLORS = [
        "#FF6B6B", "#FF9F43", "#FECA57", "#48DBFB",
        "#FF9FF3", "#54A0FF", "#5F27CD", "#00D2D3",
        "#1DD1A1", "#C8D6E5",
    ]
    fig = go.Figure(go.Pie(
        labels=df["bad_name"],
        values=df["bad_qty"],
        hole=0.55,
        marker=dict(colors=COLORS[:len(df)],
                    line=dict(color="#12121C", width=2)),
        hovertemplate=(
            "<b>%{label}</b><br>"
            "불량수량: %{value:,} EA<br>"
            "비율: %{percent}<extra></extra>"
        ),
        textinfo="label+percent",
        textfont=dict(size=12),
    ))
    fig.update_layout(
        **_LAYOUT_BASE,
        title="🔍 불량 유형 분포",
        height=360,
        margin=_MARGIN_DEFAULT,
        showlegend=True,
        annotations=[dict(text="불량<br>유형", x=0.5, y=0.5,
                          font_size=14, showarrow=False,
                          font_color="#AAAAAA")],
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# 7. 주간 생산 추이 — 스플라인 라인 차트
# ═══════════════════════════════════════════════════════════════

def make_weekly_trend_chart(df: pd.DataFrame) -> go.Figure:
    """최근 7일 일별 생산량·불량률 스플라인 추이."""
    if df.empty:
        return _empty_fig("주간 데이터가 없습니다")

    fig = go.Figure()

    # 총 생산량 — 스플라인 면적 차트
    fig.add_trace(go.Scatter(
        x=df["date_label"],
        y=df["prod_qty"],
        name="총 생산량",
        mode="lines+markers",
        line=dict(color="#4C9BE8", width=2.5, shape="spline", smoothing=1.3),
        marker=dict(size=8, symbol="circle"),
        fill="tozeroy",
        fillcolor="rgba(76,155,232,0.15)",
        hovertemplate="<b>%{x}</b><br>생산량: %{y:,} EA<extra></extra>",
    ))
    # 불량률 — 스플라인 대시 라인
    fig.add_trace(go.Scatter(
        x=df["date_label"],
        y=df["bad_rate"],
        name="불량률(%)",
        mode="lines+markers",
        line=dict(color="#FFD700", width=2, shape="spline",
                  smoothing=1.3, dash="dash"),
        marker=dict(size=7, symbol="diamond"),
        yaxis="y2",
        hovertemplate="<b>%{x}</b><br>불량률: %{y:.2f}%<extra></extra>",
    ))

    # 경고·위험 기준선
    fig.add_hline(y=BAD_RATE_WARNING, yref="y2",
                  line_dash="dot", line_color="#FFA500",
                  annotation_text=f"경고 {BAD_RATE_WARNING}%",
                  annotation_position="bottom right")
    fig.add_hline(y=BAD_RATE_DANGER, yref="y2",
                  line_dash="dot", line_color="#FF4B4B",
                  annotation_text=f"위험 {BAD_RATE_DANGER}%",
                  annotation_position="bottom right")

    fig.update_layout(
        **_LAYOUT_BASE,
        title="📈 최근 7일 생산 추이",
        margin=_MARGIN_DEFAULT,
        xaxis=dict(title="날짜", showgrid=False),
        yaxis=dict(title="생산량 (EA)", showgrid=True, gridcolor="#333344"),
        yaxis2=dict(title="불량률 (%)", overlaying="y",
                    side="right", showgrid=False),
        height=320,
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# 8. 비가동 현황 — 수평 막대 히트맵
# ═══════════════════════════════════════════════════════════════

def make_downtime_chart(df: pd.DataFrame) -> go.Figure:
    """비가동 원인별 시간(분) 수평 막대 차트."""
    if df.empty:
        return _empty_fig("비가동 데이터가 없습니다 ✅")

    label = df["line_no"] + " · " + df["biga_name"]

    fig = go.Figure(go.Bar(
        y=label,
        x=df["down_min"],
        orientation="h",
        marker=dict(
            color=df["down_min"],
            colorscale="Reds",
            showscale=True,
            colorbar=dict(title="분(min)",
                          tickfont=dict(color="#E0E0E0")),
        ),
        hovertemplate="<b>%{y}</b><br>비가동: %{x:.1f} 분<extra></extra>",
    ))
    fig.update_layout(
        **_LAYOUT_BASE,
        title="🛑 비가동 원인별 현황",
        margin=_MARGIN_DEFAULT,
        xaxis=dict(title="비가동 시간 (분)", showgrid=True,
                   gridcolor="#333344"),
        yaxis=dict(autorange="reversed"),
        height=max(280, len(df) * 42),
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# 9. 가동률 시계열 — 스플라인 라인 차트
# ═══════════════════════════════════════════════════════════════

def make_utilization_ts_chart(df: pd.DataFrame) -> go.Figure:
    """오늘 공장 가동률 스플라인 시계열 차트."""
    if df.empty:
        return _empty_fig("가동률 시계열 데이터가 없습니다")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["GDATE"],
        y=df["RATE"],
        name="가동률",
        mode="lines+markers",
        line=dict(color="#00C49F", width=2.5, shape="spline", smoothing=1.3),
        marker=dict(size=6),
        fill="tozeroy",
        fillcolor="rgba(0,196,159,0.12)",
        hovertemplate="%{x|%H:%M}<br>가동률: %{y:.1f}%<extra></extra>",
    ))
    fig.add_hline(y=UTIL_WARNING, line_dash="dot", line_color="#FFA500",
                  annotation_text=f"경고 {UTIL_WARNING}%",
                  annotation_position="bottom right")
    fig.add_hline(y=UTIL_DANGER, line_dash="dot", line_color="#FF4B4B",
                  annotation_text=f"위험 {UTIL_DANGER}%",
                  annotation_position="bottom right")

    fig.update_layout(
        **_LAYOUT_BASE,
        title="📊 오늘 공장 가동률 추이",
        margin=_MARGIN_DEFAULT,
        xaxis=dict(title="시간", showgrid=False, tickformat="%H:%M"),
        yaxis=dict(title="가동률 (%)", range=[0, 105],
                   showgrid=True, gridcolor="#333344"),
        height=300,
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# 10. ECG 심전도 스타일 스크롤링 실시간 차트
# ═══════════════════════════════════════════════════════════════

def make_scrolling_ecg_chart(
    df: pd.DataFrame,
    window_minutes: int = 60,
    y_col: str = "RATE",
    title: str = "⚡ 실시간 가동률 (ECG)",
    line_color: str = "#00FF88",
) -> go.Figure:
    """
    심전도(ECG) 스타일 스크롤링 실시간 차트.

    - X축 범위를 현재 시각 기준 최근 window_minutes 분으로 고정합니다.
    - 데이터가 갱신될 때마다 X축 range가 오른쪽으로 이동하여
      그래프가 왼쪽으로 흘러가는 스크롤 효과가 만들어집니다.
    - shape='spline' 으로 부드러운 곡선을 표현합니다.
    - Plotly transition 으로 갱신 시 부드러운 애니메이션을 적용합니다.

    Parameters
    ----------
    df             : GDATE(datetime), [y_col](float) 컬럼을 가진 DataFrame
    window_minutes : 화면에 표시할 시간 창 (분 단위, 기본 60분)
    y_col          : Y축으로 사용할 컬럼명
    title          : 차트 제목
    line_color     : 라인 색상
    """
    now    = datetime.now()
    x_min  = now - timedelta(minutes=window_minutes)
    x_max  = now + timedelta(minutes=2)          # 오른쪽 여백 2분

    if df.empty:
        # 빈 데이터일 때도 시간 창 유지
        fig = go.Figure()
        fig.add_annotation(
            text="실시간 데이터 수집 중…",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=15, color="#00FF88"),
        )
        fig.update_layout(
            **_LAYOUT_BASE,
            title=title,
            margin=_MARGIN_DEFAULT,
            xaxis=dict(range=[x_min, x_max], tickformat="%H:%M",
                       showgrid=True, gridcolor="#1A2A1A"),
            yaxis=dict(range=[0, 105], showgrid=True, gridcolor="#1A2A1A"),
            height=280,
        )
        return fig

    # ── 메인 라인 (스플라인 ECG) ──────────────────────────────
    fig = go.Figure()

    # 배경 그리드 — ECG 특유의 녹색 세로 구분선
    for m in range(0, window_minutes + 1, 10):
        tick_time = x_min + timedelta(minutes=m)
        fig.add_vline(
            x=tick_time.timestamp() * 1000,   # Plotly는 ms 단위
            line_width=0.5,
            line_color="rgba(0,255,136,0.12)",
        )

    # 경고·위험 수평선
    fig.add_hrect(y0=0, y1=UTIL_DANGER,
                  fillcolor="rgba(255,75,75,0.06)", line_width=0)
    fig.add_hrect(y0=UTIL_DANGER, y1=UTIL_WARNING,
                  fillcolor="rgba(255,165,0,0.05)", line_width=0)
    fig.add_hline(y=UTIL_WARNING, line_dash="dot", line_color="#FFA500",
                  line_width=1)
    fig.add_hline(y=UTIL_DANGER, line_dash="dot", line_color="#FF4B4B",
                  line_width=1)

    # 데이터 라인
    fig.add_trace(go.Scatter(
        x=df["GDATE"],
        y=df[y_col],
        mode="lines",
        name=y_col,
        line=dict(
            color=line_color,
            width=2,
            shape="spline",
            smoothing=1.2,
        ),
        fill="tozeroy",
        fillcolor=f"rgba(0,255,136,0.07)",
        hovertemplate="%{x|%H:%M:%S}<br>%{y:.1f}%<extra></extra>",
    ))

    # 최신값 강조 마커
    if len(df) > 0:
        latest = df.iloc[-1]
        fig.add_trace(go.Scatter(
            x=[latest["GDATE"]],
            y=[latest[y_col]],
            mode="markers",
            name="현재값",
            marker=dict(color=line_color, size=10, symbol="circle",
                        line=dict(color="#ffffff", width=1.5)),
            hovertemplate=f"현재: {latest[y_col]:.1f}%<extra></extra>",
            showlegend=False,
        ))

    fig.update_layout(
        **_LAYOUT_BASE,
        title=title,
        margin=_MARGIN_DEFAULT,
        # ─ 스크롤 효과의 핵심: X축 range를 현재 시각 기준으로 고정 ─
        xaxis=dict(
            range=[x_min, x_max],
            tickformat="%H:%M",
            showgrid=True,
            gridcolor="#1A2A1A",
            dtick=600_000,          # 10분(ms) 간격 눈금
            title="시간",
        ),
        yaxis=dict(
            range=[0, 105],
            showgrid=True,
            gridcolor="#1A2A1A",
            title="가동률 (%)",
        ),
        height=280,
        # ─ 갱신 시 부드러운 슬라이딩 애니메이션 ─
        transition=dict(
            duration=400,
            easing="cubic-in-out",
            ordering="traces first",
        ),
    )
    # _LAYOUT_BASE의 plot_bgcolor를 ECG 전용 배경으로 덮어쓰기
    # (같은 update_layout 호출에 넣으면 중복 키 오류 발생)
    fig.update_layout(plot_bgcolor="#050F05")
    return fig


# ═══════════════════════════════════════════════════════════════
# 11. 작업지시 현황 테이블
# ═══════════════════════════════════════════════════════════════

def render_work_order_table(df: pd.DataFrame) -> None:
    """작업지시 현황 Streamlit 테이블 렌더링."""
    if df.empty:
        st.info("오늘 등록된 작업지시가 없습니다.")
        return

    display_cols = [
        "작업장명", "품번", "품명", "지시수량",
        "생산확인수량", "달성률(%)", "상태표시", "긴급여부",
    ]
    # 컬럼이 없을 경우 fallback
    display_cols = [c for c in display_cols if c in df.columns]
    show_df      = df[display_cols].copy()

    def _style_achieve(val):
        if isinstance(val, (int, float)):
            return f"color: {achieve_rate_color(val)}; font-weight: bold"
        return ""

    styled = (
        show_df.style
        .applymap(_style_achieve, subset=["달성률(%)"])
        .format({
            "지시수량":     "{:,.0f}",
            "생산확인수량": "{:,.0f}",
            "달성률(%)":    "{:.1f}%",
        })
    )
    st.dataframe(styled, use_container_width=True, height=300)


# ─── 내부 유틸 ────────────────────────────────────────────────

def _empty_fig(message: str) -> go.Figure:
    """데이터 없을 때 안내 메시지 Figure 반환."""
    fig = go.Figure()
    fig.add_annotation(
        text=message, xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=16, color="#888"),
    )
    fig.update_layout(**_LAYOUT_BASE, margin=_MARGIN_DEFAULT, height=300)
    return fig
