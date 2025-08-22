import streamlit as st
import json
from pathlib import Path
from datetime import datetime, timezone
import uuid
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# =====================
# App configuration
# =====================
st.set_page_config(page_title="PFC (Personal Finance Checkup)", layout="wide")
st.title("📦 PFC (Personal Finance Checkup)")

# =====================
# Storage paths
# =====================
DATA_DIR = Path("data")
CLIENTS_FILE = Path("clients.json")
DATA_DIR.mkdir(exist_ok=True)
if not CLIENTS_FILE.exists():
    CLIENTS_FILE.write_text("[]", encoding="utf-8")

# =====================
# Utilities: validation & formatting
# =====================
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
STATE_RE = re.compile(r"^[A-Za-z]{2}$")

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")

def format_phone(s: str) -> str:
    d = only_digits(s)
    if len(d) == 10:
        return f"{d[0:3]}-{d[3:6]}-{d[6:10]}"
    return d

def validate_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email or ""))

def validate_phone10(phone: str) -> bool:
    return len(only_digits(phone)) == 10

def validate_state(state: str) -> bool:
    return bool(STATE_RE.match((state or "").strip()))

def validate_zip(zipcode: str) -> bool:
    return bool(ZIP_RE.match((zipcode or "").strip()))

def build_home_address(street: str, apt: str, city: str, state: str, zipcode: str) -> str:
    street_part = (street or "").strip()
    if (apt or "").strip():
        street_part += f" {apt.strip()}"
    city = (city or "").strip()
    state = (state or "").strip().upper()
    zipcode = (zipcode or "").strip()
    pieces = []
    if street_part:
        pieces.append(street_part)
    loc = ", ".join(p for p in [city, f"{state} {zipcode}".strip()] if p)
    if loc:
        pieces.append(loc)
    return ", ".join(pieces)

