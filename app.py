import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import io

# =========================
# 페이지 & 전역 스타일
# =========================
st.set_page_config(page_title="PFC App v0", layout="wide")
st.title("📊 Personal Finance Checkup (v0)")

# 한글/영문 폰트 후보
plt.rcParams["font.family"] = ["AppleGothic", "Malgun Gothic", "NanumGothic", "DejaVu Sans", "Arial", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

# =========================
# 기본 색상 팔레트
# =========================
DEFAULT_COLORS_SUMMARY = {
    "Income": "#4E79A7",
    "Expense": "#E15759",
    "Remaining Balance": "#59A14F",
    "Etc": "#9AA0A6",
}
DEFAULT_COLORS_ASSETS = {
    "Stock": "#4E79A7", "Mutual Fund": "#59A14F", "Real Estate": "#F28E2B", "Savings": "#76B7B2",
    "Bond": "#EDC948", "Insurance": "#B07AA1", "Annuity": "#9C755F", "401K": "#E15759",
    "403B": "#FF9DA7", "Etc": "#9AA0A6",
}
DEFAULT_COLORS_LIAB = {
    "CC Debt": "#E15759", "Car Loan": "#F28E2B", "Personal Loan": "#EDC948", "Mortgage": "#4E79A7", "Etc": "#9AA0A6",
}

# =========================
# 세션 상태 초기화
# =========================
def init_state():
    if "df_summary" not in st.session_state:
        st.session_state.df_summary = pd.DataFrame({
            "Category": ["Income", "Expense", "Remaining Balance", "Etc"],
            "Amount":   [0,        0,         0,                    0]
        })
    if "df_expense" not in st.session_state:
        st.session_state.df_expense = pd.DataFrame(columns=["Category", "Description", "Amount"])
    if "df_income" not in st.session_state:
        st.session_state.df_income = pd.DataFrame(columns=["Category", "Description", "Amount"])
    if "use_income_details" not in st.session_state:
        st.session_state.use_income_details = True   # 기본값: Income 상세 합계 사용
    if "df_assets" not in st.session_state:
        st.session_state.df_assets = pd.DataFrame(columns=["Category", "Amount"])
    if "df_liab" not in st.session_state:
        st.session_state.df_liab = pd.DataFrame(columns=["Category", "Amount"])

init_state()

# =========================
# 스타일 상태 기본값
# =========================
def ensure_style_state():
    st.session_state.setdefault("fig_size", 4.0)
    st.session_state.setdefault("title_fs", 14)
    st.session_state.setdefault("pct_min_fs", 7)
    st.session_state.setdefault("pct_max_fs", 16)
    st.session_state.setdefault("list_top_n", 12)
    st.session_state.setdefault("pct_distance", 0.68)

ensure_style_state()

# =========================
# 사이드바 컨트롤
# =========================
with st.sidebar:
    st.markdown("### ⚙️ 그래프 스타일")
    st.session_state["fig_size"] = st.slider("그래프 크기(인치)", 3.0, 8.0, st.session_state["fig_size"], 0.5, key="sl_fig")
    st.session_state["title_fs"] = st.slider("제목 글씨 크기", 10, 28, st.session_state["title_fs"], 1, key="sl_title")
    c1, c2 = st.columns(2)
    with c1:
        st.session_state["pct_min_fs"] = st.slider("퍼센트 최소 글씨", 6, 14, st.session_state["pct_min_fs"], 1, key="sl_pct_min")
    with c2:
        st.session_state["pct_max_fs"] = st.slider("퍼센트 최대 글씨", 12, 28, st.session_state["pct_max_fs"], 1, key="sl_pct_max")
    st.session_state["pct_distance"] = st.slider("퍼센트 위치(중심↔테두리)", 0.55, 0.85, st.session_state["pct_distance"], 0.01, key="sl_pct_dist")
    st.session_state["list_top_n"] = st.slider("우측 리스트 항목 수", 5, 20, st.session_state["list_top_n"], 1, key="sl_list_n")

# =========================
# 유틸
# =========================
def ensure_row(df: pd.DataFrame, category_name: str):
    if not (df["Category"] == category_name).any():
        df.loc[len(df)] = [category_name, 0]

def compute_summary(df_summary: pd.DataFrame,
                    df_expense: pd.DataFrame,
                    df_income: pd.DataFrame,
                    use_income_details: bool) -> pd.DataFrame:
    """
    - Expense = ExpenseDetails 합계
    - Income = (use_income_details=True)면 IncomeDetails 합계, 아니면 df_summary의 Income 값
    - Remaining = Income - Expense
    """
    df = df_summary.copy()
    for cat in ["Income", "Expense", "Remaining Balance", "Etc"]:
        ensure_row(df, cat)

    # Expense 합계
    exp_total = 0.0
    if not df_expense.empty and {"Amount"}.issubset(df_expense.columns):
        exp_total = pd.to_numeric(df_expense["Amount"], errors="coerce").fillna(0).sum()

    # Income 합계 (상세 사용 여부)
    if use_income_details and (not df_income.empty):
        inc_total = pd.to_numeric(df_income["Amount"], errors="coerce").fillna(0).sum()
        df.loc[df["Category"] == "Income", "Amount"] = inc_total
    else:
        df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)

    # Expense 적용
    df.loc[df["Category"] == "Expense", "Amount"] = exp_total

    # Remaining 계산
    income_val = float(df.loc[df["Category"] == "Income", "Amount"].sum())
    expense_val = float(df.loc[df["Category"] == "Expense", "Amount"].sum())
    df.loc[df["Category"] == "Remaining Balance", "Amount"] = max(income_val - expense_val, 0)
    return df

