import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# =========================================
# 페이지 & 전역 스타일
# =========================================
st.set_page_config(page_title="PFC App v0", layout="wide")
st.title("📊 Personal Finance Checkup (v0)")

# 폰트 설정(한글/영문 모두 무난한 후보)
plt.rcParams["font.family"] = ["AppleGothic", "Malgun Gothic", "NanumGothic", "DejaVu Sans", "Arial", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False  # 마이너스 깨짐 방지

# =========================================
# 기본 고정 색상 팔레트 (추천값)
# =========================================
DEFAULT_COLORS_SUMMARY = {
    "Income": "#4E79A7",
    "Expense": "#E15759",
    "Remaining Balance": "#59A14F",
    "Etc": "#9AA0A6",
}

DEFAULT_COLORS_ASSETS = {
    "Stock": "#4E79A7",
    "Mutual Fund": "#59A14F",
    "Real Estate": "#F28E2B",
    "Savings": "#76B7B2",
    "Bond": "#EDC948",
    "Insurance": "#B07AA1",
    "Annuity": "#9C755F",
    "401K": "#E15759",
    "403B": "#FF9DA7",
    "Etc": "#9AA0A6",
}

DEFAULT_COLORS_LIAB = {
    "CC Debt": "#E15759",
    "Car Loan": "#F28E2B",
    "Personal Loan": "#EDC948",
    "Mortgage": "#4E79A7",
    "Etc": "#9AA0A6",
}

# =========================================
# 스타일 상태(그래프/라벨) 기본값
# =========================================
def ensure_style_state():
    st.session_state.setdefault("fig_size", 4.5)    # 그래프 크기(인치)
    st.session_state.setdefault("title_fs", 14)     # 제목 폰트 크기
    st.session_state.setdefault("label_min_fs", 9)  # 라벨 최소 글씨 크기
    st.session_state.setdefault("label_max_fs", 18) # 라벨 최대 글씨 크기
    st.session_state.setdefault("label_thresh_pct", 3.0)  # 이 퍼센트 미만은 라벨 숨김
    st.session_state.setdefault("list_top_n", 12)   # 우측 리스트 표시 개수

ensure_style_state()

# =========================================
# 사이드바 컨트롤
# =========================================
with st.sidebar:
    st.markdown("### ⚙️ 그래프 스타일")
    st.session_state["fig_size"] = st.slider("그래프 크기(인치)", 3.0, 8.0, st.session_state["fig_size"], 0.5)
    st.session_state["title_fs"] = st.slider("제목 글씨 크기", 10, 28, st.session_state["title_fs"], 1)
    st.session_state["label_min_fs"] = st.slider("라벨 최소 글씨 크기", 6, 16, st.session_state["label_min_fs"], 1)
    st.session_state["label_max_fs"] = st.slider("라벨 최대 글씨 크기", 12, 32, st.session_state["label_max_fs"], 1)
    st.session_state["label_thresh_pct"] = st.slider("라벨 표시 임계값(%)", 0.0, 10.0, st.session_state["label_thresh_pct"], 0.5)
    st.session_state["list_top_n"] = st.slider("우측 리스트 항목 수", 5, 20, st.session_state["list_top_n"], 1)

# =========================================
# 유틸
# =========================================
def ensure_row(df: pd.DataFrame, category_name: str):
    """Summary에 필수 카테고리 행이 없으면 추가"""
    if not (df["Category"] == category_name).any():
        df.loc[len(df)] = [category_name, 0]

def draw_pie_with_list(df: pd.DataFrame, title: str, base_colors: dict, key_tag: str):
    """
    왼쪽: 파이 차트(내부 라벨, 작은 조각 숨김)
    오른쪽: 퍼센트 내림차순 리스트
    df: {Category, Amount}
    """
    if df is None or df.empty:
        st.info(f"'{title}'에 표시할 데이터가 없습니다.")
        return

    if "Category" not in df.columns or "Amount" not in df.columns:
        st.error(f"'{title}' 데이터에 'Category'와 'Amount' 컬럼이 필요합니다.")
        return

    df = df.copy()
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    df = df.groupby("Category", as_index=False)["Amount"].sum()
    df = df[df["Amount"] > 0]
    if df.empty:
        st.info(f"'{title}'에 표시할 데이터가 없습니다.")
        return

    # 사이드바 색상 변경
    with st.sidebar.expander(f"🎨 색상 변경: {title}"):
        color_map = {}
        for cat in df["Category"]:
            default = base_colors.get(cat, "#9AA0A6")
            color_map[cat] = st.color_picker(cat, default, key=f"{key_tag}_color_{cat}")

    colors = [color_map[c] for c in df["Category"]]
    values = df["Amount"].to_numpy()
    labels = df["Category"].tolist()
    total = float(values.sum())
    fracs = values / total
    percents = fracs * 100

    # 화면 배치: 왼쪽 차트 / 오른쪽 리스트
    col_chart, col_list = st.columns([5, 2], gap="large")

    # ---------- 파이 차트 ----------
    with col_chart:
        fig, ax = plt.subplots(figsize=(st.session_state["fig_size"], st.session_state["fig_size"]))

        # 라벨은 내부에서 따로 처리할 거라 외부 labels=None
        wedges, _, autotexts = ax.pie(
            values,
            labels=None,
            autopct=lambda p: f"{p:.1f}%",
            startangle=90,
            colors=colors,
            textprops={"fontsize": st.session_state["label_min_fs"]},
        )

        # 내부 라벨: 작은 조각은 숨기고, 나머지는 "카테고리\nxx.x%" 표시
        min_fs = st.session_state["label_min_fs"]
        max_fs = st.session_state["label_max_fs"]
        thresh = st.session_state["label_thresh_pct"]

        for i, aut in enumerate(autotexts):
            pct_val = percents[i]
            if pct_val < thresh:
                aut.set_text("")  # 라벨 숨김
                continue

            # 텍스트 구성 및 스타일
            aut.set_text(f"{labels[i]}\n{pct_val:.1f}%")
            # 조각 비율로 글씨 크기 보간
            frac = float(fracs[i])  # 0~1
            size = min_fs + (max_fs - min_fs) * frac
            aut.set_fontsize(size)
            aut.set_weight("bold")
            aut.set_color("white")
            aut.set_clip_on(True)  # 축 밖 그리지 않기
            # 중앙 정렬 보장
            aut.set_ha("center")
            aut.set_va("center")

        ax.axis("equal")
        plt.title(title, fontsize=st.session_state["title_fs"], fontweight="bold")
        st.pyplot(fig)

    # ---------- 우측 리스트 ----------
    with col_list:
        st.markdown("#### 비율 순 정렬")
        order = np.argsort(-percents)  # 내림차순
        top_n = int(st.session_state["list_top_n"])
        items = [(labels[i], percents[i]) for i in order[:top_n]]

        # 컬러칩과 함께 표시
        md_lines = []
        for i, (name, pct) in enumerate(items, start=1):
            chip = f"<span style='display:inline-block;width:10px;height:10px;background:{color_map[name]};border-radius:2px;margin-right:6px;'></span>"
            md_lines.append(f"{chip} **{name}** — {pct:.1f}%")
        st.markdown("<br>".join(md_lines), unsafe_allow_html=True)

# =========================================
# 업로더
# =========================================
uploaded_file = st.file_uploader(
    "📂 XLSX 업로드 (시트: Summary, ExpenseDetails, Assets, Liabilities)",
    type=["xlsx"]
)

if uploaded_file:
    try:
        xls = pd.ExcelFile(uploaded_file, engine="openpyxl")

        # 0) ExpenseDetails 합계
        total_exp = 0.0
        df_ed = None
        if "ExpenseDetails" in xls.sheet_names:
            df_ed = pd.read_excel(xls, sheet_name="ExpenseDetails")
            if {"Category", "Description", "Amount"}.issubset(df_ed.columns):
                total_exp = pd.to_numeric(df_ed["Amount"], errors="coerce").fillna(0).sum()
            else:
                st.warning("ExpenseDetails 시트는 'Category, Description, Amount' 컬럼이 필요합니다.")
        else:
            st.warning("시트 'ExpenseDetails' 가 없습니다. (Summary의 Expense는 0으로 집계)")

        # 1) Summary + 자동 집계
        df_sum = None
        if "Summary" in xls.sheet_names:
            df_sum = pd.read_excel(xls, sheet_name="Summary")
            if {"Category", "Amount"}.issubset(df_sum.columns):
                df_sum["Amount"] = pd.to_numeric(df_sum["Amount"], errors="coerce").fillna(0)
                for cat in ["Income", "Expense", "Remaining Balance", "Etc"]:
                    ensure_row(df_sum, cat)
                # Expense 자동 반영 & Remaining 계산
                df_sum.loc[df_sum["Category"] == "Expense", "Amount"] = total_exp
                income_val = float(df_sum.loc[df_sum["Category"] == "Income", "Amount"].sum())
                expense_val = float(df_sum.loc[df_sum["Category"] == "Expense", "Amount"].sum())
                df_sum.loc[df_sum["Category"] == "Remaining Balance", "Amount"] = max(income_val - expense_val, 0)

                draw_pie_with_list(df_sum, "INCOME / EXPENSE", DEFAULT_COLORS_SUMMARY, key_tag="summary")
            else:
                st.error("Summary 시트는 'Category, Amount' 컬럼이 필요합니다.")
        else:
            st.warning("시트 'Summary' 가 없습니다.")

        # 2) Assets
        df_assets = None
        if "Assets" in xls.sheet_names:
            df_assets = pd.read_excel(xls, sheet_name="Assets")
            if {"Category", "Amount"}.issubset(df_assets.columns):
                draw_pie_with_list(df_assets, "ASSET", DEFAULT_COLORS_ASSETS, key_tag="assets")
            else:
                st.error("Assets 시트는 'Category, Amount' 컬럼이 필요합니다.")
        else:
            st.warning("시트 'Assets' 가 없습니다.")

        # 3) Liabilities
        df_liab = None
        if "Liabilities" in xls.sheet_names:
            df_liab = pd.read_excel(xls, sheet_name="Liabilities")
            if {"Category", "Amount"}.issubset(df_liab.columns):
                draw_pie_with_list(df_liab, "LIABILITY", DEFAULT_COLORS_LIAB, key_tag="liab")
            else:
                st.error("Liabilities 시트는 'Category, Amount' 컬럼이 필요합니다.")
        else:
            st.warning("시트 'Liabilities' 가 없습니다.")

        # (선택) 원본 보기
        with st.expander("원본 데이터 미리보기"):
            if df_sum is not None:
                st.write("Summary", df_sum)
            if df_ed is not None:
                st.write("ExpenseDetails", df_ed)
            if df_assets is not None:
                st.write("Assets", df_assets)
            if df_liab is not None:
                st.write("Liabilities", df_liab)

    except Exception as e:
        st.error(f"파일 처리 중 오류: {e}")
else:
    st.info("템플릿을 다운로드하여 입력 후 업로드하세요. (시트: Summary, ExpenseDetails, Assets, Liabilities)")
