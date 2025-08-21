# app.py  — PFC App (v1.x)
# 전체 코드: 클라이언트 관리(리스트/선택, 신규 등록, 수정/삭제) + 재무 입력(Income/Expense/Assets/Liabilities) + 실시간 요약
# 주요 변경점:
# - "등록" 버튼 항상 활성화, 제출 시에만 유효성 검사/포맷 적용
# - 전화번호 000-000-0000 포맷으로 저장 (입력 시 제한X, 저장 전에 포맷/검증)
# - 이메일 형식 검사, Apt 칸 Optional
# - 등록/리스트/수정 통합, 리스트에서 선택 → 프로필 보여주고 수정/삭제 가능
# - 선택된 클라이언트 기준으로 실시간 요약 반영

import re
import math
import pandas as pd
import numpy as np
import streamlit as st

# -----------------------------
# 유틸 함수
# -----------------------------
def fmt_phone(raw: str) -> str:
    """숫자만 추출 후 10자리면 000-000-0000 형태로 반환, 아니면 원본 유지"""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"
    return raw.strip()

def valid_email(email: str) -> bool:
    if not email:
        return False
    # 간단/안전한 패턴
    pat = r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
    return re.match(pat, email.strip()) is not None

def build_full_address(street: str, apt: str, city: str, state: str, zipc: str) -> str:
    parts = []
    s = (street or "").strip()
    a = (apt or "").strip()
    c = (city or "").strip()
    t = (state or "").strip()
    z = (zipc or "").strip()
    if s:
        if a:
            parts.append(f"{s} {a}")
        else:
            parts.append(s)
    # City, State Zip
    line2 = " ".join([c, f"{t} {z}".strip()]).strip()
    if line2:
        parts.append(line2)
    return ", ".join(parts)

def money(x) -> float:
    try:
        return float(x)
    except:
        return 0.0

# -----------------------------
# 초기 상태
# -----------------------------
def init_state():
    ss = st.session_state
    if "clients_df" not in ss:
        ss.clients_df = pd.DataFrame(
            columns=[
                "id","first_name","last_name","name","email","phone",
                "street","apt","city","state","zip","home_address","notes"
            ]
        )
    if "next_client_id" not in ss:
        ss.next_client_id = 1

    # client_books: client_id -> dict of dfs
    if "client_books" not in ss:
        ss.client_books = {}

    if "selected_client_id" not in ss:
        ss.selected_client_id = None

init_state()

def ensure_client_book(cid: int):
    books = st.session_state.client_books
    if cid not in books:
        books[cid] = {
            "income": pd.DataFrame(columns=["Category","Description","Amount"]),
            "expense": pd.DataFrame(columns=["Category","Description","Amount"]),
            "assets":  pd.DataFrame(columns=["Category","Amount"]),
            "liab":    pd.DataFrame(columns=["Category","Amount"])
        }

# -----------------------------
# 상단 타이틀 & 파일 (선택)
# -----------------------------
st.set_page_config(page_title="PFC", layout="wide")
st.title("📊 Personal Finance Checkup (v1)")

# -----------------------------
# 실시간 요약 (선택된 클라이언트 기준)
# -----------------------------
def render_top_metrics():
    cid = st.session_state.selected_client_id
    c1,c2,c3,c4 = st.columns(4)
    if cid is None or cid not in st.session_state.client_books:
        with c1: st.metric("Income", "0.00")
        with c2: st.metric("Expense", "0.00")
        with c3: st.metric("Remaining", "0.00")
        with c4: st.metric("Etc", "0.00")
        return

    book = st.session_state.client_books[cid]
    inc = book["income"]["Amount"].map(money).sum() if not book["income"].empty else 0.0
    exp = book["expense"]["Amount"].map(money).sum() if not book["expense"].empty else 0.0
    etc = 0.0  # 추후 별도 필드 필요 시 연결
    rem = inc - exp + etc

    with c1: st.metric("Income", f"{inc:,.2f}")
    with c2: st.metric("Expense", f"{exp:,.2f}")
    with c3: st.metric("Remaining", f"{rem:,.2f}")
    with c4: st.metric("Etc", f"{etc:,.2f}")

render_top_metrics()
st.markdown("---")

# -----------------------------
# 클라이언트 관리 영역
# -----------------------------
st.header("👥 클라이언트 선택 / 관리")

tab_list, tab_new = st.tabs(["리스트/선택", "신규 등록"])