def draw_pie_with_list(df: pd.DataFrame, title: str, base_colors: dict, key_tag: str):
    """왼쪽: 파이(%만 내부). 오른쪽: 퍼센트 정렬 리스트"""
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

    # 색상 변경
    with st.sidebar.expander(f"🎨 색상 변경: {title}", expanded=False):
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

    col_chart, col_list = st.columns([5, 2], gap="large")

    # 파이
    with col_chart:
        fig, ax = plt.subplots(figsize=(st.session_state["fig_size"], st.session_state["fig_size"]))
        wedges, _, autotexts = ax.pie(
            values,
            labels=None,
            autopct=lambda p: f"{p:.1f}%",
            startangle=90,
            colors=colors,
            pctdistance=st.session_state["pct_distance"],
            textprops={"fontsize": st.session_state["pct_min_fs"], "color": "white", "weight": "bold"},
        )
        # % 글씨 크기 보간
        min_fs = st.session_state["pct_min_fs"]
        max_fs = st.session_state["pct_max_fs"]
        for i, aut in enumerate(autotexts):
            frac = float(fracs[i])
            scale = np.sqrt(frac)
            size = min_fs + (max_fs - min_fs) * scale
            aut.set_fontsize(size)
            aut.set_ha("center"); aut.set_va("center"); aut.set_clip_on(True)

        # 경계선
        for w in wedges:
            w.set_linewidth(1)
            w.set_edgecolor("white")

        ax.axis("equal")
        plt.title(title, fontsize=st.session_state["title_fs"], fontweight="bold")
        st.pyplot(fig, clear_figure=True)

    # 리스트
    with col_list:
        st.markdown("#### 비율 순 정렬")
        order = np.argsort(-percents)
        top_n = int(st.session_state["list_top_n"])
        items = [(labels[i], percents[i], colors[i]) for i in order[:top_n]]
        md_lines = []
        for name, pct, col in items:
            chip = f"<span style='display:inline-block;width:10px;height:10px;background:{col};border-radius:2px;margin-right:6px;'></span>"
            md_lines.append(f"{chip} **{name}** — {pct:.1f}%")
        st.markdown("<br>".join(md_lines), unsafe_allow_html=True)

