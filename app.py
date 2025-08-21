# app.py  — PFC (Personal Finance Checkup) v1

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import re
from io import BytesIO
from datetime import datetime

st.set_page_config(page_title="PFC", layout="wide")

# ========== 세션 초기화 ==========
def ss_init():
    ss = st.session_state
    ss.setdefault("clients_df", pd.DataFrame(
        columns=["id","first_name","last_name","name","email","phone",
                 "street","apt","city","state","zip","home_address","notes"]))
    ss.setdefault("next_client_id", 1)
    ss.setdefault("active_client_id", None)

    # 각 클라이언트의 재무 데이터 저장소 (client_id -> dict)
    ss.setdefault("book", {})  # { client_id: {"income":df, "expense":df, "assets":df, "liab":df, "etc":float} }

    # UI 상태
    ss.setdefault("graph", {
        "radius": 4.0,
        "title_size": 14,
        "pct_min": 7,
        "pct_max": 16,
        "pct_y": 0.68,
        "legend_top": 12
    })

ss_init()


# ========== 유틸 ==========
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

def fmt_phone(s: str) -> str:
    """숫자만 남기고 000-000-0000 형태(최대 10자리). 입력 중에도 매번 호출."""
    digits = re.sub(r"\D", "", s or "")[:10]
    if len(digits) >= 7:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    elif len(digits) >= 4:
        return f"{digits[:3]}-{digits[3:]}"
    else:
        return digits

def valid_email(s: str) -> bool:
    return bool(EMAIL_RE.match(s or ""))

def build_full_address(street, apt, city, state, zipc):
    parts = []
    if street: parts.append(street.strip())
    if apt:    parts.append(apt.strip())
    loc = ", ".join(p for p in [city.strip() if city else "", state.strip() if state else ""] if p)
    if loc:    parts.append(loc)
    if zipc:   parts.append(zipc.strip())
    return ", ".join(parts)

def ensure_client_book(client_id):
    book = st.session_state.book
    if client_id not in book:
        book[client_id] = {
            "income": pd.DataFrame(columns=["Category","Description","Amount"]),
            "expense": pd.DataFrame(columns=["Category","Description","Amount"]),
            "assets": pd.DataFrame(columns=["Category","Amount"]),
            "liab": pd.DataFrame(columns=["Category","Amount"]),
            "etc": 0.0
        }

def get_active_book():
    cid = st.session_state.active_client_id
    if cid is None: 
        return None
    ensure_client_book(cid)
    return st.session_state.book[cid]

def money(x):
    try:
        return f"{float(x):,.2f}"
    except:
        return "0.00"


# ========== 공통: 파이차트 렌더러 ==========
CATEGORY_COLORS_DEFAULT = {
    "Income": "#4472C4", "Expense": "#ED7D31", "Remaining Balance": "#70AD47", "Etc": "#7F7F7F",
    "Stock": "#4472C4", "Mutual Fund": "#6F9FD8", "Real Estate": "#ED7D31", "Savings": "#5B9BD5",
    "Bond": "#A5A5A5", "Insurance": "#FFC000", "Annuity": "#9E480E", "401K": "#C00000", "403B": "#FF9999",
    "CC debt": "#C00000", "Car loan": "#7F6000", "Personal Loan": "#8064A2", "Mortgage": "#BF9000", "Etc.": "#7F7F7F"
}

