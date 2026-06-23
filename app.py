"""
app.py
------
MES/POP 실시간 모니터링 대시보드 — 메인 진입점

실행 방법:
    streamlit run app.py

구조:
    app.py              ← 이 파일 (페이지 레이아웃 & 자동갱신 루프)
    database.py         ← DB 커넥션 (dotenv 기반)
    queries.py          ← SQL 쿼리 + @st.cache_data
    data_processor.py   ← DataFrame 전처리
    ui_components.py    ← Plotly 차트 & Streamlit 컴포넌트
    .env                ← 접속 정보 (git 제외)
"""

import os
import time
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from database import test_connection
import queries as Q
import data_processor as DP
import ui_components as UI

# ─── 환경변수 ─────────────────────────────────────────────────
KST = ZoneInfo("Asia/Seoul")  # 한국 시간대 (Cloud UTC 보정)
REFRESH_MS = int(os.getenv("REFRESH_INTERVAL_MS", 10_000))   # 기본 10초

# ═══════════════════════════════════════════════════════════════
# 페이지 기본 설정
# ═══════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="MES/POP 실시간 모니터링",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── 다크 테마 커스텀 CSS ──────────────────────────────────────
st.markdown("""
<style>
/* 전체 배경 */
[data-testid="stAppViewContainer"] {
    background-color: #0E0E1A;
}
[data-testid="stSidebar"] {
    background-color: #12121C;
    border-right: 1px solid #2A2A3A;
}
/* 헤더 */
[data-testid="stHeader"] {
    background-color: #0E0E1A;
}
/* Metric 카드 */
[data-testid="metric-container"] {
    background: linear-gradient(135deg, #1A1A2E 0%, #16213E 100%);
    border: 1px solid #2A2A4A;
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.4);
}
[data-testid="stMetricValue"] {
    font-size: 1.8rem !important;
    font-weight: 700;
    color: #E8E8F0 !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.85rem !important;
    color: #9090B0 !important;
}
/* 섹션 구분선 */
hr {
    border-color: #2A2A3A;
}
/* 사이드바 텍스트 */
.css-1d391kg, .css-1aumxhk {
    color: #C0C0D0;
}
/* 상태 뱃지 */
.status-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
}
/* 섹션 타이틀 */
.section-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #A0A8C8;
    margin-bottom: 4px;
    padding-bottom: 4px;
    border-bottom: 1px solid #2A2A3A;
}
/* 자동갱신 카운터 숨기기 */
iframe[title="streamlit_autorefresh.autorefresh"] {
    display: none;
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# 자동 갱신 (streamlit-autorefresh)
# ═══════════════════════════════════════════════════════════════

refresh_count = st_autorefresh(
    interval=REFRESH_MS,
    limit=None,
    key="mes_dashboard_autorefresh",
)


# ═══════════════════════════════════════════════════════════════
# 사이드바
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 🏭 MES/POP 모니터링")
    st.markdown("---")

    # 날짜 선택
    selected_date = st.date_input(
        "📅 조회 날짜",
        value=datetime.now(KST).date(),
        max_value=datetime.now(KST).date(),
    )
    # 개인서버(정답 데이터)와 동일하게 "조회 당일" 기준으로 조회
    target_ymd  = selected_date.strftime("%Y%m%d")
    target_ymd8 = selected_date.strftime("%Y%m%d")
    st.markdown("---")

    # DB 연결 상태
    st.markdown("### 🔌 DB 연결 상태")
    if test_connection():
        st.success("✅ 연결 정상")
    else:
        st.error("❌ 연결 실패 — .env 확인")

    st.markdown("---")

    # 갱신 정보
    st.markdown("### ⏱️ 자동 갱신")
    st.info(f"매 **{REFRESH_MS // 1000}초** 자동 갱신")
    st.caption(f"마지막 갱신: {datetime.now(KST).strftime('%H:%M:%S')}")
    st.caption(f"갱신 횟수: {refresh_count}")

    st.markdown("---")
    st.markdown("### 📋 임계값 기준")
    st.markdown(f"""
    | 구분 | 경고 | 위험 |
    |------|------|------|
    | 불량률 | {os.getenv('BAD_RATE_WARNING','3')}% | {os.getenv('BAD_RATE_DANGER','5')}% |
    | 가동률 | {os.getenv('UTIL_RATE_WARNING','70')}% | {os.getenv('UTIL_RATE_DANGER','50')}% |
    """)


# ═══════════════════════════════════════════════════════════════
# 메인 헤더
# ═══════════════════════════════════════════════════════════════

col_title, col_time = st.columns([4, 1])
with col_title:
    st.markdown(
        f"<h1 style='color:#C0C8E8; margin-bottom:0'>🏭 실시간 생산 모니터링</h1>"
        f"<p style='color:#6870A0; margin-top:0'>📅 {selected_date.strftime('%Y년 %m월 %d일')} 기준</p>",
        unsafe_allow_html=True,
    )
with col_time:
    st.markdown(
        f"<div style='text-align:right; color:#6870A0; padding-top:20px'>"
        f"🕐 {datetime.now(KST).strftime('%H:%M:%S')}</div>",
        unsafe_allow_html=True,
    )

st.markdown("---")


# ═══════════════════════════════════════════════════════════════
# 데이터 로드 (캐시 활용)
# ═══════════════════════════════════════════════════════════════

with st.spinner("📡 데이터 로딩 중..."):
    kpi_raw         = Q.get_today_production_kpi(target_ymd)
    achievement_raw = Q.get_today_achievement_rate(target_ymd)
    utilization_raw = Q.get_factory_utilization(target_ymd8)

    df_hourly   = DP.process_hourly_production(Q.get_hourly_production(target_ymd))
    df_line     = DP.process_line_production(Q.get_line_production(target_ymd))
    df_defect   = DP.process_defect_types(Q.get_defect_by_type(target_ymd))
    df_downtime = DP.process_downtime(Q.get_downtime_summary(target_ymd))
    df_weekly   = DP.process_weekly_trend(Q.get_weekly_production_trend())
    df_util_ts  = DP.process_utilization_ts(Q.get_utilization_timeseries(target_ymd8))
    df_orders   = DP.process_work_orders(Q.get_active_work_orders(target_ymd8))


# ═══════════════════════════════════════════════════════════════
# SECTION 1: KPI 카드 (최상단)
# ═══════════════════════════════════════════════════════════════

UI.render_kpi_header(kpi_raw, achievement_raw, utilization_raw)

st.markdown("<br>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# SECTION 2: Gauge 차트 (달성률 + 가동률)
# ═══════════════════════════════════════════════════════════════

g_col1, g_col2, g_col3 = st.columns([1, 1, 2])

with g_col1:
    st.plotly_chart(
        UI.make_achievement_gauge(achievement_raw.get("achieve_rate", 0.0)),
        use_container_width=True,
    )

with g_col2:
    st.plotly_chart(
        UI.make_utilization_gauge(utilization_raw.get("rate", 0.0)),
        use_container_width=True,
    )

with g_col3:
    # ⚡ ECG 심전도 스타일 스크롤링 차트
    # — X축 range를 현재 시각 기준으로 고정하여 새 데이터 추가 시
    #   그래프가 왼쪽으로 부드럽게 흘러가는 효과를 구현합니다.
    st.plotly_chart(
        UI.make_scrolling_ecg_chart(
            df_util_ts,
            window_minutes=60,
            y_col="RATE",
            title="⚡ 실시간 가동률 (ECG)",
            line_color="#00FF88",
        ),
        use_container_width=True,
    )

st.markdown("---")


# ═══════════════════════════════════════════════════════════════
# SECTION 3: 시간대별 생산 + 라인별 현황
# ═══════════════════════════════════════════════════════════════

c3_left, c3_right = st.columns([3, 2])

with c3_left:
    st.plotly_chart(
        UI.make_hourly_chart(df_hourly),
        use_container_width=True,
    )

with c3_right:
    st.plotly_chart(
        UI.make_line_bar_chart(df_line),
        use_container_width=True,
    )

st.markdown("---")


# ═══════════════════════════════════════════════════════════════
# SECTION 4: 불량 유형 + 비가동 현황
# ═══════════════════════════════════════════════════════════════

c4_left, c4_right = st.columns(2)

with c4_left:
    st.plotly_chart(
        UI.make_defect_pie(df_defect),
        use_container_width=True,
    )

with c4_right:
    st.plotly_chart(
        UI.make_downtime_chart(df_downtime),
        use_container_width=True,
    )

st.markdown("---")


# ═══════════════════════════════════════════════════════════════
# SECTION 5: 최근 7일 추이
# ═══════════════════════════════════════════════════════════════

st.plotly_chart(
    UI.make_weekly_trend_chart(df_weekly),
    use_container_width=True,
)

st.markdown("---")


# ═══════════════════════════════════════════════════════════════
# SECTION 6: 작업지시 현황 테이블
# ═══════════════════════════════════════════════════════════════

st.markdown("### 📋 오늘의 작업지시 현황")
UI.render_work_order_table(df_orders)


# ═══════════════════════════════════════════════════════════════
# 푸터
# ═══════════════════════════════════════════════════════════════

st.markdown("---")
st.markdown(
    "<p style='text-align:center; color:#3A3A5A; font-size:0.8rem'>"
    "MES/POP 실시간 모니터링 대시보드 · "
    f"자동 갱신 {REFRESH_MS // 1000}s · "
    f"DB: {os.getenv('DB_HOST','?')}:{os.getenv('DB_PORT','3306')} · "
    f"사업장: {os.getenv('MILL_CD','?')}"
    "</p>",
    unsafe_allow_html=True,
)