# =========================
# 파일 불러오기 / 저장
# =========================
with st.expander("📂 파일 불러오기 / 저장", expanded=False):
    uploaded = st.file_uploader("XLSX 업로드 (시트: Summary, ExpenseDetails, IncomeDetails, Assets, Liabilities)",
                                type=["xlsx"], key="upl_xlsx")
    col_u1, col_u2, col_u3 = st.columns([1,1,2])

    if uploaded:
        try:
            xls = pd.ExcelFile(uploaded, engine="openpyxl")
            if "Summary" in xls.sheet_names:
                st.session_state.df_summary = pd.read_excel(xls, sheet_name="Summary")
            if "ExpenseDetails" in xls.sheet_names:
                st.session_state.df_expense = pd.read_excel(xls, sheet_name="ExpenseDetails")
            if "IncomeDetails" in xls.sheet_names:
                st.session_state.df_income = pd.read_excel(xls, sheet_name="IncomeDetails")
            if "Assets" in xls.sheet_names:
                st.session_state.df_assets = pd.read_excel(xls, sheet_name="Assets")
            if "Liabilities" in xls.sheet_names:
                st.session_state.df_liab = pd.read_excel(xls, sheet_name="Liabilities")
            st.success("불러오기 완료")
        except Exception as e:
            st.error(f"불러오기 오류: {e}")

    if col_u1.button("세션 초기화", key="btn_reset"):
        for k in ["df_summary","df_expense","df_income","df_assets","df_liab","use_income_details"]:
            if k in st.session_state: del st.session_state[k]
        init_state()
        st.rerun()

    def make_excel_bytes() -> bytes:
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            calc = compute_summary(st.session_state.df_summary,
                                   st.session_state.df_expense,
                                   st.session_state.df_income,
                                   st.session_state.use_income_details)
            calc.to_excel(writer, index=False, sheet_name="Summary")
            st.session_state.df_income.to_excel(writer, index=False, sheet_name="IncomeDetails")
            st.session_state.df_expense.to_excel(writer, index=False, sheet_name="ExpenseDetails")
            st.session_state.df_assets.to_excel(writer, index=False, sheet_name="Assets")
            st.session_state.df_liab.to_excel(writer, index=False, sheet_name="Liabilities")
        out.seek(0)
        return out.read()

    col_u2.download_button("현재 상태 엑셀 다운로드",
                           data=make_excel_bytes(),
                           file_name="PFC_Current.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="dl_current")

# =========================
# 입력 & 관리 (탭)
# =========================
st.markdown("---")
st.header("✍️ 입력 & 관리")

tab_inc, tab_exp, tab_sum, tab_ast, tab_liab = st.tabs(
    ["Income 입력", "Expense 입력", "Summary(보기/설정)", "Assets", "Liabilities"]
)

# --- Income 입력: 폼 사용 (Enter 제출 + 자동 초기화) ---
with tab_inc:
    st.subheader("수입 항목 추가")
    with st.form("form_add_income", clear_on_submit=True):
        s1, s2, s3 = st.columns([1.2, 2, 1])
        with s1:
            in_cat = st.text_input("Category", value="")
        with s2:
            in_desc = st.text_input("Description", value="")
        with s3:
            in_amt = st.number_input("Amount", min_value=0.0, step=10.0, value=0.0)
        submitted_inc = st.form_submit_button("추가")
    if submitted_inc:
        # 아무 것도 없더라도 오류 없이 통과 (빈 입력은 추가 안 함)
        if (in_cat or in_desc) or (in_amt > 0):
            st.session_state.df_income = pd.concat(
                [st.session_state.df_income,
                 pd.DataFrame([{"Category": in_cat, "Description": in_desc, "Amount": in_amt}])],
                ignore_index=True
            )
            st.success("추가 완료!")

    st.markdown("##### 현재 수입 내역")
    if st.session_state.df_income.empty:
        st.info("수입 항목이 없습니다.")
    else:
        df_show = st.session_state.df_income.copy()
        df_show.index = range(1, len(df_show) + 1)
        del_idx = st.multiselect("삭제할 행 선택 (번호)", options=list(df_show.index), key="ms_del_inc")
        st.dataframe(df_show, use_container_width=True, key="df_income_table")
        if st.button("선택 행 삭제", key="btn_del_inc"):
            if del_idx:
                real_idx = [i-1 for i in del_idx]
                st.session_state.df_income = st.session_state.df_income.drop(real_idx).reset_index(drop=True)
                st.success("삭제 완료!")
            else:
                st.info("선택한 행이 없습니다.")

# --- Expense 입력: 폼 사용 (Enter 제출 + 자동 초기화) ---
with tab_exp:
    st.subheader("지출 항목 추가")
    with st.form("form_add_expense", clear_on_submit=True):
        c1, c2, c3 = st.columns([1.2, 2, 1])
        with c1:
            exp_cat = st.text_input("Category", value="")
        with c2:
            exp_desc = st.text_input("Description", value="")
        with c3:
            exp_amt = st.number_input("Amount", min_value=0.0, step=10.0, value=0.0)
        submitted_exp = st.form_submit_button("추가")
    if submitted_exp:
        if (exp_cat or exp_desc) or (exp_amt > 0):
            st.session_state.df_expense = pd.concat(
                [st.session_state.df_expense,
                 pd.DataFrame([{"Category": exp_cat, "Description": exp_desc, "Amount": exp_amt}])],
                ignore_index=True
            )
            st.success("추가 완료!")

    st.markdown("##### 현재 지출 내역")
    if st.session_state.df_expense.empty:
        st.info("지출 항목이 없습니다.")
    else:
        df_show = st.session_state.df_expense.copy()
        df_show.index = range(1, len(df_show) + 1)
        del_idx = st.multiselect("삭제할 행 선택 (번호)", options=list(df_show.index), key="ms_del_exp")
        st.dataframe(df_show, use_container_width=True, key="df_exp_table")
        if st.button("선택 행 삭제", key="btn_del_exp"):
            if del_idx:
                real_idx = [i-1 for i in del_idx]
                st.session_state.df_expense = st.session_state.df_expense.drop(real_idx).reset_index(drop=True)
                st.success("삭제 완료!")
            else:
                st.info("선택한 행이 없습니다.")

# --- Summary 보기/설정 ---
with tab_sum:
    st.subheader("Summary (자동 집계)")
    st.checkbox("Income을 'Income Details' 합계로 사용", value=st.session_state.use_income_details,
                key="chk_use_inc_details")
    st.session_state.use_income_details = st.session_state.chk_use_inc_details

    if not st.session_state.use_income_details:
        cur_inc = float(st.session_state.df_summary.loc[
            st.session_state.df_summary["Category"] == "Income", "Amount"
        ].sum())
        new_inc = st.number_input("수동 Income 금액", min_value=0.0, step=100.0, value=cur_inc, key="ni_manual_income")
        st.session_state.df_summary.loc[st.session_state.df_summary["Category"] == "Income", "Amount"] = new_inc
        st.caption("※ 'Income Details'를 사용하지 않을 때만 적용됩니다.")

    cur_etc = float(st.session_state.df_summary.loc[
        st.session_state.df_summary["Category"] == "Etc", "Amount"
    ].sum())
    new_etc = st.number_input("Etc 금액", min_value=0.0, step=50.0, value=cur_etc, key="ni_manual_etc")
    st.session_state.df_summary.loc[st.session_state.df_summary["Category"] == "Etc", "Amount"] = new_etc

    calc = compute_summary(st.session_state.df_summary,
                           st.session_state.df_expense,
                           st.session_state.df_income,
                           st.session_state.use_income_details)

    income_val = float(calc.loc[calc["Category"]=="Income","Amount"].sum())
    expense_val = float(calc.loc[calc["Category"]=="Expense","Amount"].sum())
    remain_val = float(calc.loc[calc["Category"]=="Remaining Balance","Amount"].sum())
    etc_val = float(calc.loc[calc["Category"]=="Etc","Amount"].sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Income", f"{income_val:,.2f}")
    m2.metric("Expense", f"{expense_val:,.2f}")
    m3.metric("Remaining", f"{remain_val:,.2f}")
    m4.metric("Etc", f"{etc_val:,.2f}")

# --- Assets ---
with tab_ast:
    st.subheader("Assets 편집")
    st.session_state.df_assets = st.data_editor(
        st.session_state.df_assets, num_rows="dynamic", use_container_width=True, key="ed_assets"
    )

# --- Liabilities ---
with tab_liab:
    st.subheader("Liabilities 편집")
    st.session_state.df_liab = st.data_editor(
        st.session_state.df_liab, num_rows="dynamic", use_container_width=True, key="ed_liab"
    )

# =========================
# 시각화 (실시간)
# =========================
st.markdown("---")
st.header("📈 시각화")

df_sum_calc = compute_summary(st.session_state.df_summary,
                              st.session_state.df_expense,
                              st.session_state.df_income,
                              st.session_state.use_income_details)

draw_pie_with_list(df_sum_calc, "INCOME / EXPENSE", DEFAULT_COLORS_SUMMARY, key_tag="summary")
draw_pie_with_list(st.session_state.df_assets, "ASSET", DEFAULT_COLORS_ASSETS, key_tag="assets")
draw_pie_with_list(st.session_state.df_liab, "LIABILITY", DEFAULT_COLORS_LIAB, key_tag="liab")