def pie_with_percent(ax, series: pd.Series, title: str, color_map: dict):
    # series: index=라벨, values=값
    values = series[series>0].sort_values(ascending=False)
    if values.empty:
        ax.text(0.5,0.5,"표시할 데이터가 없습니다.", ha="center", va="center", fontsize=12)
        ax.axis('off')
        return

    # 색 매핑
    colors = [color_map.get(lbl, None) for lbl in values.index]

    # 사이드바 스타일 값
    g = st.session_state.graph
    radius = g["radius"]
    title_size = g["title_size"]
    pct_min = g["pct_min"]
    pct_max = g["pct_max"]
    pct_y = g["pct_y"]

    # 라벨은 비워서 텍스트 이름은 넣지 않음(원 안쪽은 %) — 범례에서 이름 표시
    wedges, _ = ax.pie(
        values.values,
        labels=None,
        startangle=90,
        counterclock=False,
        colors=colors,
        wedgeprops=dict(width=1.0, edgecolor="white")
    )

    # 퍼센트 텍스트
    total = values.sum()
    for w, v, lbl in zip(wedges, values.values, values.index):
        frac = v/total
        pct = frac*100
        # wedge 중심 각도
        ang = (w.theta2 + w.theta1)/2.0
        # 라벨 위치
        x = np.cos(np.deg2rad(ang))*pct_y
        y = np.sin(np.deg2rad(ang))*pct_y
        # 작은 비율은 더 작은 폰트
        fs = pct_min + (pct_max - pct_min)*min(frac/0.25, 1.0)  # 25%이상은 최대 폰트
        ax.text(x, y, f"{pct:.1f}%", ha="center", va="center", fontsize=fs, weight="bold", color="white")

    ax.set_title(title, fontsize=title_size, weight="bold")

    # 정렬된 범례(내림차순)
    legend_labels = [f"{name} — {v/total*100:.1f}%" for name, v in values.items()]
    ax.legend(wedges, values.index, title="비율 순 정렬", loc="center left", bbox_to_anchor=(1, 0.5))

    ax.set_aspect("equal")


# ========== 사이드바(그래프 스타일) ==========
with st.sidebar:
    st.markdown("### 🎛 그래프 스타일")
    g = st.session_state.graph
    g["radius"] = st.slider("그래프 크기(인치)", 3.0, 6.0, g["radius"], 0.25)
    g["title_size"] = st.slider("제목 글씨 크기", 10, 24, g["title_size"], 1)
    col_a, col_b = st.columns(2)
    with col_a:
        g["pct_min"] = st.slider("퍼센트 최소 글씨", 6, 16, g["pct_min"], 1)
    with col_b:
        g["pct_max"] = st.slider("퍼센트 최대 글씨", 12, 26, g["pct_max"], 1)
    g["pct_y"] = st.slider("퍼센트 위치(중심→테두리)", 0.4, 0.9, g["pct_y"], 0.01)
    g["legend_top"] = st.slider("우측 리스트 항목 수", 5, 20, g["legend_top"], 1)


# ========== 상단: 파일 불러오기/저장(간단 CSV) ==========
with st.expander("📂 파일 불러오기 / 저장", expanded=False):
    st.caption("※ 간단 CSV 저장/복원(클라이언트/데이터 포함). 상용 배포 전 DB로 교체 권장.")
    col_u, col_d = st.columns(2)
    with col_u:
        up = st.file_uploader("불러오기(csv)", type=["csv"])
        if up is not None:
            df = pd.read_csv(up)
            try:
                # 매우 단순한 저장 포맷: type 컬럼으로 구분
                clients = df[df["type"]=="client"].drop(columns=["type"]).copy()
                data    = df[df["type"]!="client"].copy()
                if not clients.empty:
                    st.session_state.clients_df = clients.reset_index(drop=True)
                    if "id" in clients.columns:
                        st.session_state.next_client_id = (clients["id"].max()+1) if len(clients)>0 else 1
                # 데이터 복원
                st.session_state.book = {}
                for cid in clients["id"].unique():
                    ensure_client_book(int(cid))
                for _, r in data.iterrows():
                    cid = int(r["client_id"])
                    ensure_client_book(cid)
                    bucket = r["type"]
                    if bucket in ["income","expense"]:
                        st.session_state.book[cid][bucket] = pd.concat(
                            [st.session_state.book[cid][bucket],
                             pd.DataFrame([{"Category":r["Category"],"Description":r.get("Description",""),"Amount":r["Amount"]}])],
                            ignore_index=True)
                    elif bucket in ["assets","liab"]:
                        st.session_state.book[cid][bucket] = pd.concat(
                            [st.session_state.book[cid][bucket],
                             pd.DataFrame([{"Category":r["Category"],"Amount":r["Amount"]}])],
                            ignore_index=True)
                    elif bucket == "etc":
                        st.session_state.book[cid]["etc"] = float(r["Amount"])
                st.success("불러오기 완료")
            except Exception as e:
                st.error(f"불러오기 실패: {e}")

    with col_d:
        if st.button("현재 상태 저장(csv)"):
            # 클라이언트
            cdf = st.session_state.clients_df.copy()
            if not cdf.empty: cdf["type"] = "client"
            rows = [cdf]
            # 데이터
            for cid, b in st.session_state.book.items():
                for bucket in ["income","expense"]:
                    if not b[bucket].empty:
                        tmp = b[bucket].copy()
                        tmp["type"] = bucket
                        tmp["client_id"] = cid
                        rows.append(tmp)
                for bucket in ["assets","liab"]:
                    if not b[bucket].empty:
                        tmp = b[bucket].copy()
                        tmp["Description"] = ""
                        tmp["type"] = bucket
                        tmp["client_id"] = cid
                        rows.append(tmp)
                # etc
                rows.append(pd.DataFrame([{
                    "type":"etc","client_id":cid,"Category":"Etc","Description":"","Amount":b["etc"]
                }]))
            if rows:
                out = pd.concat(rows, ignore_index=True)
                csv = out.to_csv(index=False).encode("utf-8")
                st.download_button("CSV 다운로드", csv, file_name="pfc_export.csv", mime="text/csv")


