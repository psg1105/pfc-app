import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import io

# ---------------------- 기본 설정 ----------------------
st.set_page_config(page_title="PFC App v0", layout="wide")
st.title("📊 Personal Finance Checkup (v0)")

plt.rcParams["font.family"] = ["AppleGothic","Malgun Gothic","NanumGothic","DejaVu Sans","Arial","sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

DEFAULT_COLORS_SUMMARY = {"Income":"#4E79A7","Expense":"#E15759","Remaining Balance":"#59A14F","Etc":"#9AA0A6"}
DEFAULT_COLORS_ASSETS  = {"Stock":"#4E79A7","Mutual Fund":"#59A14F","Real Estate":"#F28E2B","Savings":"#76B7B2",
                          "Bond":"#EDC948","Insurance":"#B07AA1","Annuity":"#9C755F","401K":"#E15759",
                          "403B":"#FF9DA7","Etc":"#9AA0A6"}
DEFAULT_COLORS_LIAB    = {"CC Debt":"#E15759","Car Loan":"#F28E2B","Personal Loan":"#EDC948","Mortgage":"#4E79A7","Etc":"#9AA0A6"}

# ---------------------- state ----------------------
def init_state():
    ss = st.session_state
    ss.setdefault("df_summary", pd.DataFrame({"Category":["Income","Expense","Remaining Balance","Etc"],"Amount":[0,0,0,0]}))
    ss.setdefault("df_expense", pd.DataFrame(columns=["Category","Description","Amount"]))
    ss.setdefault("df_income",  pd.DataFrame(columns=["Category","Description","Amount"]))
    ss.setdefault("df_assets",  pd.DataFrame(columns=["Category","Amount"]))
    ss.setdefault("df_liab",    pd.DataFrame(columns=["Category","Amount"]))
    ss.setdefault("use_income_details", True)
    ss.setdefault("focus_next", None)
    ss.setdefault("fig_size", 4.0)
    ss.setdefault("title_fs", 14)
    ss.setdefault("pct_min_fs", 7)
    ss.setdefault("pct_max_fs", 16)
    ss.setdefault("list_top_n", 12)
    ss.setdefault("pct_distance", 0.68)
init_state()

# ---------------------- sidebar ----------------------
with st.sidebar:
    st.markdown("### ⚙️ 그래프 스타일")
    st.session_state["fig_size"] = st.slider("그래프 크기(인치)", 3.0, 8.0, st.session_state["fig_size"], 0.5)
    st.session_state["title_fs"] = st.slider("제목 글씨 크기", 10, 28, st.session_state["title_fs"], 1)
    c1,c2 = st.columns(2)
    with c1: st.session_state["pct_min_fs"] = st.slider("퍼센트 최소 글씨", 6, 14, st.session_state["pct_min_fs"], 1)
    with c2: st.session_state["pct_max_fs"] = st.slider("퍼센트 최대 글씨", 12, 28, st.session_state["pct_max_fs"], 1)
    st.session_state["pct_distance"] = st.slider("퍼센트 위치(중심↔테두리)", 0.55, 0.85, st.session_state["pct_distance"], 0.01)
    st.session_state["list_top_n"] = st.slider("우측 리스트 항목 수", 5, 20, st.session_state["list_top_n"], 1)

# ---------------------- utils ----------------------
def ensure_row(df, cat):
    if not (df["Category"]==cat).any():
        df.loc[len(df)] = [cat, 0]

def compute_summary(df_summary, df_expense, df_income, use_income_details):
    df = df_summary.copy()
    for c in ["Income","Expense","Remaining Balance","Etc"]:
        ensure_row(df, c)
    exp_total = pd.to_numeric(df_expense["Amount"], errors="coerce").fillna(0).sum() if not df_expense.empty else 0.0
    if use_income_details and not df_income.empty:
        inc_total = pd.to_numeric(df_income["Amount"], errors="coerce").fillna(0).sum()
        df.loc[df["Category"]=="Income","Amount"] = inc_total
    else:
        df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    df.loc[df["Category"]=="Expense","Amount"] = exp_total
    income = float(df.loc[df["Category"]=="Income","Amount"].sum())
    expense= float(df.loc[df["Category"]=="Expense","Amount"].sum())
    df.loc[df["Category"]=="Remaining Balance","Amount"] = max(income-expense, 0)
    return df

def draw_pie_with_list(df, title, base_colors, key_tag):
    if df is None or df.empty:
        st.info(f"'{title}'에 표시할 데이터가 없습니다."); return
    if not {"Category","Amount"}.issubset(df.columns):
        st.error(f"'{title}' 데이터에 'Category'와 'Amount'가 필요합니다."); return
    df = df.copy()
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    df = df.groupby("Category", as_index=False)["Amount"].sum()
    df = df[df["Amount"]>0]
    if df.empty:
        st.info(f"'{title}'에 표시할 데이터가 없습니다."); return

    with st.sidebar.expander(f"🎨 색상 변경: {title}", expanded=False):
        color_map = {cat: st.color_picker(cat, base_colors.get(cat, "#9AA0A6"), key=f"{key_tag}_color_{cat}") for cat in df["Category"]}
    colors = [color_map[c] for c in df["Category"]]
    values = df["Amount"].to_numpy(); labels = df["Category"].tolist()
    total = float(values.sum()); fracs = values/total; percents = fracs*100

    col_chart, col_list = st.columns([5,2], gap="large")
    with col_chart:
        fig, ax = plt.subplots(figsize=(st.session_state["fig_size"], st.session_state["fig_size"]))
        wedges, _, autotexts = ax.pie(
            values, labels=None, autopct=lambda p: f"{p:.1f}%", startangle=90,
            colors=colors, pctdistance=st.session_state["pct_distance"],
            textprops={"fontsize": st.session_state["pct_min_fs"], "color":"white","weight":"bold"},
        )
        mn = st.session_state["pct_min_fs"]; mx = st.session_state["pct_max_fs"]
        for i, aut in enumerate(autotexts):
            size = mn + (mx-mn)*np.sqrt(float(fracs[i]))
            aut.set_fontsize(size); aut.set_ha("center"); aut.set_va("center"); aut.set_clip_on(True)
        for w in wedges: w.set_linewidth(1); w.set_edgecolor("white")
        ax.axis("equal")
        plt.title(title, fontsize=st.session_state["title_fs"], fontweight="bold")
        st.pyplot(fig, clear_figure=True)

    with col_list:
        st.markdown("#### 비율 순 정렬")
        order = np.argsort(-percents); top_n = int(st.session_state["list_top_n"])
        items = [(labels[i], percents[i], colors[i]) for i in order[:top_n]]
        md = []
        for name, pct, col in items:
            chip = f"<span style='display:inline-block;width:10px;height:10px;background:{col};border-radius:2px;margin-right:6px;'></span>"
            md.append(f"{chip} **{name}** — {pct:.1f}%")
        st.markdown("<br>".join(md), unsafe_allow_html=True)

def focus_category(label_text="Category"):
    st.components.v1.html(
        f"""<script>
        setTimeout(function(){{
            const els = window.parent.document.querySelectorAll('input[aria-label="{label_text}"]');
            if(els&&els.length){{ els[0].focus(); els[0].select(); }}
        }}, 60);
        </script>""", height=0
    )

def metrics_block(df_sum):
    income = float(df_sum.loc[df_sum["Category"]=="Income","Amount"].sum())
    expense= float(df_sum.loc[df_sum["Category"]=="Expense","Amount"].sum())
    remain = float(df_sum.loc[df_sum["Category"]=="Remaining Balance","Amount"].sum())
    etc    = float(df_sum.loc[df_sum["Category"]=="Etc","Amount"].sum())
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Income", f"{income:,.2f}")
    m2.metric("Expense", f"{expense:,.2f}")
    m3.metric("Remaining", f"{remain:,.2f}")
    m4.metric("Etc", f"{etc:,.2f}")

# ---------------------- 파일 I/O ----------------------
with st.expander("📂 파일 불러오기 / 저장", expanded=False):
    up = st.file_uploader("XLSX 업로드 (시트: Summary, ExpenseDetails, IncomeDetails, Assets, Liabilities)", type=["xlsx"])
    c1,c2,_ = st.columns([1,1,2])
    if up:
        try:
            xls = pd.ExcelFile(up, engine="openpyxl")
            if "Summary" in xls.sheet_names: st.session_state.df_summary = pd.read_excel(xls, "Summary")
            if "ExpenseDetails" in xls.sheet_names: st.session_state.df_expense = pd.read_excel(xls, "ExpenseDetails")
            if "IncomeDetails" in xls.sheet_names:  st.session_state.df_income  = pd.read_excel(xls, "IncomeDetails")
            if "Assets" in xls.sheet_names:         st.session_state.df_assets  = pd.read_excel(xls, "Assets")
            if "Liabilities" in xls.sheet_names:    st.session_state.df_liab    = pd.read_excel(xls, "Liabilities")
            st.success("불러오기 완료")
        except Exception as e:
            st.error(f"불러오기 오류: {e}")

    if c1.button("세션 초기화", key="btn_reset"):
        for k in ["df_summary","df_expense","df_income","df_assets","df_liab","use_income_details","focus_next"]:
            if k in st.session_state: del st.session_state[k]
        init_state(); st.rerun()

    def export_bytes():
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as w:
            calc = compute_summary(st.session_state.df_summary, st.session_state.df_expense,
                                   st.session_state.df_income, st.session_state.use_income_details)
            calc.to_excel(w, index=False, sheet_name="Summary")
            st.session_state.df_income.to_excel(w, index=False, sheet_name="IncomeDetails")
            st.session_state.df_expense.to_excel(w, index=False, sheet_name="ExpenseDetails")
            st.session_state.df_assets.to_excel(w, index=False, sheet_name="Assets")
            st.session_state.df_liab.to_excel(w, index=False, sheet_name="Liabilities")
        out.seek(0); return out.read()
    c2.download_button("현재 상태 엑셀 다운로드", data=export_bytes(),
                       file_name="PFC_Current.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------------------- 실시간 요약(모든 탭 상단) ----------------------
calc_top = compute_summary(st.session_state.df_summary, st.session_state.df_expense,
                           st.session_state.df_income, st.session_state.use_income_details)
st.markdown("### 📌 실시간 요약")
metrics_block(calc_top)

# ---------------------- 입력 & 관리 (Summary 탭을 맨 뒤) ----------------------
st.markdown("---")
st.header("✍️ 입력 & 관리")
tab_inc, tab_exp, tab_ast, tab_liab, tab_sum = st.tabs(
    ["Income 입력","Expense 입력","Assets","Liabilities","Summary(보기/설정)"]
)

# Income
with tab_inc:
    st.subheader("수입 항목 추가")
    with st.form("form_add_income", clear_on_submit=True):
        a,b,c = st.columns([1.2,2,1])
        with a: in_cat  = st.text_input("Category", value="")
        with b: in_desc = st.text_input("Description", value="")
        with c: in_amt  = st.number_input("Amount", min_value=0.0, step=10.0, value=0.0)
        ok = st.form_submit_button("추가")
    if ok:
        if (in_cat or in_desc) or (in_amt>0):
            st.session_state.df_income = pd.concat([st.session_state.df_income,
                pd.DataFrame([{"Category":in_cat,"Description":in_desc,"Amount":in_amt}])], ignore_index=True)
            st.success("추가 완료!")
        st.session_state.focus_next = "income"
        st.rerun()  # 🔁 즉시 상단 요약 갱신

    st.markdown("##### 현재 수입 내역")
    if st.session_state.df_income.empty: st.info("수입 항목이 없습니다.")
    else:
        df = st.session_state.df_income.copy(); df.index = range(1,len(df)+1)
        del_idx = st.multiselect("삭제할 행 선택 (번호)", options=list(df.index), key="ms_del_inc")
        st.dataframe(df, use_container_width=True, key="df_income_table")
        if st.button("선택 행 삭제", key="btn_del_inc"):
            if del_idx:
                real = [i-1 for i in del_idx]
                st.session_state.df_income = st.session_state.df_income.drop(real).reset_index(drop=True)
                st.success("삭제 완료!"); st.rerun()
            else: st.info("선택한 행이 없습니다.")

# Expense
with tab_exp:
    st.subheader("지출 항목 추가")
    with st.form("form_add_expense", clear_on_submit=True):
        a,b,c = st.columns([1.2,2,1])
        with a: exp_cat  = st.text_input("Category", value="")
        with b: exp_desc = st.text_input("Description", value="")
        with c: exp_amt  = st.number_input("Amount", min_value=0.0, step=10.0, value=0.0)
        ok = st.form_submit_button("추가")
    if ok:
        if (exp_cat or exp_desc) or (exp_amt>0):
            st.session_state.df_expense = pd.concat([st.session_state.df_expense,
                pd.DataFrame([{"Category":exp_cat,"Description":exp_desc,"Amount":exp_amt}])], ignore_index=True)
            st.success("추가 완료!")
        st.session_state.focus_next = "expense"
        st.rerun()

    st.markdown("##### 현재 지출 내역")
    if st.session_state.df_expense.empty: st.info("지출 항목이 없습니다.")
    else:
        df = st.session_state.df_expense.copy(); df.index = range(1,len(df)+1)
        del_idx = st.multiselect("삭제할 행 선택 (번호)", options=list(df.index), key="ms_del_exp")
        st.dataframe(df, use_container_width=True, key="df_exp_table")
        if st.button("선택 행 삭제", key="btn_del_exp"):
            if del_idx:
                real = [i-1 for i in del_idx]
                st.session_state.df_expense = st.session_state.df_expense.drop(real).reset_index(drop=True)
                st.success("삭제 완료!"); st.rerun()
            else: st.info("선택한 행이 없습니다.")

# Assets
with tab_ast:
    st.subheader("자산 항목 추가")
    with st.form("form_add_asset", clear_on_submit=True):
        a1,a2 = st.columns([2,1])
        with a1: ast_cat = st.text_input("Category", value="")
        with a2: ast_amt = st.number_input("Amount", min_value=0.0, step=100.0, value=0.0)
        ok = st.form_submit_button("추가")
    if ok:
        if ast_cat or (ast_amt>0):
            st.session_state.df_assets = pd.concat([st.session_state.df_assets,
                pd.DataFrame([{"Category":ast_cat,"Amount":ast_amt}])], ignore_index=True)
            st.success("추가 완료!")
        st.session_state.focus_next = "asset"
        st.rerun()

    st.subheader("Assets 편집")
    st.session_state.df_assets = st.data_editor(st.session_state.df_assets, num_rows="dynamic",
                                                use_container_width=True, key="ed_assets")

# Liabilities
with tab_liab:
    st.subheader("부채 항목 추가")
    with st.form("form_add_liab", clear_on_submit=True):
        l1,l2 = st.columns([2,1])
        with l1: li_cat = st.text_input("Category", value="")
        with l2: li_amt = st.number_input("Amount", min_value=0.0, step=100.0, value=0.0)
        ok = st.form_submit_button("추가")
    if ok:
        if li_cat or (li_amt>0):
            st.session_state.df_liab = pd.concat([st.session_state.df_liab,
                pd.DataFrame([{"Category":li_cat,"Amount":li_amt}])], ignore_index=True)
            st.success("추가 완료!")
        st.session_state.focus_next = "liab"
        st.rerun()

    st.subheader("Liabilities 편집")
    st.session_state.df_liab = st.data_editor(st.session_state.df_liab, num_rows="dynamic",
                                              use_container_width=True, key="ed_liab")

# Summary(보기/설정)
with tab_sum:
    st.subheader("Summary (보기/설정)")
    # 상단과 동일 메트릭도 같이 출력
    calc_in_tab = compute_summary(st.session_state.df_summary, st.session_state.df_expense,
                                  st.session_state.df_income, st.session_state.use_income_details)
    metrics_block(calc_in_tab)
    st.divider()

    st.checkbox("Income을 'Income Details' 합계로 사용", value=st.session_state.use_income_details, key="chk_use_inc_details")
    st.session_state.use_income_details = st.session_state.chk_use_inc_details

    if not st.session_state.use_income_details:
        cur_inc = float(st.session_state.df_summary.loc[st.session_state.df_summary["Category"]=="Income","Amount"].sum())
        new_inc = st.number_input("수동 Income 금액", min_value=0.0, step=100.0, value=cur_inc, key="ni_manual_income")
        st.session_state.df_summary.loc[st.session_state.df_summary["Category"]=="Income","Amount"] = new_inc
        st.caption("※ 'Income Details'를 사용하지 않을 때만 적용됩니다.")

    cur_etc = float(st.session_state.df_summary.loc[st.session_state.df_summary["Category"]=="Etc","Amount"].sum())
    new_etc = st.number_input("Etc 금액", min_value=0.0, step=50.0, value=cur_etc, key="ni_manual_etc")
    st.session_state.df_summary.loc[st.session_state.df_summary["Category"]=="Etc","Amount"] = new_etc

# ---------------------- 시각화 ----------------------
st.markdown("---")
st.header("📈 시각화")

df_sum_calc = compute_summary(st.session_state.df_summary, st.session_state.df_expense,
                              st.session_state.df_income, st.session_state.use_income_details)
def color_block(df, title, palette, key): draw_pie_with_list(df, title, palette, key)
draw_pie_with_list(df_sum_calc, "INCOME / EXPENSE", DEFAULT_COLORS_SUMMARY, key_tag="summary")
draw_pie_with_list(st.session_state.df_assets, "ASSET", DEFAULT_COLORS_ASSETS, key_tag="assets")
draw_pie_with_list(st.session_state.df_liab, "LIABILITY", DEFAULT_COLORS_LIAB, key_tag="liab")

# ---------------------- 포커스 이동 ----------------------
t = st.session_state.get("focus_next")
if t in {"income","expense","asset","liab"}:
    focus_category("Category")
st.session_state["focus_next"] = None