# == 리스트/선택 탭 ==
with tab_list:
    st.subheader("등록된 클라이언트")

    # 표출 표
    if st.session_state.clients_df.empty:
        st.info("등록된 클라이언트가 없습니다.")
    else:
        show_cols = ["id","name","email","phone","home_address"]
        st.dataframe(
            st.session_state.clients_df[show_cols].sort_values("id").set_index("id"),
            use_container_width=True,
            height=280
        )

    # 선택
    all_options = []
    for _, r in st.session_state.clients_df.sort_values("id").iterrows():
        label = f'{r["name"]} — {r["email"]} ({r["id"]})'
        all_options.append((label, int(r["id"])))
    opt_labels = [o[0] for o in all_options]
    opt_values = [o[1] for o in all_options]

    sel = st.selectbox("클라이언트 선택", options=[None]+opt_values, format_func=lambda v: "선택하세요" if v is None else [l for l,val in all_options if val==v][0], key="sel_client_for_work")
    if sel is not None:
        st.session_state.selected_client_id = int(sel)
        ensure_client_book(int(sel))
        st.success("선택되었습니다. 아래에서 입력을 진행하세요.")

        # 선택된 클라이언트 프로필/수정/삭제
        st.markdown("### 프로필 보기/수정")
        dfc = st.session_state.clients_df
        row = dfc.loc[dfc["id"]==sel].iloc[0]

        with st.form("edit_profile"):
            c1,c2 = st.columns(2)
            with c1:
                e_first = st.text_input("First Name", value=row["first_name"])
            with c2:
                e_last  = st.text_input("Last Name", value=row["last_name"])
            e_phone = st.text_input("Phone Number", value=row["phone"], placeholder="000-000-0000")
            e_email = st.text_input("Email", value=row["email"], placeholder="name@example.com")

            st.markdown("**Home address**")
            s1 = st.text_input("Street Address", value=row["street"])
            s2 = st.text_input("Ste#/Apt#/Unit# (Optional)", value=row["apt"])
            cc, ss, zz = st.columns([1,0.6,0.8])
            with cc: city = st.text_input("City", value=row["city"])
            with ss: state = st.text_input("State", value=row["state"], max_chars=2)
            with zz: zipc  = st.text_input("Zip Code", value=row["zip"])
            notes = st.text_area("Notes", value=row["notes"], height=90)

            c_upd, c_del = st.columns([3,1])
            with c_upd:
                update = st.form_submit_button("프로필 저장", use_container_width=True)
            with c_del:
                delete = st.form_submit_button("삭제", use_container_width=True)

            if update:
                errs=[]
                if not e_first.strip(): errs.append("First Name을 입력하세요.")
                if not e_last.strip():  errs.append("Last Name을 입력하세요.")
                if not valid_email(e_email): errs.append("이메일 형식이 올바르지 않습니다.")

                digits = re.sub(r"\D","", e_phone or "")
                if len(digits)!=10: errs.append("전화번호는 10자리(예: 224-829-2014)여야 합니다.")
                phone_fmt = fmt_phone(e_phone)

                if not s1.strip(): errs.append("Street Address를 입력하세요.")
                if not city.strip(): errs.append("City를 입력하세요.")
                if not state.strip() or len(state.strip())!=2: errs.append("State는 2글자 약어로 입력하세요.")
                if not zipc.strip(): errs.append("Zip Code를 입력하세요.")

                if errs:
                    for m in errs:
                        st.markdown(f"<small style='color:#ff6b6b'>{m}</small>", unsafe_allow_html=True)
                else:
                    home = build_full_address(s1,s2,city,state,zipc)
                    idx = dfc.index[dfc["id"]==sel][0]
                    dfc.loc[idx,"first_name"] = e_first.strip()
                    dfc.loc[idx,"last_name"]  = e_last.strip()
                    dfc.loc[idx,"name"]       = f"{e_first.strip()} {e_last.strip()}"
                    dfc.loc[idx,"email"]      = e_email.strip()
                    dfc.loc[idx,"phone"]      = phone_fmt
                    dfc.loc[idx,"street"]     = s1.strip()
                    dfc.loc[idx,"apt"]        = (s2 or "").strip()
                    dfc.loc[idx,"city"]       = city.strip()
                    dfc.loc[idx,"state"]      = state.strip()
                    dfc.loc[idx,"zip"]        = zipc.strip()
                    dfc.loc[idx,"home_address"]= home
                    dfc.loc[idx,"notes"]      = (notes or "").strip()
                    st.success("프로필이 저장되었습니다.")
                    st.rerun()

            if delete:
                # 자료와 함께 삭제
                st.session_state.clients_df = dfc[dfc["id"]!=sel].reset_index(drop=True)
                if sel in st.session_state.client_books:
                    del st.session_state.client_books[sel]
                st.session_state.selected_client_id = None
                st.warning("클라이언트가 삭제되었습니다.")
                st.rerun()

