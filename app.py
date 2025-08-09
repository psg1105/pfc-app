import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="PFC App v0", layout="wide")
st.title("📊 Personal Finance Checkup (v0)")

uploaded_file = st.file_uploader("📂 XLSX 업로드 (시트: Summary, ExpenseDetails, Assets, Liabilities)", type=["xlsx"])

def draw_pie(df: pd.DataFrame, title: str):
    df = df.copy()
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    df = df.groupby("Category", as_index=False)["Amount"].sum()
    df = df[df["Amount"] > 0]
    if df.empty:
        st.info(f"'{title}'에 표시할 데이터가 없습니다.")
        return
    fig, ax = plt.subplots()
    ax.pie(df["Amount"], labels=df["Category"], autopct="%1.1f%%", startangle=90)
    ax.axis("equal")
    st.subheader(title)
    st.pyplot(fig)

if uploaded_file:
    try:
        xls = pd.ExcelFile(uploaded_file, engine="openpyxl")

        # 0) ExpenseDetails 합계 산출
        total_exp = 0.0
        if "ExpenseDetails" in xls.sheet_names:
            df_ed = pd.read_excel(xls, sheet_name="ExpenseDetails")
            if {"Category","Description","Amount"}.issubset(df_ed.columns):
                total_exp = pd.to_numeric(df_ed["Amount"], errors="coerce").fillna(0).sum()
            else:
                st.warning("ExpenseDetails 시트는 'Category, Description, Amount' 컬럼이 필요합니다.")
        else:
            st.warning("시트 'ExpenseDetails' 가 없습니다. (Summary의 Expense는 0으로 집계)")

        # 1) Summary 로드 + 자동 집계 반영
        if "Summary" in xls.sheet_names:
            df_sum = pd.read_excel(xls, sheet_name="Summary")
            if {"Category","Amount"}.issubset(df_sum.columns):
                # 표준 행 확보
                def ensure_row(df, cat):
                    if not (df["Category"] == cat).any():
                        df.loc[len(df)] = [cat, 0]
                for cat in ["Income","Expense","Remaining Balance","Etc"]:
                    ensure_row(df_sum, cat)

                # 숫자 변환
                df_sum["Amount"] = pd.to_numeric(df_sum["Amount"], errors="coerce").fillna(0)

                # Expense 자동 반영
                df_sum.loc[df_sum["Category"]=="Expense","Amount"] = total_exp

                # Remaining = Income - Expense
                income_val = float(df_sum.loc[df_sum["Category"]=="Income","Amount"].sum())
                expense_val = float(df_sum.loc[df_sum["Category"]=="Expense","Amount"].sum())
                df_sum.loc[df_sum["Category"]=="Remaining Balance","Amount"] = max(income_val - expense_val, 0)

                draw_pie(df_sum, "① Income / Expense / Remaining / Etc (비율)")
            else:
                st.error("Summary 시트는 'Category, Amount' 컬럼이 필요합니다.")
        else:
            st.warning("시트 'Summary' 가 없습니다.")

        # 2) Assets 파이
        if "Assets" in xls.sheet_names:
            df_assets = pd.read_excel(xls, sheet_name="Assets")
            if {"Category","Amount"}.issubset(df_assets.columns):
                draw_pie(df_assets, "② Assets 분포 (비율)")
            else:
                st.error("Assets 시트는 'Category, Amount' 컬럼이 필요합니다.")
        else:
            st.warning("시트 'Assets' 가 없습니다.")

        # 3) Liabilities 파이
        if "Liabilities" in xls.sheet_names:
            df_liab = pd.read_excel(xls, sheet_name="Liabilities")
            if {"Category","Amount"}.issubset(df_liab.columns):
                draw_pie(df_liab, "③ Liabilities 분포 (비율)")
            else:
                st.error("Liabilities 시트는 'Category, Amount' 컬럼이 필요합니다.")
        else:
            st.warning("시트 'Liabilities' 가 없습니다.")

        # (선택) 원본 표 미리보기
        with st.expander("원본 데이터 미리보기"):
            if 'df_sum' in locals(): st.write("Summary", df_sum)
            if 'df_ed' in locals(): st.write("ExpenseDetails", df_ed)
            if 'df_assets' in locals(): st.write("Assets", df_assets)
            if 'df_liab' in locals(): st.write("Liabilities", df_liab)

    except Exception as e:
        st.error(f"파일 처리 중 오류: {e}")
else:
    st.info("템플릿을 다운로드하여 입력 후 업로드하세요.")