# =====================
# Persistence helpers
# =====================
def load_clients() -> list:
    try:
        return json.loads(CLIENTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_clients(clients: list) -> None:
    CLIENTS_FILE.write_text(json.dumps(clients, ensure_ascii=False, indent=2), encoding="utf-8")

def get_client(clients: list, client_id: str) -> dict | None:
    for c in clients:
        if c.get("id") == client_id:
            return c
    return None

def client_data_path(client_id: str) -> Path:
    return DATA_DIR / f"client_{client_id}.json"

def _empty_finance() -> dict:
    return {
        "income_details": [],
        "expense_details": [],
        "assets": [],
        "liabilities": [],
        "summary": {"etc": 0.0},
    }

def load_client_finance(client_id: str) -> dict:
    p = client_data_path(client_id)
    if not p.exists():
        data = _empty_finance()
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        # schema guard
        for k, v in _empty_finance().items():
            raw.setdefault(k, v)
        raw["summary"].setdefault("etc", 0.0)
        return raw
    except Exception:
        return _empty_finance()

def save_client_finance(client_id: str, data: dict) -> None:
    p = client_data_path(client_id)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def delete_client_and_data(client_id: str) -> None:
    p = client_data_path(client_id)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass
    clients = load_clients()
    clients = [c for c in clients if c.get("id") != client_id]
    save_clients(clients)

# =====================
# Session defaults & helpers
# =====================
if "selected_client_id" not in st.session_state:
    st.session_state.selected_client_id = None
if "_edit_loaded_id" not in st.session_state:
    st.session_state._edit_loaded_id = None

for k in [
    "reg_first","reg_last","reg_email","reg_phone",
    "reg_street","reg_apt","reg_city","reg_state","reg_zip",
    "reg_notes",
]:
    st.session_state.setdefault(k, "")

st.session_state.reg_phone = format_phone(st.session_state.reg_phone)

def clear_transient_inputs(client_id: str | None):
    if not client_id:
        return
    suffix = f"_{client_id}"
    for key in list(st.session_state.keys()):
        if key.endswith(suffix) and (
            key.startswith("income_details_")
            or key.startswith("expense_details_")
            or key.startswith("assets_")
            or key.startswith("liabilities_")
            or key.startswith("summary_etc_")
            or key.startswith("editrow_")
        ):
            st.session_state.pop(key, None)

# =====================
# Top summary
# =====================
summary_box = st.container()
with summary_box:
    clients = load_clients()
    sel_id = st.session_state.selected_client_id
    if sel_id and get_client(clients, sel_id):
        finance = load_client_finance(sel_id)
        income_sum = float(sum(x.get("amount", 0.0) for x in finance.get("income_details", [])))
        expense_sum = float(sum(x.get("amount", 0.0) for x in finance.get("expense_details", [])))
        remaining = max(income_sum - expense_sum, 0.0)
        etc_val = float(finance.get("summary", {}).get("etc", 0.0))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Income", f"${income_sum:,.2f}")
        c2.metric("Expense", f"${expense_sum:,.2f}")
        c3.metric("Remaining", f"${remaining:,.2f}")
        c4.metric("Etc", f"${etc_val:,.2f}")
    else:
        st.info("선택된 클라이언트가 없습니다. ‘리스트/선택’ 탭에서 클라이언트를 선택하세요.")

st.divider()

# =====================
# Tabs
# =====================
TAB1, TAB2, TAB3, TAB4 = st.tabs(["1) 신규 등록", "2) 리스트/선택", "3) 재무 입력", "4) 시각화"])

# -------- TAB 1: 신규 등록 --------
with TAB1:
    st.subheader("1-1. 신규 등록")
    with st.form("new_client_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("First Name", key="reg_first")
        with col2:
            st.text_input("Last Name", key="reg_last")

        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Phone (10 digits)", key="reg_phone")
        with col2:
            st.text_input("Email", key="reg_email")

        st.markdown("**Home Address**")
        col1, col2 = st.columns([2, 1])
        with col1:
            st.text_input("Street Address", key="reg_street")
            st.text_input("Ste (Apt/Unit) — Optional", key="reg_apt")
        with col2:
            st.text_input("City", key="reg_city")
            st.text_input("State (2 letters)", key="reg_state")
            st.text_input("Zip (12345 or 12345-6789)", key="reg_zip")

        st.text_area("Notes", key="reg_notes")

        submitted = st.form_submit_button("등록")
        if submitted:
            errs = []
            if not st.session_state.reg_first.strip(): errs.append("First Name을 입력하세요.")
            if not st.session_state.reg_last.strip(): errs.append("Last Name을 입력하세요.")
            if not validate_email(st.session_state.reg_email): errs.append("Email 형식이 올바르지 않습니다.")
            if not validate_phone10(st.session_state.reg_phone): errs.append("Phone Number는 정확히 10자리여야 합니다.")
            if not st.session_state.reg_street.strip(): errs.append("Street Address를 입력하세요.")
            if not st.session_state.reg_city.strip(): errs.append("City를 입력하세요.")
            if not validate_state(st.session_state.reg_state): errs.append("State는 2글자여야 합니다.")
            if not validate_zip(st.session_state.reg_zip): errs.append("Zip은 12345 또는 12345-6789 형식이어야 합니다.")

            if errs:
                st.markdown("<div style='color:#c1121f;font-size:0.9rem;'>"+ "<br>".join([f"• {e}" for e in errs]) +"</div>", unsafe_allow_html=True)
            else:
                phone_fmt = format_phone(st.session_state.reg_phone)
                state_up = st.session_state.reg_state.strip().upper()
                home_address = build_home_address(
                    st.session_state.reg_street, st.session_state.reg_apt,
                    st.session_state.reg_city, state_up, st.session_state.reg_zip,
                )
                new_client = {
                    "id": uuid.uuid4().hex,
                    "first": st.session_state.reg_first.strip(),
                    "last": st.session_state.reg_last.strip(),
                    "email": st.session_state.reg_email.strip(),
                    "phone": phone_fmt,
                    "home_address": home_address,
                    "address_street": st.session_state.reg_street.strip(),
                    "address_apt": st.session_state.reg_apt.strip(),
                    "address_city": st.session_state.reg_city.strip(),
                    "address_state": state_up,
                    "address_zip": st.session_state.reg_zip.strip(),
                    "notes": st.session_state.reg_notes.strip(),
                    "created_at": now_iso(),
                }
                clients = load_clients()
                clients.append(new_client)
                save_clients(clients)
                st.success("등록되었습니다.")
                st.rerun()

# -------- TAB 2: 리스트/선택 & 프로필 수정/삭제 --------
with TAB2:
    st.subheader("1-2. 리스트/선택/프로필")
    clients = load_clients()

    if clients:
        rows = [{
            "id": c.get("id"),
            "name": f"{c.get('first','')} {c.get('last','')}",
            "email": c.get("email",""),
            "phone": c.get("phone",""),
            "home_address": c.get("home_address",""),
        } for c in clients]

        search_q = st.text_input("검색 (name / email / phone / address)", key="client_search", placeholder="e.g., chris, 224-829, deerfield, gmail")
        def norm_phone(p): return re.sub(r"\D","",p or "")
        filtered = rows
        if search_q:
            terms = [t.strip().lower() for t in search_q.split() if t.strip()]
            def match(r):
                hay = " ".join([r["name"], r["email"], r["phone"], r["home_address"]]).lower()
                digits = norm_phone(r["phone"])
                def ok(t):
                    if re.sub(r"\D","",t):
                        return re.sub(r"\D","",t) in digits or t in hay
                    return t in hay
                return all(ok(t) for t in terms)
            filtered = [r for r in rows if match(r)]

        if not filtered: st.warning("검색 결과가 없습니다.")
        st.dataframe(pd.DataFrame(filtered), use_container_width=True, hide_index=True)

        labels = [f"{r['name']} ({r['email']})" for r in filtered]
        ids    = [r["id"] for r in filtered]
        idx = 0
        if st.session_state.selected_client_id in ids:
            idx = ids.index(st.session_state.selected_client_id)
        sel_label = st.selectbox("클라이언트 선택", options=labels, index=idx if labels else 0)
        sel_id = ids[labels.index(sel_label)] if labels else None
        if sel_id != st.session_state.selected_client_id:
            clear_transient_inputs(st.session_state.selected_client_id)
            st.session_state.selected_client_id = sel_id
            st.session_state._edit_loaded_id = None
            st.rerun()

        if st.session_state.selected_client_id:
            client = get_client(load_clients(), st.session_state.selected_client_id)
            if client:
                st.markdown("---")
                c1,c2 = st.columns([2,2])
                with c1:
                    st.markdown(f"**{client.get('first','')} {client.get('last','')}**")
                    st.write(client.get("email","")); st.write(client.get("phone",""))
                with c2:
                    st.write(client.get("home_address","")); st.caption(client.get("notes",""))

            if client:
                if st.session_state._edit_loaded_id != client["id"]:
                    st.session_state.edit_first  = client.get("first","")
                    st.session_state.edit_last   = client.get("last","")
                    st.session_state.edit_email  = client.get("email","")
                    st.session_state.edit_phone  = client.get("phone","")
                    st.session_state.edit_street = client.get("address_street","")
                    st.session_state.edit_apt    = client.get("address_apt","")
                    st.session_state.edit_city   = client.get("address_city","")
                    st.session_state.edit_state  = client.get("address_state","")
                    st.session_state.edit_zip    = client.get("address_zip","")
                    st.session_state.edit_notes  = client.get("notes","")
                    st.session_state._edit_loaded_id = client["id"]

                cur = st.session_state.get("edit_phone", None)
                if cur is not None: st.session_state.edit_phone = format_phone(cur)

                st.markdown("---"); st.markdown("### 프로필 수정")
                with st.form("edit_client_form"):
                    col1,col2 = st.columns(2)
                    with col1: st.text_input("First Name", key="edit_first")
                    with col2: st.text_input("Last Name", key="edit_last")
                    col1,col2 = st.columns(2)
                    with col1: st.text_input("Phone (10 digits)", key="edit_phone")
                    with col2: st.text_input("Email", key="edit_email")
                    st.markdown("**Home Address**")
                    col1,col2 = st.columns([2,1])
                    with col1:
                        st.text_input("Street Address", key="edit_street")
                        st.text_input("Ste (Apt/Unit) — Optional", key="edit_apt")
                    with col2:
                        st.text_input("City", key="edit_city")
                        st.text_input("State (2 letters)", key="edit_state")
                        st.text_input("Zip (12345 or 12345-6789)", key="edit_zip")
                    st.text_area("Notes", key="edit_notes")

                    csave, cdel = st.columns([1,1])
                    with csave: save_clicked = st.form_submit_button("수정 내용 저장")
                    with cdel:  del_clicked  = st.form_submit_button("선택 클라이언트 삭제", help="선택한 클라이언트와 해당 재무 데이터를 모두 삭제합니다 (되돌릴 수 없음)")

                    if save_clicked:
                        errs=[]
                        if not st.session_state.edit_first.strip(): errs.append("First Name을 입력하세요.")
                        if not st.session_state.edit_last.strip(): errs.append("Last Name을 입력하세요.")
                        if not validate_email(st.session_state.edit_email): errs.append("Email 형식이 올바르지 않습니다.")
                        if not validate_phone10(st.session_state.edit_phone): errs.append("Phone Number는 정확히 10자리여야 합니다.")
                        if not st.session_state.edit_street.strip(): errs.append("Street Address를 입력하세요.")
                        if not st.session_state.edit_city.strip(): errs.append("City를 입력하세요.")
                        if not validate_state(st.session_state.edit_state): errs.append("State는 2글자여야 합니다.")
                        if not validate_zip(st.session_state.edit_zip): errs.append("Zip은 12345 또는 12345-6789 형식이어야 합니다.")
                        if errs:
                            st.markdown("<div style='color:#c1121f;font-size:0.9rem;'>"+ "<br>".join([f"• {e}" for e in errs]) +"</div>", unsafe_allow_html=True)
                        else:
                            cs = load_clients()
                            c = get_client(cs, client["id"]) or {}
                            c["first"] = st.session_state.edit_first.strip()
                            c["last"]  = st.session_state.edit_last.strip()
                            c["email"] = st.session_state.edit_email.strip()
                            c["phone"] = format_phone(st.session_state.edit_phone)
                            c["address_street"] = st.session_state.edit_street.strip()
                            c["address_apt"]    = st.session_state.edit_apt.strip()
                            c["address_city"]   = st.session_state.edit_city.strip()
                            c["address_state"]  = st.session_state.edit_state.strip().upper()
                            c["address_zip"]    = st.session_state.edit_zip.strip()
                            c["home_address"]   = build_home_address(
                                c["address_street"], c["address_apt"], c["address_city"], c["address_state"], c["address_zip"]
                            )
                            c["notes"] = st.session_state.edit_notes.strip()
                            save_clients(cs)
                            st.success("저장되었습니다."); st.rerun()

                    if del_clicked:
                        st.warning("삭제는 되돌릴 수 없습니다. 하단 체크 후 최종 삭제를 눌러주세요.")
                        if st.checkbox("정말 삭제합니다.") and st.button("최종 삭제", type="primary"):
                            delete_client_and_data(client["id"])
                            st.session_state.selected_client_id = None
                            st.success("삭제되었습니다."); st.rerun()
    else:
        st.info("등록된 클라이언트가 없습니다. ‘신규 등록’ 탭에서 먼저 등록하세요.")

# -------- TAB 3: 재무 입력 (CRUD 완성) --------
with TAB3:
    st.subheader("2) 재무 입력 (클라이언트별 저장)")
    sel_id = st.session_state.selected_client_id
    if not sel_id:
        st.info("클라이언트를 먼저 선택하세요 (리스트/선택 탭).")
    else:
        finance = load_client_finance(sel_id)

        def human_label(section_key: str, item: dict, idx: int) -> str:
            if section_key in ("income_details","expense_details"):
                return f"[{idx}] {item.get('category','')} / {item.get('desc','')} / ${item.get('amount',0):,.2f}"
            else:
                return f"[{idx}] {item.get('category','')} / ${item.get('amount',0):,.2f}"

        def render_section(section_key: str, has_desc: bool):
            items = finance.get(section_key, [])
            cols = ["category","desc","amount"] if has_desc else ["category","amount"]
            if items:
                st.dataframe(pd.DataFrame(items)[cols], use_container_width=True, hide_index=True)
            else:
                st.caption("(아직 항목이 없습니다)")

            # ---- Add
            with st.form(f"add_{section_key}", clear_on_submit=True):
                c1,c2,c3 = (st.columns([1,2,1]) if has_desc else st.columns([2,1]))
                if has_desc:
                    with c1: new_cat = st.text_input("Category", key=f"{section_key}_category_{sel_id}")
                    with c2: new_desc = st.text_input("Description", key=f"{section_key}_desc_{sel_id}")
                    with c3: new_amt = st.number_input("Amount", min_value=0.0, step=100.0, key=f"{section_key}_amount_{sel_id}")
                else:
                    with c1: new_cat = st.text_input("Category", key=f"{section_key}_category_{sel_id}")
                    with c2: new_amt = st.number_input("Amount", min_value=0.0, step=100.0, key=f"{section_key}_amount_{sel_id}")
                    new_desc = ""
                if st.form_submit_button("추가"):
                    errs=[]
                    if not (new_cat or "").strip(): errs.append("Category를 입력하세요.")
                    try:
                        amt = float(new_amt)
                        if amt < 0: errs.append("Amount는 0 이상이어야 합니다.")
                    except Exception:
                        errs.append("Amount가 올바르지 않습니다.")
                    if errs:
                        st.markdown("<div style='color:#c1121f;font-size:0.9rem;'>"+ "<br>".join([f"• {e}" for e in errs]) +"</div>", unsafe_allow_html=True)
                    else:
                        rec = {"category": new_cat.strip(), "amount": float(new_amt)}
                        if has_desc: rec["desc"] = (new_desc or "").strip()
                        finance[section_key].append(rec)
                        save_client_finance(sel_id, finance)
                        for k in [f"{section_key}_category_{sel_id}", f"{section_key}_desc_{sel_id}", f"{section_key}_amount_{sel_id}"]:
                            st.session_state.pop(k, None)
                        st.success("추가되었습니다."); st.rerun()

            # ---- Edit / Delete
            with st.expander("편집 / 삭제", expanded=False):
                if not items:
                    st.caption("편집/삭제할 항목이 없습니다.")
                else:
                    label_list = [human_label(section_key, it, i) for i,it in enumerate(items)]
                    sel_key = f"editrow_select_{section_key}_{sel_id}"
                    row_label = st.selectbox("항목 선택", options=label_list, key=sel_key)
                    row_idx = label_list.index(row_label)

                    # Edit form
                    with st.form(f"edit_{section_key}", clear_on_submit=True):
                        c1,c2,c3 = (st.columns([1,2,1]) if has_desc else st.columns([2,1]))
                        if has_desc:
                            with c1: e_cat = st.text_input("Category", value=items[row_idx].get("category",""))
                            with c2: e_desc = st.text_input("Description", value=items[row_idx].get("desc",""))
                            with c3: e_amt = st.number_input("Amount", min_value=0.0, value=float(items[row_idx].get("amount",0.0)), step=100.0)
                        else:
                            with c1: e_cat = st.text_input("Category", value=items[row_idx].get("category",""))
                            with c2: e_amt = st.number_input("Amount", min_value=0.0, value=float(items[row_idx].get("amount",0.0)), step=100.0)
                            e_desc = ""
                        c_a, c_b = st.columns([1,1])
                        with c_a: edit_ok = st.form_submit_button("수정 저장")
                        with c_b: del_ok  = st.form_submit_button("이 항목 삭제")

                        if edit_ok:
                            errs=[]
                            if not e_cat.strip(): errs.append("Category를 입력하세요.")
                            try:
                                if float(e_amt) < 0: errs.append("Amount는 0 이상이어야 합니다.")
                            except Exception:
                                errs.append("Amount가 올바르지 않습니다.")
                            if errs:
                                st.markdown("<div style='color:#c1121f;font-size:0.9rem;'>"+ "<br>".join([f"• {e}" for e in errs]) +"</div>", unsafe_allow_html=True)
                            else:
                                finance[section_key][row_idx]["category"] = e_cat.strip()
                                finance[section_key][row_idx]["amount"]   = float(e_amt)
                                if has_desc:
                                    finance[section_key][row_idx]["desc"] = (e_desc or "").strip()
                                save_client_finance(sel_id, finance)
                                st.success("수정되었습니다."); st.rerun()

                        if del_ok:
                            finance[section_key].pop(row_idx)
                            save_client_finance(sel_id, finance)
                            st.success("삭제되었습니다."); st.rerun()

        inc, exp, ast, lia, summ = st.tabs(["Income","Expense","Assets","Liabilities","Summary"])
        with inc: render_section("income_details", has_desc=True)
        with exp: render_section("expense_details", has_desc=True)
        with ast: render_section("assets", has_desc=False)
        with lia: render_section("liabilities", has_desc=False)
        with summ:
            st.markdown("**Etc 설정**")
            etc_val = float(finance.get("summary", {}).get("etc", 0.0))
            etc_key = f"summary_etc_{sel_id}"
            new_etc = st.number_input("Etc", min_value=0.0, value=float(etc_val), step=100.0, key=etc_key)
            if st.button("Etc 저장"):
                finance.setdefault("summary", {})["etc"] = float(new_etc)
                save_client_finance(sel_id, finance)
                st.session_state.pop(etc_key, None)
                st.success("저장되었습니다."); st.rerun()

            income_sum = float(sum(x.get("amount", 0.0) for x in finance.get("income_details", [])))
            expense_sum = float(sum(x.get("amount", 0.0) for x in finance.get("expense_details", [])))
            remaining = max(income_sum - expense_sum, 0.0)
            etc_val = float(finance.get("summary", {}).get("etc", 0.0))
            st.markdown("---")
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Income", f"${income_sum:,.2f}")
            c2.metric("Expense", f"${expense_sum:,.2f}")
            c3.metric("Remaining", f"${remaining:,.2f}")
            c4.metric("Etc", f"${etc_val:,.2f}")

# -------- TAB 4: 시각화 --------
with TAB4:
    st.subheader("3) 시각화 (파이 그래프)")
    sel_id = st.session_state.selected_client_id
    if not sel_id:
        st.info("클라이언트를 먼저 선택하세요 (리스트/선택 탭).")
    else:
        finance = load_client_finance(sel_id)

        st.sidebar.markdown("### 그래프 설정")
        pie_size = st.sidebar.slider("파이 크기 (inches)", 4, 12, 6)
        title_fs = st.sidebar.slider("제목 글씨 크기", 12, 32, 18)
        pct_fs   = st.sidebar.slider("퍼센트 글씨 크기", 8, 18, 12)
        pct_dist = st.sidebar.slider("퍼센트 위치 (중심→가장자리)", 0.4, 1.2, 0.7)

        def draw_pie(values: list[float], labels_for_legend: list[str], title: str):
            vals, leg = zip(*[(v,l) for v,l in zip(values, labels_for_legend) if v > 0]) if any(values) else ([],[])
            fig, ax = plt.subplots(figsize=(pie_size, pie_size))
            if sum(vals) > 0:
                wedges, texts, autotexts = ax.pie(
                    vals, labels=None,
                    autopct=lambda p: f"{p:.1f}%" if p > 0 else "",
                    pctdistance=pct_dist, startangle=90,
                )
                plt.setp(autotexts, size=pct_fs)
                ax.axis("equal"); ax.set_title(title, fontsize=title_fs)
                c1,c2 = st.columns([2,1])
                with c1: st.pyplot(fig, use_container_width=True)
                with c2:
                    st.markdown("**범례**")
                    for l, v in sorted(zip(leg, vals), key=lambda x: x[1], reverse=True):
                        st.write(f"• {l}: ${v:,.2f}")
            else:
                ax.set_title(title, fontsize=title_fs)
                st.pyplot(fig, use_container_width=True)

        income_sum = float(sum(x.get("amount", 0.0) for x in finance.get("income_details", [])))
        expense_sum = float(sum(x.get("amount", 0.0) for x in finance.get("expense_details", [])))
        remaining = max(income_sum - expense_sum, 0.0)
        etc_val = float(finance.get("summary", {}).get("etc", 0.0))
        draw_pie([income_sum, expense_sum, remaining, etc_val], ["Income","Expense","Remaining","Etc"], "Income / Expense Mix")

        st.markdown("---")
        assets = finance.get("assets", [])
        if assets:
            df = pd.DataFrame(assets); g = df.groupby("category", dropna=False)["amount"].sum().reset_index()
            draw_pie(g["amount"].tolist(), g["category"].astype(str).tolist(), "Assets by Category")
        else:
            st.info("자산 항목이 없습니다.")

        st.markdown("---")
        liabs = finance.get("liabilities", [])
        if liabs:
            df = pd.DataFrame(liabs); g = df.groupby("category", dropna=False)["amount"].sum().reset_index()
            draw_pie(g["amount"].tolist(), g["category"].astype(str).tolist(), "Liabilities by Category")
        else:
            st.info("부채 항목이 없습니다.")

# =====================
# Footer
# =====================
st.caption("Demo storage: JSON files (clients.json, data/client_{id}.json). Future: SQLite.")