# ========== 상단: 실시간 요약 (모든 탭 공통 표시) ==========
def calc_summary_for_active():
    cid = st.session_state.active_client_id
    if cid is None: 
        return 0.0, 0.0, 0.0, 0.0
    b = get_active_book()
    income = float(b["income"]["Amount"].sum()) if not b["income"].empty else 0.0
    expense = float(b["expense"]["Amount"].sum()) if not b["expense"].empty else 0.0
    etc = float(b.get("etc",0.0) or 0.0)
    remaining = max(income - expense, 0.0)
    return income, expense, remaining, etc

def summary_bar():
    income, expense, remaining, etc = calc_summary_for_active()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Income", money(income))
    col2.metric("Expense", money(expense))
    col3.metric("Remaining", money(remaining))
    col4.metric("Etc", money(etc))


st.markdown("## 📊 Personal Finance Checkup (v1)")
summary_bar()
st.markdown("---")


# ========== 탭: 클라이언트 선택/관리 ==========
st.subheader("👥 클라이언트 선택 / 관리")
tab_list, tab_new = st.tabs(["리스트/선택","신규 등록"])

with tab_new:
    # 신규등록 폼
    with st.form("new_client_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            first_name = st.text_input("First Name", key="new_first")
        with c2:
            last_name  = st.text_input("Last Name",  key="new_last")

        # Phone Number 자동 포맷: 입력값을 매번 포맷해서 value로 반영
        if "new_phone" not in st.session_state:
            st.session_state.new_phone = ""
        raw_phone = st.text_input("Phone Number", value=st.session_state.new_phone, placeholder="000-000-0000")
        ph = fmt_phone(raw_phone)
        if ph != st.session_state.new_phone:
            st.session_state.new_phone = ph

        email = st.text_input("Email", key="new_email", placeholder="name@example.com")

        st.markdown("**Home address**")
        street = st.text_input("Street Address", key="new_street")
        apt    = st.text_input("Ste#/Apt#/Unit# (Optional)", key="new_apt")
        c3, c4, c5 = st.columns([1,0.6,0.8])
        with c3:
            city  = st.text_input("City", key="new_city")
        with c4:
            state = st.text_input("State", key="new_state", max_chars=2)
        with c5:
            zipc  = st.text_input("Zip Code", key="new_zip")

        notes = st.text_area("Notes", key="new_notes", height=90)

        # 유효성
        req_ok = all([
            (first_name or "").strip(),
            (last_name or "").strip(),
            valid_email(email),
            len(re.sub(r"\D","", st.session_state.new_phone)) == 10,
            (street or "").strip(), (city or "").strip(), (state or "").strip(), (zipc or "").strip()
        ])
        err_msgs = []
        if email and not valid_email(email): err_msgs.append("이메일 형식이 올바르지 않습니다.")
        if st.session_state.new_phone and len(re.sub(r"\D","", st.session_state.new_phone)) != 10:
            err_msgs.append("전화번호는 10자리(예: 224-829-2014) 여야 합니다.")
        if state and len(state.strip()) != 2: err_msgs.append("State는 2글자 약어로 입력하세요. (예: IL)")
        for m in err_msgs:
            st.markdown(f"<small style='color:#ff6b6b'>{m}</small>", unsafe_allow_html=True)

        submitted = st.form_submit_button("등록", use_container_width=True, disabled=not req_ok)
        if submitted:
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
                "phone": st.session_state.new_phone,
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
            st.success("클라이언트가 등록되었습니다.")
            # 입력칸 클리어
            st.session_state.new_first=""
            st.session_state.new_last=""
            st.session_state.new_phone=""
            st.session_state.new_email=""
            st.session_state.new_street=""
            st.session_state.new_apt=""
            st.session_state.new_city=""
            st.session_state.new_state=""
            st.session_state.new_zip=""
            st.session_state.new_notes=""
            st.rerun()

with tab_list:
    cdf = st.session_state.clients_df
    st.markdown("#### 등록된 클라이언트")
    st.dataframe(cdf[["id","name","email","phone","home_address"]], use_container_width=True, hide_index=True)

    # 선택/수정/삭제
    st.markdown("##### 클라이언트 선택")
    options = []
    for _, r in cdf.iterrows():
        options.append(f'{r["id"]} — {r["name"]} — {r["email"]}')
    sel = st.selectbox("선택", options, index=0 if options else None, placeholder="클라이언트를 선택하세요.")
    if sel:
        sel_id = int(sel.split(" — ")[0])
        st.session_state.active_client_id = sel_id
        st.success("선택되었습니다. 아래에서 입력을 진행하세요.")

        # 디테일/수정/삭제
        st.markdown("##### 프로필 보기 / 수정")
        row = cdf[cdf["id"]==sel_id].iloc[0]
        with st.form(f"edit_client_{sel_id}", clear_on_submit=False):
            cc1, cc2 = st.columns(2)
            with cc1:
                e_first = st.text_input("First Name", value=row["first_name"])
            with cc2:
                e_last  = st.text_input("Last Name",  value=row["last_name"])

            e_phone_raw = st.text_input("Phone Number", value=row["phone"], placeholder="000-000-0000")
            e_phone = fmt_phone(e_phone_raw)
            if not valid_email(row["email"]):
                # 수정폼에서 보이는 value를 수정했을 수 있으므로…
                pass
            e_email = st.text_input("Email", value=row["email"])

            st.markdown("**Home address**")
            e_street = st.text_input("Street Address", value=row["street"])
            e_apt    = st.text_input("Ste#/Apt#/Unit# (Optional)", value=row.get("apt",""))
            ec1, ec2, ec3 = st.columns([1,0.6,0.8])
            with ec1:
                e_city  = st.text_input("City", value=row["city"])
            with ec2:
                e_state = st.text_input("State", value=row["state"], max_chars=2)
            with ec3:
                e_zip   = st.text_input("Zip Code", value=row["zip"])

            e_notes = st.text_area("Notes", value=row.get("notes",""), height=90)

            col_a, col_b = st.columns(2)
            with col_a:
                update = st.form_submit_button("수정 저장", use_container_width=True)
            with col_b:
                delete = st.form_submit_button("선택 삭제", use_container_width=True)

            if update:
                # 저장
                idx = cdf.index[cdf["id"]==sel_id][0]
                st.session_state.clients_df.loc[idx,"first_name"] = e_first.strip()
                st.session_state.clients_df.loc[idx,"last_name"]  = e_last.strip()
                st.session_state.clients_df.loc[idx,"name"]       = f"{e_first.strip()} {e_last.strip()}"
                st.session_state.clients_df.loc[idx,"phone"]      = fmt_phone(e_phone)
                st.session_state.clients_df.loc[idx,"email"]      = e_email.strip()
                st.session_state.clients_df.loc[idx,"street"]     = e_street.strip()
                st.session_state.clients_df.loc[idx,"apt"]        = (e_apt or "").strip()
                st.session_state.clients_df.loc[idx,"city"]       = e_city.strip()
                st.session_state.clients_df.loc[idx,"state"]      = e_state.strip()
                st.session_state.clients_df.loc[idx,"zip"]        = e_zip.strip()
                st.session_state.clients_df.loc[idx,"home_address"] = build_full_address(
                    e_street, e_apt, e_city, e_state, e_zip)
                st.session_state.clients_df.loc[idx,"notes"]      = (e_notes or "").strip()
                st.success("수정 저장 완료")
                st.rerun()
            if delete:
                # 삭제
                st.session_state.clients_df = cdf[cdf["id"]!=sel_id].reset_index(drop=True)
                st.session_state.book.pop(sel_id, None)
                st.session_state.active_client_id = None
                st.success("삭제되었습니다.")
                st.rerun()


st.markdown("---")
summary_bar()
st.markdown("## ✍️ 입력 & 관리")

# ========== 재무 입력 탭(선택된 클라이언트 기준) ==========
tabs = st.tabs(["Income 입력","Expense 입력","Assets","Liabilities","Summary(보기/설정)"])

# ------ Income
with tabs[0]:
    cid = st.session_state.active_client_id
    if cid is None:
        st.info("먼저 클라이언트를 선택하세요.")
    else:
        ensure_client_book(cid)
        b = get_active_book()
        st.markdown("#### 수입 항목 추가")
        with st.form(f"add_income_{cid}", clear_on_submit=True):
            c1,c2,c3 = st.columns([1,2,1])
            icat = c1.text_input("Category")
            idesc = c2.text_input("Description")
            iamt = c3.number_input("Amount", min_value=0.0, step=10.0, format="%.2f")
            added = st.form_submit_button("추가")
            if added and icat and iamt>0:
                b["income"] = pd.concat([b["income"], pd.DataFrame([{
                    "Category":icat.strip(), "Description":idesc.strip(), "Amount":float(iamt)
                }])], ignore_index=True)
                st.success("추가 완료")
                st.rerun()

        st.markdown("#### 현재 수입 내역")
        if b["income"].empty:
            st.info("수입 항목이 없습니다.")
        else:
            df_show = b["income"].copy()
            df_show.index = range(1, len(df_show)+1)
            st.dataframe(df_show, use_container_width=True)

# ------ Expense
with tabs[1]:
    cid = st.session_state.active_client_id
    if cid is None:
        st.info("먼저 클라이언트를 선택하세요.")
    else:
        ensure_client_book(cid)
        b = get_active_book()
        st.markdown("#### 지출 항목 추가")
        with st.form(f"add_expense_{cid}", clear_on_submit=True):
            c1,c2,c3 = st.columns([1,2,1])
            ecat = c1.text_input("Category")
            edesc = c2.text_input("Description")
            eamt = c3.number_input("Amount", min_value=0.0, step=10.0, format="%.2f")
            added = st.form_submit_button("추가")
            if added and ecat and eamt>0:
                b["expense"] = pd.concat([b["expense"], pd.DataFrame([{
                    "Category":ecat.strip(), "Description":edesc.strip(), "Amount":float(eamt)
                }])], ignore_index=True)
                st.success("추가 완료")
                st.rerun()

        st.markdown("#### 현재 지출 내역")
        if b["expense"].empty:
            st.info("지출 항목이 없습니다.")
        else:
            df_show = b["expense"].copy()
            df_show.index = range(1, len(df_show)+1)
            st.dataframe(df_show, use_container_width=True)

# ------ Assets
with tabs[2]:
    cid = st.session_state.active_client_id
    if cid is None:
        st.info("먼저 클라이언트를 선택하세요.")
    else:
        ensure_client_book(cid)
        b = get_active_book()
        st.markdown("#### Assets 편집")
        with st.form(f"add_asset_{cid}", clear_on_submit=True):
            c1,c2 = st.columns([2,1])
            acat = c1.text_input("Category (예: Stock, Savings, 401K, Real Estate, ...)")
            aamt = c2.number_input("Amount", min_value=0.0, step=10.0, format="%.2f")
            added = st.form_submit_button("추가")
            if added and acat and aamt>0:
                b["assets"] = pd.concat([b["assets"], pd.DataFrame([{
                    "Category":acat.strip(),"Amount":float(aamt)
                }])], ignore_index=True)
                st.success("추가 완료")
                st.rerun()

        if b["assets"].empty:
            st.info("자산 데이터가 없습니다.")
        else:
            df_show = b["assets"].copy()
            df_show.index = range(1, len(df_show)+1)
            st.dataframe(df_show, use_container_width=True)

# ------ Liabilities
with tabs[3]:
    cid = st.session_state.active_client_id
    if cid is None:
        st.info("먼저 클라이언트를 선택하세요.")
    else:
        ensure_client_book(cid)
        b = get_active_book()
        st.markdown("#### Liabilities 편집")
        with st.form(f"add_liab_{cid}", clear_on_submit=True):
            c1,c2 = st.columns([2,1])
            lcat = c1.text_input("Category (예: CC debt, Car loan, Mortgage, ...)")
            lamt = c2.number_input("Amount", min_value=0.0, step=10.0, format="%.2f")
            added = st.form_submit_button("추가")
            if added and lcat and lamt>0:
                b["liab"] = pd.concat([b["liab"], pd.DataFrame([{
                    "Category":lcat.strip(),"Amount":float(lamt)
                }])], ignore_index=True)
                st.success("추가 완료")
                st.rerun()

        if b["liab"].empty:
            st.info("부채 데이터가 없습니다.")
        else:
            df_show = b["liab"].copy()
            df_show.index = range(1, len(df_show)+1)
            st.dataframe(df_show, use_container_width=True)

# ------ Summary
with tabs[4]:
    cid = st.session_state.active_client_id
    if cid is None:
        st.info("먼저 클라이언트를 선택하세요.")
    else:
        b = get_active_book()
        st.markdown("#### Summary (보기/설정)")
        colE, colV = st.columns([1,1])
        with colE:
            use_income_total = True  # (지금은 고정) — Income Details 합계를 사용
            etc_val = st.number_input("Etc 금액", min_value=0.0, step=10.0, format="%.2f", value=float(b.get("etc",0.0) or 0.0))
            if st.button("Etc 저장"):
                b["etc"] = float(etc_val)
                st.success("Etc 저장 완료")
                st.rerun()

        # 시각화
        st.markdown("#### 📈 시각화")

        income_sum = float(b["income"]["Amount"].sum()) if not b["income"].empty else 0.0
        expense_sum = float(b["expense"]["Amount"].sum()) if not b["expense"].empty else 0.0
        remaining = max(income_sum - expense_sum, 0.0)
        etc = float(b.get("etc",0.0) or 0.0)

        # 1) INCOME / EXPENSE
        fig1, ax1 = plt.subplots(figsize=(st.session_state.graph["radius"], st.session_state.graph["radius"]))
        s1 = pd.Series({"Income":income_sum, "Expense":expense_sum, "Remaining Balance":remaining, "Etc":etc})
        pie_with_percent(ax1, s1, "INCOME / EXPENSE", CATEGORY_COLORS_DEFAULT)
        st.pyplot(fig1, use_container_width=True)

        # 우측 리스트 형태의 범례는 pie_with_percent에서 처리됨

        # 2) ASSET
        if b["assets"].empty:
            st.info("ASSET에 표시할 데이터가 없습니다.")
        else:
            s2 = b["assets"].groupby("Category")["Amount"].sum()
            fig2, ax2 = plt.subplots(figsize=(st.session_state.graph["radius"], st.session_state.graph["radius"]))
            pie_with_percent(ax2, s2, "ASSET", CATEGORY_COLORS_DEFAULT)
            st.pyplot(fig2, use_container_width=True)

        # 3) LIABILITY
        if b["liab"].empty:
            st.info("LIABILITY에 표시할 데이터가 없습니다.")
        else:
            s3 = b["liab"].groupby("Category")["Amount"].sum()
            fig3, ax3 = plt.subplots(figsize=(st.session_state.graph["radius"], st.session_state.graph["radius"]))
            pie_with_percent(ax3, s3, "LIABILITY", CATEGORY_COLORS_DEFAULT)
            st.pyplot(fig3, use_container_width=True)
