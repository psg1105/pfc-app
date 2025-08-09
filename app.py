import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# =========================================
# 페이지 & 전역 스타일
# =========================================
st.set_page_config(page_title="PFC App v0", layout="wide")
st.title("📊 Personal Finance Checkup (v0)")

# matplotlib 폰트(무난한 sans-serif + 한글 후보)
plt.rcParams["font.family"] = ["AppleGothic", "Malgun Gothic", "NanumGothic", "DejaVu Sans", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False  # 한글 폰트 사용 시 마이너스 깨짐 방지

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
# 스타일 상태(그래프 크기/폰트) 기본값
# =========================================
def ensure_style_state():
    st.session_state.setdefault("fig_size", 4.5)   # 그래프 크기(인치) - 작게 기본
    st.session_state.setdefault("title_fs", 14)    # 제목 폰트 크기
    st.session_state.setdefault("label_fs", 10)    # 라벨 폰트 크기
    st.session_state.setdefault("pct_fs", 11)      # 퍼센트 폰트 크기

ensure_style_state()

# =========================================
# 사이드바: 공통 스타일 컨트롤
# =========================================
with st.sidebar:
    st.markdown("### ⚙️ 그래프 스타일")
    st.session_state["fig_size"] = st.slider("그래프 크기(인치)", 3.0, 8.0, st.session_state["fig_size"], 0.5)
    st.session_state["title_fs"] = st.slider("제목 글씨 크기", 10, 24, st.session_state["title_fs"], 1)
    st.session_state["label_fs"] = st.slider("라벨 글씨 크기", 8, 20, st.session_state["label_fs"], 1)
    st.session_state["pct_fs"] = st.slider("퍼센트 글씨 크기", 8, 20, st.session_state["pct_fs"], 1)

# =========================================
# 유틸
# =========================================
def draw_pie(df: pd.DataFrame, title: str, base_colors: dict, key_tag: str):
    """
    df: 반드시 {Category, Amount}
    base_colors: 카테고리별 기본색 dict
    key_tag: "summary" / "assets" / "liab" 등 고유 키(사이드바 color_picker용)
    """
    if df is None or df.empty:
        st.info(f"'{title}'에 표시할 데이터가 없습니다.")
        return

    df = df.copy()
    if "Category" not in df.columns or "Amount" not in df.columns:
        st.error(f"'{title}' 데이터에 'Category'와 'Amount' 컬럼이 필요합니다.")
        return

    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    df = df.groupby("Category", as_index=False)["Amount"].sum()
    df = df[df["Amount"] > 0]

    if df.empty:
        st.info(f"'{title}'에 표시할 데이터가 없습니다.")
        return

    # 사이드바에서 카테고리별 색상 변경
    with st.sidebar.expander(f"🎨 색상 변경: {title}"):
        color_map = {}
        for cat in df["Category"]:
            default = base_colors.get(cat, "#9AA0A6")
            color_map[cat] = st.color_picker(cat, default, key=f"{key_tag}_color_{cat}")

    colors = [color_map[c] for c in df["Category"]]

    fig, ax = plt.subplots(figsize=(st.session_state["fig_size"], st.session_state["fig_size"]))
    wedges, texts, autotexts = ax.pie(
        df["Amount"],
        labels=df["Category"],
        autopct="%1.1f%%",
        startangle=90,
        colors=colors,
        textprops={"fontsize": st.session_state["label_fs"]},
    )
    # 퍼센트 텍스트 스타일
    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontsize(st.session_state["pct_fs"])
        autotext.set_weight("bold")

    ax.axis("equal")
    plt.title(title, fontsize=st.session_state["title_fs"], fontweight="bold")
    st.pyplot(fig)

def ensure_row(df: pd.DataFrame, category_name: str):
    """Summary에 필수 카테고리 행이 없으면 추가"""
    if not (df["Category"] == category_name).any():
        df.loc[len(df)] = [category_name, 0]

# =========================================
# 파일 업로더
# =========================================
uploaded_file = st.file_uploader(
    "📂 XLSX 업로드 (시트: Summary, ExpenseDetails, Assets, Liabilities)",
    type=["xlsx"]
)

if uploaded_file:
    try:
        xls = pd.ExcelFile(uploaded_file, engine="openpyxl")

        # -------------------------
        # 0) ExpenseDetails 합계 산출
        # -------------------------
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

        # -------------------------
        # 1) Summary 로드 + 자동 집계 반영
        # -------------------------
        df_sum = None
        if "Summary" in xls.sheet_names:
            df_sum = pd.read_excel(xls, sheet_name="Summary")
            if {"Category", "Amount"}.issubset(df_sum.columns):
                df_sum["Amount"] = pd.to_numeric(df_sum["Amount"], errors="coerce").fillna(0)
                # 필수 카테고리 행 보장
                for cat in ["Income", "Expense", "Remaining Balance", "Etc"]:
                    ensure_row(df_sum, cat)

                # Expense 자동 반영
                df_sum.loc[df_sum["Category"] == "Expense", "Amount"] = total_exp

                # Remaining = Income - Expense
                income_val = float(df_sum.loc[df_sum["Category"] == "Income", "Amount"].sum())
                expense_val = float(df_sum.loc[df_sum["Category"] == "Expense", "Amount"].sum())
                df_sum.loc[df_sum["Category"] == "Remaining Balance", "Amount"] = max(income_val - expense_val, 0)

                # 파이 차트 (Summary)
                draw_pie(df_sum, "① Income / Expense / Remaining / Etc (비율)", DEFAULT_COLORS_SUMMARY, key_tag="summary")
            else:
                st.error("Summary 시트는 'Category, Amount' 컬럼이 필요합니다.")
        else:
            st.warning("시트 'Summary' 가 없습니다.")

        # -------------------------
        # 2) Assets
        # -------------------------
        df_assets = None
        if "Assets" in xls.sheet_names:
            df_assets = pd.read_excel(xls, sheet_name="Assets")
            if {"Category", "Amount"}.issubset(df_assets.columns):
                draw_pie(df_assets, "② Assets 분포 (비율)", DEFAULT_COLORS_ASSETS, key_tag="assets")
            else:
                st.error("Assets 시트는 'Category, Amount' 컬럼이 필요합니다.")
        else:
            st.warning("시트 'Assets' 가 없습니다.")

        # -------------------------
        # 3) Liabilities
        # -------------------------
        df_liab = None
        if "Liabilities" in xls.sheet_names:
            df_liab = pd.read_excel(xls, sheet_name="Liabilities")
            if {"Category", "Amount"}.issubset(df_liab.columns):
                draw_pie(df_liab, "③ Liabilities 분포 (비율)", DEFAULT_COLORS_LIAB, key_tag="liab")
            else:
                st.error("Liabilities 시트는 'Category, Amount' 컬럼이 필요합니다.")
        else:
            st.warning("시트 'Liabilities' 가 없습니다.")

        # -------------------------
        # (선택) 원본 데이터 미리보기
        # -------------------------
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
