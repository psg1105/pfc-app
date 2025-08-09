import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

st.set_page_config(page_title="PFC App v0", layout="wide")
st.title("📊 Personal Finance Checkup (v0)")

uploaded_file = st.file_uploader("📂 재무 파일 업로드 (XLSX 권장: 시트는 IncomeExpense/Assets/Liabilities)", type=["xlsx", "csv"])

def draw_pie(df: pd.DataFrame, title: str):
    """Category, Amount 로 구성된 df를 받아 파이 차트를 그린다."""
    # 숫자만 남기고 음수/NaN 처리
    df = df.copy()
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
    df = df.groupby("Category", as_index=False)["Amount"].sum()
    df = df[df["Amount"] > 0]

    if df.empty:
        st.info(f"'{title}'에 표시할 데이터가 없습니다.")
        return

    # % 라벨을 함께 보여주기 위해 autopct 사용
    fig, ax = plt.subplots()
    ax.pie(df["Amount"], labels=df["Category"], autopct="%1.1f%%", startangle=90)
    ax.axis("equal")
    st.subheader(title)
    st.pyplot(fig)

if uploaded_file is None:
    st.info("XLSX 파일을 업로드하면 파이 차트를 그립니다. (CSV 업로드 시엔 미리보기만 가능)")
else:
    if uploaded_file.name.endswith(".xlsx"):
        try:
            xls = pd.ExcelFile(uploaded_file, engine="openpyxl")

            # 1) Income / Expense / Remaining / Etc
            if "IncomeExpense" in xls.sheet_names:
                df_ie = pd.read_excel(xls, sheet_name="IncomeExpense")
                # 컬럼 보정
                need_cols = {"Category", "Amount"}
                if need_cols.issubset(set(df_ie.columns)):
                    draw_pie(df_ie, "① Income / Expense / Remaining Balance / Etc (비율)")
                else:
                    st.error("IncomeExpense 시트에 'Category'와 'Amount' 컬럼이 있어야 합니다.")
            else:
                st.warning("시트 'IncomeExpense' 가 없습니다.")

            # 2) Assets pie
            if "Assets" in xls.sheet_names:
                df_assets = pd.read_excel(xls, sheet_name="Assets")
                if {"Category","Amount"}.issubset(set(df_assets.columns)):
                    draw_pie(df_assets, "② Assets 분포 (비율)")
                else:
                    st.error("Assets 시트에 'Category'와 'Amount' 컬럼이 있어야 합니다.")
            else:
                st.warning("시트 'Assets' 가 없습니다.")

            # 3) Liabilities pie
            if "Liabilities" in xls.sheet_names:
                df_liab = pd.read_excel(xls, sheet_name="Liabilities")
                if {"Category","Amount"}.issubset(set(df_liab.columns)):
                    draw_pie(df_liab, "③ Liabilities 분포 (비율)")
                else:
                    st.error("Liabilities 시트에 'Category'와 'Amount' 컬럼이 있어야 합니다.")
            else:
                st.warning("시트 'Liabilities' 가 없습니다.")

        except Exception as e:
            st.error(f"파일 처리 중 오류: {e}")
    else:
        # CSV일 경우: 그냥 미리보기만 (시트 개념이 없어서 세 개 파이차트 구성이 곤란)
        try:
            df = pd.read_csv(uploaded_file)
            st.subheader("CSV 미리보기")
            st.dataframe(df, use_container_width=True)
            st.info("파이차트는 XLSX(시트: IncomeExpense/Assets/Liabilities)로 업로드해야 자동 생성됩니다.")
        except Exception as e:
            st.error(f"CSV 읽기 오류: {e}")