# == 신규 등록 탭 ==
with tab_new:
    st.subheader("새 클라이언트 등록")

    with st.form("new_client_form", clear_on_submit=False):
        c1,c2 = st.columns(2)
        with c1:
            first_name = st.text_input("First Name", key="new_first")
        with c2:
            last_name  = st.text_input("Last Name",  key="new_last")

        # 폼 안에서는 on_change 사용 X → 제출 시 검증/포맷
        if "new_phone" not in st.session_state:
            st.session_state.new_phone = ""
        st.text_input("Phone Number", key="new_phone", placeholder="000-000-0000")
        email  = st.text_input("Email", key="new_email", placeholder="name@example.com")

        st.markdown("**Home address**")
        street = st.text_input("Street Address", key="new_street")
        apt    = st.text_input("Ste#/Apt#/Unit# (Optional)", key="new_apt")
        c3,c4,c5 = st.columns([1,0.6,0.8])
        with c3:
            city  = st.text_input("City", key="new_city")
        with c4:
            state = st.text_input("State", key="new_state", max_chars=2)
        with c5:
            zipc  = st.text_input("Zip Code", key="new_zip")

        notes = st.text_area("Notes", key="new_notes", height=90)

        submitted = st.form_submit_button("등록", use_container_width=True)
        if submitted:
            errors = []
            if not first_name.strip(): errors.append("First Name을 입력하세요.")
            if not last_name.strip():  errors.append("Last Name을 입력하세요.")
            if not valid_email(email): errors.append("이메일 형식이 올바르지 않습니다.")

            digits = re.sub(r"\D","", st.session_state.new_phone or "")
            if len(digits) != 10:
                errors.append("전화번호는 10자리(예: 224-829-2014)여야 합니다.")
            phone_formatted = fmt_phone(st.session_state.new_phone)

            if not street.strip(): errors.append("Street Address를 입력하세요.")
            if not city.strip():   errors.append("City를 입력하세요.")
            if not state.strip() or len(state.strip()) != 2:
                errors.append("State는 2글자 약어로 입력하세요. (예: IL)")
            if not zipc.strip():   errors.append("Zip Code를 입력하세요.")

            if errors:
                for m in errors:
                    st.markdown(f"<small style='color:#ff6b6b'>{m}</small>", unsafe_allow_html=True)
            else:
                # 저장
                cdf = st.session_state.clients_df
                cid = int(st.session_state.next_client_id)
                name = f"{first_name.strip()} {last_name.strip()}"
                home_addr = build_full_address(street, apt, city, state, zipc)
                row = {
                    "id": cid,
                    "first_name": first_name.strip(),
                    "last_name": last_name.strip(),
                    "name": name,
                    "email": email.strip(),
                    "phone": phone_formatted,
                    "street": street.strip(),
                    "apt": (apt or "").strip(),
                    "city": city.strip(),
                    "state": state.strip(),
                    "zip": zipc.strip(),
                    "home_address": home_addr,
                    "notes": (notes or "").strip()
                }
                st.session_state.clients_df = pd.concat([cdf, pd.DataFrame([row])], ignore_index=True)
                st.session_state.next_client_id = cid + 1
                ensure_client_book(cid)
                st.session_state.selected_client_id = cid
                st.success("클라이언트가 등록되었습니다.")

                # 입력칸 초기화
                st.session_state.new_first  = ""
                st.session_state.new_last   = ""
                st.session_state.new_phone  = ""
                st.session_state.new_email  = ""
                st.session_state.new_street = ""
                st.session_state.new_apt    = ""
                st.session_state.new_city   = ""
                st.session_state.new_state  = ""
                st.session_state.new_zip    = ""
                st.session_state.new_notes  = ""
                st.rerun()

st.markdown("---")

# -----------------------------
# 재무 입력 & 관리
# -----------------------------
st.header("✍️ 입력 & 관리")
tabs = st.tabs(["Income 입력", "Expense 입력", "Assets", "Liabilities", "Summary(보기/설정)"])

def require_selected_client():
    cid = st.session_state.selected_client_id
    if cid is None or cid not in st.session_state.client_books:
        st.info("먼저 상단에서 클라이언트를 선택(또는 등록)하세요.")
        return None, None
    return cid, st.session_state.client_books[cid]

