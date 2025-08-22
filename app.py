# app.py  — PFC v1 (clients + income/expense/assets/liabilities + charts)
# 한국어 UI / 파일형 스토리지(JSON) / 세션 안정화 / 입력 검증 / 전화번호 자동 포맷

import os, re, json, uuid
from typing import Dict, Any, List
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

# ---------- 기본 설정 ----------
st.set_page_config(page_title="Personal Finance Checkup", layout="wide")

DATA_DIR = "data"
CLIENTS_FILE = os.path.join(DATA_DIR, "clients.json")

os.makedirs(DATA_DIR, exist_ok=True)

# ---------- 유틸 ----------
def load_json(path:str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path:str, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def get_clients() -> List[Dict[str,Any]]:
    return load_json(CLIENTS_FILE, [])

def save_clients(clients: List[Dict[str,Any]]):
    save_json(CLIENTS_FILE, clients)

def client_file(client_id:str) -> str:
    return os.path.join(DATA_DIR, f"client_{client_id}.json")

def load_client_data(client_id:str) -> Dict[str,Any]:
    path = client_file(client_id)
    default = {
        "income_details": [],      # [{category, desc, amount}]
        "expense_details": [],     # [{category, desc, amount}]
        "assets": [],              # [{category, amount}]
        "liabilities": [],         # [{category, amount}]
        "summary": {"etc": 0.0}
    }
    return load_json(path, default)

def save_client_data(client_id:str, data:Dict[str,Any]):
    save_json(client_file(client_id), data)

def join_address(street, unit, city, state, zipc):
    parts = [street.strip()]
    if unit.strip():
        parts.append(unit.strip())
    tail = ", ".join([s for s in [city.strip(), state.strip()] if s])
    if tail:
        parts.append(tail)
    if str(zipc).strip():
        parts.append(str(zipc).strip())
    return " ".join(parts).replace("  ", " ").strip()

# ---------- 검증 ----------
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
ZIP_RE   = re.compile(r"^\d{5}(-\d{4})?$")

def only_digits(s:str) -> str:
    return re.sub(r"\D+", "", s or "")

def format_phone_10(s:str) -> str:
    d = only_digits(s)
    d = d[:10]  # 최대 10자리
    if len(d) >= 7:
        return f"{d[:3]}-{d[3:6]}-{d[6:]}"
    elif len(d) >= 4:
        return f"{d[:3]}-{d[3:]}"
    else:
        return d

def valid_phone_10(s:str) -> bool:
    return bool(re.fullmatch(r"\d{3}-\d{3}-\d{4}", s))

# ---------- 세션 초기화 ----------
def init_session():
    keys = {
        "active_client_id": "",
        # 신규 등록용
        "new_first": "", "new_last": "", "new_phone": "", "new_email": "",
        "new_street": "", "new_unit": "", "new_city": "",
        "new_state": "", "new_zip": "", "new_notes": "",
        # 입력 탭 공용(초기화/자동 포커스 용)
        "focus_after_add": ""
    }
    for k,v in keys.items():
        st.session_state.setdefault(k, v)

init_session()

# 전화번호 자동 포맷(폼 밖에서 항상 한 번 적용)
if st.session_state.get("new_phone"):
    st.session_state.new_phone = format_phone_10(st.session_state.new_phone)

# ---------- 헤더 ----------
st.markdown("## 📊 Personal Finance Checkup (v1)")

# ---------- 상단 실시간 요약 (선택된 클라이언트 기준) ----------
def render_realtime_summary(client_id:str):
    left, mid1, mid2, right = st.columns([1,1,1,1])
    if not client_id:
        with left:    st.metric("Income", "0.00")
        with mid1:    st.metric("Expense", "0.00")
        with mid2:    st.metric("Remaining", "0.00")
        with right:   st.metric("Etc", "0.00")
        return

    data = load_client_data(client_id)
    income = sum([x["amount"] for x in data["income_details"]]) if data["income_details"] else 0.0
    expense = sum([x["amount"] for x in data["expense_details"]]) if data["expense_details"] else 0.0
    remaining = max(income - expense, 0.0)
    etc = float(data.get("summary",{}).get("etc", 0.0))

    with left:  st.metric("Income", f"{income:,.2f}")
    with mid1:  st.metric("Expense", f"{expense:,.2f}")
    with mid2:  st.metric("Remaining", f"{remaining:,.2f}")
    with right: st.metric("Etc", f"{etc:,.2f}")

# ---------- 클라이언트 관리 ----------
st.markdown("### 👥 클라이언트")

tab_list, tab_new, tab_profile = st.tabs(["리스트/선택", "신규 등록", "프로필 수정"])

with tab_list:
    st.caption("등록된 클라이언트")
    clients = get_clients()
    df_clients = pd.DataFrame(clients) if clients else pd.DataFrame(columns=["id","first","last","email","phone","home_address"])
    st.dataframe(df_clients[["id","first","last","email","phone","home_address"]], use_container_width=True, hide_index=True)

    # 선택
    options = {f'{c["first"]} {c["last"]} — {c["email"]} ({c["phone"]})': c["id"] for c in clients}
    chosen = st.selectbox("클라이언트 선택", [""] + list(options.keys()), index=0)
    if chosen:
        st.session_state.active_client_id = options[chosen]
        st.success("선택되었습니다. 아래에서 입력을 진행하세요.")
    else:
        st.session_state.active_client_id = ""

    # 삭제
    with st.expander("선택한 클라이언트 삭제"):
        if st.session_state.active_client_id:
            if st.warning("삭제 시 해당 클라이언트의 모든 재무 데이터가 함께 삭제됩니다. 되돌릴 수 없습니다.", icon="⚠️"):
                if st.button("영구 삭제", type="primary"):
                    cid = st.session_state.active_client_id
                    # clients 목록에서 제거
                    new_list = [c for c in clients if c["id"] != cid]
                    save_clients(new_list)
                    # 데이터 파일 삭제
                    p = client_file(cid)
                    if os.path.exists(p):
                        os.remove(p)
                    st.session_state.active_client_id = ""
                    st.success("삭제 완료.")
                    st.experimental_rerun()
        else:
            st.info("먼저 클라이언트를 선택하세요.")

    st.markdown("---")
    st.subheader("📌 실시간 요약")
    render_realtime_summary(st.session_state.active_client_id)

with tab_new:
    st.caption("※ *Apt/Unit#*는 선택 입력, 이메일/전화/우편번호는 형식 검사를 통과해야 등록됩니다.")

    # 필드
    colA, colB = st.columns(2)
    with colA:
        st.session_state.new_first = st.text_input("First Name", value=st.session_state.new_first, key="new_first_key")
    with colB:
        st.session_state.new_last  = st.text_input("Last Name",  value=st.session_state.new_last,  key="new_last_key")

    colP, colE = st.columns(2)
    with colP:
        st.session_state.new_phone = st.text_input("Phone Number", value=st.session_state.new_phone or "", placeholder="000-000-0000", key="new_phone_key")
        # 즉시 포맷 반영
        st.session_state.new_phone = format_phone_10(st.session_state.new_phone)
        if st.session_state.new_phone and not valid_phone_10(st.session_state.new_phone):
            st.caption(":red[형식: 000-000-0000]")

    with colE:
        st.session_state.new_email = st.text_input("Email", value=st.session_state.new_email, key="new_email_key")
        if st.session_state.new_email and not EMAIL_RE.match(st.session_state.new_email):
            st.caption(":red[유효한 이메일 주소가 아닙니다]")

    st.markdown("**Home address**")
    st.session_state.new_street = st.text_input("Street Address", value=st.session_state.new_street, key="new_street_key")
    st.session_state.new_unit   = st.text_input("Ste/Apt/Unit# (Optional)", value=st.session_state.new_unit, key="new_unit_key")

    colC, colS, colZ = st.columns([1,1,1])
    with colC:
        st.session_state.new_city  = st.text_input("City",  value=st.session_state.new_city, key="new_city_key")
    with colS:
        st.session_state.new_state = st.text_input("State", value=st.session_state.new_state, key="new_state_key")
    with colZ:
        st.session_state.new_zip   = st.text_input("Zip Code", value=st.session_state.new_zip, key="new_zip_key")
        if st.session_state.new_zip and not ZIP_RE.match(st.session_state.new_zip):
            st.caption(":red[형식: 5자리 또는 5-4자리]")

    st.session_state.new_notes = st.text_area("Notes", value=st.session_state.new_notes, key="new_notes_key")

    # 검증
    req_ok = all([
        st.session_state.new_first.strip(),
        st.session_state.new_last.strip(),
        EMAIL_RE.match(st.session_state.new_email or "") is not None,
        valid_phone_10(st.session_state.new_phone or ""),
        st.session_state.new_street.strip(),
        st.session_state.new_city.strip(),
        st.session_state.new_state.strip(),
        ZIP_RE.match(st.session_state.new_zip or "") is not None
    ])

    btn = st.button("등록", type="primary", disabled=not req_ok)
    if btn:
        clients = get_clients()
        cid = str(uuid.uuid4())[:12]

        full_addr = join_address(
            st.session_state.new_street,
            st.session_state.new_unit,
            st.session_state.new_city,
            st.session_state.new_state,
            st.session_state.new_zip
        )

        new_client = {
            "id": cid,
            "first": st.session_state.new_first.strip(),
            "last":  st.session_state.new_last.strip(),
            "email": st.session_state.new_email.strip(),
            "phone": st.session_state.new_phone.strip(),
            "home_address": full_addr,
            "notes": st.session_state.new_notes.strip(),
            "created_at": datetime.now().isoformat()
        }
        clients.append(new_client)
        save_clients(clients)

        # 개인 재무 데이터 빈 껍데기 생성
        save_client_data(cid, load_client_data(cid))

        # 입력 필드 초기화
        st.session_state.update({
            "new_first":"", "new_last":"", "new_phone":"", "new_email":"",
            "new_street":"", "new_unit":"", "new_city":"", "new_state":"", "new_zip":"",
            "new_notes":""
        })
        st.success("등록 완료! 리스트에서 선택 후 재무 입력을 진행해 주세요.")
        st.experimental_rerun()

with tab_profile:
    st.caption("리스트/선택 탭에서 클라이언트를 고른 뒤 이곳에서 프로필을 수정/저장할 수 있습니다.")
    cid = st.session_state.active_client_id
    if not cid:
        st.info("먼저 클라이언트를 선택하세요.")
    else:
        clients = get_clients()
        cur = next((c for c in clients if c["id"]==cid), None)
        if not cur:
            st.error("클라이언트를 찾을 수 없습니다.")
        else:
            st.subheader(f"프로필 수정 — {cur['first']} {cur['last']}")
            # 편집 필드
            cA, cB = st.columns(2)
            with cA:
                first = st.text_input("First Name", cur["first"])
            with cB:
                last  = st.text_input("Last Name", cur["last"])

            pE, pP = st.columns(2)
            with pE:
                email = st.text_input("Email", cur["email"])
            with pP:
                phone = st.text_input("Phone Number", cur["phone"], placeholder="000-000-0000")
                phone = format_phone_10(phone)

            st.markdown("**Home address**")
            st_addr = st.text_input("Street Address", cur.get("home_address",""))
            notes   = st.text_area("Notes", cur.get("notes",""))

            ok = True
            if email and not EMAIL_RE.match(email): 
                st.caption(":red[이메일 형식이 올바르지 않습니다]"); ok=False
            if phone and not valid_phone_10(phone):
                st.caption(":red[전화번호 형식: 000-000-0000]"); ok=False

            save_btn = st.button("프로필 저장", disabled=not ok)
            if save_btn and ok:
                cur["first"], cur["last"], cur["email"], cur["phone"] = first.strip(), last.strip(), email.strip(), phone.strip()
                cur["home_address"] = st_addr.strip()
                cur["notes"] = notes.strip()
                save_clients(clients)
                st.success("저장되었습니다.")
                st.experimental_rerun()

# ---------- 입력 & 관리 (재무 데이터) ----------
st.markdown("---")
st.markdown("### ✍️ 입력 & 관리")
if not st.session_state.active_client_id:
    st.info("클라이언트를 먼저 선택하세요. (👥 클라이언트 > 리스트/선택)")
    st.stop()

cid = st.session_state.active_client_id
data = load_client_data(cid)

tab_inc, tab_exp, tab_assets, tab_liab, tab_summary = st.tabs(
    ["Income 입력", "Expense 입력", "Assets", "Liabilities", "Summary(보기/설정)"]
)

def add_row(tbl_key:str, row:Dict[str,Any]):
    data[tbl_key].append(row)
    save_client_data(cid, data)

def del_rows(tbl_key:str, idxes:List[int]):
    keep = [r for i,r in enumerate(data[tbl_key]) if i not in idxes]
    data[tbl_key] = keep
    save_client_data(cid, data)

with tab_inc:
    st.subheader("수입 항목 추가")
    c1, c2, c3 = st.columns([1,2,1])
    with c1:
        cat = st.text_input("Category", key="inc_cat")
    with c2:
        desc = st.text_input("Description", key="inc_desc")
    with c3:
        amt = st.number_input("Amount", min_value=0.0, step=10.0, key="inc_amt")

    if st.button("추가", key="inc_add_btn", disabled=not bool(cat and amt>0)):
        add_row("income_details", {"category":cat.strip(), "desc":desc.strip(), "amount":float(amt)})
        st.session_state.inc_cat = ""; st.session_state.inc_desc=""; st.session_state.inc_amt=0.0
        st.experimental_rerun()

    st.markdown("현재 수입 내역")
    df = pd.DataFrame(data["income_details"]) if data["income_details"] else pd.DataFrame(columns=["category","desc","amount"])
    st.dataframe(df, use_container_width=True)
    # 실시간 요약 갱신
    render_realtime_summary(cid)

with tab_exp:
    st.subheader("지출 항목 추가")
    c1, c2, c3 = st.columns([1,2,1])
    with c1:
        cat = st.text_input("Category", key="exp_cat")
    with c2:
        desc = st.text_input("Description", key="exp_desc")
    with c3:
        amt = st.number_input("Amount", min_value=0.0, step=10.0, key="exp_amt")

    if st.button("추가", key="exp_add_btn", disabled=not bool(cat and amt>0)):
        add_row("expense_details", {"category":cat.strip(), "desc":desc.strip(), "amount":float(amt)})
        st.session_state.exp_cat = ""; st.session_state.exp_desc=""; st.session_state.exp_amt=0.0
        st.experimental_rerun()

    st.markdown("현재 지출 내역")
    df = pd.DataFrame(data["expense_details"]) if data["expense_details"] else pd.DataFrame(columns=["category","desc","amount"])
    st.dataframe(df, use_container_width=True)
    render_realtime_summary(cid)

with tab_assets:
    st.subheader("자산 입력")
    c1, c2 = st.columns([2,1])
    with c1:
        cat = st.text_input("Category", key="ast_cat")
    with c2:
        amt = st.number_input("Amount", min_value=0.0, step=100.0, key="ast_amt")

    if st.button("추가", key="ast_add_btn", disabled=not bool(cat and amt>0)):
        add_row("assets", {"category":cat.strip(), "amount":float(amt)})
        st.session_state.ast_cat=""; st.session_state.ast_amt=0.0
        st.experimental_rerun()

    df = pd.DataFrame(data["assets"]) if data["assets"] else pd.DataFrame(columns=["category","amount"])
    st.dataframe(df, use_container_width=True)
    render_realtime_summary(cid)

with tab_liab:
    st.subheader("부채 입력")
    c1, c2 = st.columns([2,1])
    with c1:
        cat = st.text_input("Category", key="liab_cat")
    with c2:
        amt = st.number_input("Amount", min_value=0.0, step=100.0, key="liab_amt")

    if st.button("추가", key="liab_add_btn", disabled=not bool(cat and amt>0)):
        add_row("liabilities", {"category":cat.strip(), "amount":float(amt)})
        st.session_state.liab_cat=""; st.session_state.liab_amt=0.0
        st.experimental_rerun()

    df = pd.DataFrame(data["liabilities"]) if data["liabilities"] else pd.DataFrame(columns=["category","amount"])
    st.dataframe(df, use_container_width=True)
    render_realtime_summary(cid)

with tab_summary:
    st.subheader("Summary(보기/설정)")
    etc = st.number_input("Etc 금액", min_value=0.0, step=10.0, value=float(data.get("summary",{}).get("etc",0.0)))
    if st.button("Etc 저장"):
        data.setdefault("summary",{})["etc"] = float(etc)
        save_client_data(cid, data)
        st.success("저장 완료")
        st.experimental_rerun()

    st.markdown("#### 실시간 수치")
    render_realtime_summary(cid)

    st.markdown("#### 파이차트")
    # 1) INCOME/EXPENSE/REMAINING/ETC
    income = sum([x["amount"] for x in data["income_details"]]) if data["income_details"] else 0.0
    expense = sum([x["amount"] for x in data["expense_details"]]) if data["expense_details"] else 0.0
    remaining = max(income - expense, 0.0)
    etc_val = float(data.get("summary",{}).get("etc", 0.0))
    labels = ["Income","Expense","Remaining","Etc"]
    vals = [income, expense, remaining, etc_val]
    fig, ax = plt.subplots(figsize=(6,6))
    wedges, texts, autotexts = ax.pie(vals, labels=labels, autopct="%1.1f%%")
    ax.set_title("INCOME / EXPENSE")
    st.pyplot(fig)

    # 2) ASSET 분포
    if data["assets"]:
        dfA = pd.DataFrame(data["assets"])
        grp = dfA.groupby("category")["amount"].sum().sort_values(ascending=False)
        fig2, ax2 = plt.subplots(figsize=(6,6))
        ax2.pie(grp.values, labels=grp.index, autopct="%1.1f%%")
        ax2.set_title("ASSET")
        st.pyplot(fig2)

    # 3) LIABILITY 분포
    if data["liabilities"]:
        dfL = pd.DataFrame(data["liabilities"])
        grpL = dfL.groupby("category")["amount"].sum().sort_values(ascending=False)
        fig3, ax3 = plt.subplots(figsize=(6,6))
        ax3.pie(grpL.values, labels=grpL.index, autopct="%1.1f%%")
        ax3.set_title("LIABILITY")
        st.pyplot(fig3)
