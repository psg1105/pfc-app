import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

st.set_page_config(page_title="PFC App v0", layout="wide")

# 제목
st.title("📊 Personal Finance Checkup (v0)")

# 파일 업로드
uploaded_file = st.file_uploader("📂 재무 데이터 파일 업로드 (CSV 또는 Excel)", type=["csv", "xlsx"])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file, engine="openpyxl")
        
        st.subheader("📄 데이터 미리보기")
        st.dataframe(df)

        # 간단한 통계
        st.subheader("📈 기본 통계")
        st.write(df.describe())

        # 숫자 컬럼 그래프
        numeric_cols = df.select_dtypes(include=np.number).columns.tolist()
        if numeric_cols:
            col_to_plot = st.selectbox("📌 그래프에 표시할 숫자 컬럼 선택", numeric_cols)
            fig, ax = plt.subplots()
            df[col_to_plot].plot(kind="bar", ax=ax)
            st.pyplot(fig)
        else:
            st.info("📌 숫자 데이터가 없습니다.")

    except Exception as e:
        st.error(f"❌ 파일을 불러오는 중 오류가 발생했습니다: {e}")
else:
    st.info("📌 CSV 또는 Excel 파일을 업로드하세요.")