# ---- Income 입력 ----
with tabs[0]:
    cid, book = require_selected_client()
    if cid is not None:
        st.subheader("수입 항목 추가")
        c1,c2,c3 = st.columns([1,1,0.5])
        with c1: inc_cat = st.text_input("Category", key="inc_cat")
        with c2: inc_desc= st.text_input("Description", key="inc_desc")
        with c3: inc_amt = st.number_input("Amount", min_value=0.0, step=1.0, key="inc_amt")

        if st.button("추가", key="btn_add_inc"):
            df = book["income"]
            new = {"Category":inc_cat.strip(),"Description":inc_desc.strip(),"Amount":inc_amt}
            book["income"] = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
            st.success("추가 완료!")
            st.rerun()

        st.subheader("현재 수입 내역")
        df_show = book["income"].copy()
        if df_show.empty:
            st.info("수입 항목이 없습니다.")
        else:
            df_show.index = range(1, len(df_show)+1)
            st.dataframe(df_show, use_container_width=True)

# ---- Expense 입력 ----
with tabs[1]:
    cid, book = require_selected_client()
    if cid is not None:
        st.subheader("지출 항목 추가")
        c1,c2,c3 = st.columns([1,1,0.5])
        with c1: exp_cat = st.text_input("Category", key="exp_cat")
        with c2: exp_desc= st.text_input("Description", key="exp_desc")
        with c3: exp_amt = st.number_input("Amount", min_value=0.0, step=1.0, key="exp_amt")

        if st.button("추가", key="btn_add_exp"):
            df = book["expense"]
            new = {"Category":exp_cat.strip(),"Description":exp_desc.strip(),"Amount":exp_amt}
            book["expense"] = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
            st.success("추가 완료!")
            st.rerun()

        st.subheader("현재 지출 내역")
        df_show = book["expense"].copy()
        if df_show.empty:
            st.info("지출 항목이 없습니다.")
        else:
            df_show.index = range(1, len(df_show)+1)
            st.dataframe(df_show, use_container_width=True)

# ---- Assets ----
with tabs[2]:
    cid, book = require_selected_client()
    if cid is not None:
        st.subheader("자산 편집")
        # 간단 입력
        c1,c2 = st.columns([1,0.6])
        with c1: a_cat = st.text_input("Category", key="ast_cat")
        with c2: a_amt = st.number_input("Amount", min_value=0.0, step=1.0, key="ast_amt")
        if st.button("추가", key="btn_add_ast"):
            df = book["assets"]
            new = {"Category":a_cat.strip(),"Amount":a_amt}
            book["assets"] = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
            st.success("추가 완료!")
            st.rerun()

        df_show = book["assets"].copy()
        if df_show.empty:
            st.info("자산 데이터가 없습니다.")
        else:
            df_show.index = range(1, len(df_show)+1)
            st.dataframe(df_show, use_container_width=True)

# ---- Liabilities ----
with tabs[3]:
    cid, book = require_selected_client()
    if cid is not None:
        st.subheader("부채 편집")
        c1,c2 = st.columns([1,0.6])
        with c1: l_cat = st.text_input("Category", key="lia_cat")
        with c2: l_amt = st.number_input("Amount", min_value=0.0, step=1.0, key="lia_amt")
        if st.button("추가", key="btn_add_lia"):
            df = book["liab"]
            new = {"Category":l_cat.strip(),"Amount":l_amt}
            book["liab"] = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
            st.success("추가 완료!")
            st.rerun()

        df_show = book["liab"].copy()
        if df_show.empty:
            st.info("부채 데이터가 없습니다.")
        else:
            df_show.index = range(1, len(df_show)+1)
            st.dataframe(df_show, use_container_width=True)

# ---- Summary ----
with tabs[4]:
    cid, book = require_selected_client()
    st.subheader("Summary(보기/설정)")
    if cid is None:
        st.info("클라이언트를 선택하면 요약이 표시됩니다.")
    else:
        inc = book["income"]["Amount"].map(money).sum() if not book["income"].empty else 0.0
        exp = book["expense"]["Amount"].map(money).sum() if not book["expense"].empty else 0.0
        etc = 0.0
        rem = inc - exp + etc
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.metric("Income", f"{inc:,.2f}")
        with c2: st.metric("Expense", f"{exp:,.2f}")
        with c3: st.metric("Remaining", f"{rem:,.2f}")
        with c4: st.metric("Etc", f"{etc:,.2f}")

        st.markdown("— 상세 표")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Income Details**")
            df = book["income"].copy()
            if df.empty: st.info("없음")
            else:
                df.index = range(1,len(df)+1)
                st.dataframe(df, use_container_width=True)
        with col2:
            st.markdown("**Expense Details**")
            df = book["expense"].copy()
            if df.empty: st.info("없음")
            else:
                df.index = range(1,len(df)+1)
                st.dataframe(df, use_container_width=True)
