import streamlit as st
import json
from pathlib import Path
from datetime import datetime, date, timezone
import uuid
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import io
import os
import tempfile
import shutil

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

def today_iso_date() -> str:
    return date.today().isoformat()  # YYYY-MM-DD

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

# ---- date helpers ----
def coerce_date_col(df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
    """Ensure df[col] is dtype datetime.date (or NaN)."""
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    return df

def to_iso_date(val) -> str:
    """Value from editor -> ISO date string."""
    if isinstance(val, date):
        return val.isoformat()
    try:
        return pd.to_datetime(val).date().isoformat()
    except Exception:
        return today_iso_date()

# =====================
# Robust file I/O
# =====================
def atomic_write(path: Path, text: str) -> None:
    try:
        if path.exists():
            bak = path.with_suffix(path.suffix + ".bak")
            try:
                shutil.copy2(path, bak)
            except Exception:
                pass
        with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding="utf-8") as tmp:
            tmp.write(text)
            tmp_path = Path(tmp.name)
        os.replace(str(tmp_path), str(path))
    except Exception as e:
        st.error(f"파일 저장 중 오류: {e}")

# =====================
# Persistence helpers
# =====================
def load_clients() -> list:
    try:
        return json.loads(CLIENTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_clients(clients: list) -> None:
    atomic_write(CLIENTS_FILE, json.dumps(clients, ensure_ascii=False, indent=2))

def get_client(clients: list, client_id: str) -> dict | None:
    for c in clients:
        if c.get("id") == client_id:
            return c
    return None

def client_data_path(client_id: str) -> Path:
    return DATA_DIR / f"client_{client_id}.json"

def _empty_finance() -> dict:
    # 각 행에 선택적 "date": "YYYY-MM-DD" 허용
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
        atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2))
        return data
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        base = _empty_finance()
        for k in base:
            raw.setdefault(k, base[k])
        raw["summary"].setdefault("etc", 0.0)
        return raw
    except Exception:
        return _empty_finance()

def save_client_finance(client_id: str, data: dict) -> None:
    p = client_data_path(client_id)
    atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2))

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
# Duplicate detection
# =====================
def find_duplicates(clients: list, email: str, phone: str, exclude_id: str | None = None) -> list:
    email_norm = (email or "").strip().lower()
    phone_norm = only_digits(phone or "")
    dups = []
    for c in clients:
        if exclude_id and c.get("id") == exclude_id:
            continue
        if (c.get("email","").strip().lower() == email_norm) or (only_digits(c.get("phone","")) == phone_norm):
            dups.append({"id": c.get("id"), "name": f"{c.get('first','')} {c.get('last','')}",
                         "email": c.get("email",""), "phone": c.get("phone",""),
                         "archived": bool(c.get("archived", False))})
    return dups

# =====================
# Session defaults & helpers
# =====================
if "selected_client_id" not in st.session_state:
    st.session_state.selected_client_id = None
if "_edit_loaded_id" not in st.session_state:
    st.session_state._edit_loaded_id = None
if "autosave" not in st.session_state:
    st.session_state.autosave = False  # 자동 저장 토글

# registration form state
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
            key.startswith("income_editor_")
            or key.startswith("expense_editor_")
            or key.startswith("assets_editor_")
            or key.startswith("liabilities_editor_")
            or key.startswith("summary_etc_")
            or key.endswith(f"_working_{client_id}")
            or key.startswith("income_quick_")
            or key.startswith("expense_quick_")
            or key.startswith("assets_quick_")
            or key.startswith("liabilities_quick_")
            or key.endswith("_presel_"+str(client_id))
        ):
            st.session_state.pop(key, None)

# =====================
# Sidebar: global toggles
# =====================
st.sidebar.markdown("### ⚙️ 설정")
st.sidebar.checkbox("자동 저장 (표 편집 즉시 저장)", key="autosave")
st.sidebar.caption("오류가 있으면 자동 저장이 보류되고 경고가 표시됩니다.")

# =====================
# Top summary (all-time)
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
        allow_dup = st.checkbox("중복 무시하고 등록", value=False)

        submitted = st.form_submit_button("등록")
        if submitted:
            errs=[]
            if not st.session_state.reg_first.strip(): errs.append("First Name을 입력하세요.")
            if not st.session_state.reg_last.strip(): errs.append("Last Name을 입력하세요.")
            if not validate_email(st.session_state.reg_email): errs.append("Email 형식이 올바르지 않습니다.")
            if not validate_phone10(st.session_state.reg_phone): errs.append("Phone Number는 정확히 10자리여야 합니다.")
            if not st.session_state.reg_street.strip(): errs.append("Street Address를 입력하세요.")
            if not st.session_state.reg_city.strip(): errs.append("City를 입력하세요.")
            if not validate_state(st.session_state.reg_state): errs.append("State는 2글자여야 합니다.")
            if not validate_zip(st.session_state.reg_zip): errs.append("Zip은 12345 또는 12345-6789 형식이어야 합니다.")

            clients_local = load_clients()
            dups = find_duplicates(clients_local, st.session_state.reg_email, st.session_state.reg_phone)
            if dups and not allow_dup:
                errs.append("이미 동일 Email 또는 Phone을 가진 클라이언트가 존재합니다. (아래 표 참고)")

            if errs:
                st.markdown("<div style='color:#c1121f;font-size:0.9rem;'>"+ "<br>".join([f"• {e}" for e in errs]) +"</div>", unsafe_allow_html=True)
                if dups:
                    st.dataframe(pd.DataFrame(dups), use_container_width=True, hide_index=True)
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
                    "archived": False,
                }
                clients_local.append(new_client)
                save_clients(clients_local)
                st.success("등록되었습니다.")
                st.rerun()

# -------- TAB 2: 리스트/선택 & 프로필 수정/삭제 + 내보내기 + 아카이브 --------
with TAB2:
    st.subheader("1-2. 리스트/선택/프로필")
    clients = load_clients()

    if clients:
        include_archived = st.checkbox("아카이브 포함해서 보기", value=False, key="include_archived")

        base_rows = [{
            "id": c.get("id"),
            "name": f"{c.get('first','')} {c.get('last','')}",
            "email": c.get("email",""),
            "phone": c.get("phone",""),
            "home_address": c.get("home_address",""),
            "archived": bool(c.get("archived", False)),
        } for c in clients]

        rows = [r for r in base_rows if include_archived or (not r["archived"])]

        search_q = st.text_input("검색 (name / email / phone / address)", key="client_search", placeholder="e.g., chris, 224-829, deerfield, gmail")
        def norm_phone(p): return re.sub(r"\D","",p or "")
        filtered = rows
        if search_q:
            terms = [t.strip().lower() for t in search_q.split() if t.strip()]
            def match(r):
                hay = " ".join([r["name"], r["email"], r["phone"], r["home_address"]]).lower()
                digits = norm_phone(r["phone"])
                def ok(t):
                    if re.sub(r"\D","",t): return re.sub(r"\D","",t) in digits or t in hay
                    return t in hay
                return all(ok(t) for t in terms)
            filtered = [r for r in rows if match(r)]

        if not filtered: st.warning("검색 결과가 없습니다.")
        st.dataframe(pd.DataFrame(filtered), use_container_width=True, hide_index=True)

        labels = [f"{'(A) ' if r['archived'] else ''}{r['name']} ({r['email']})" for r in filtered]
        ids    = [r["id"] for r in filtered]
        idx=0
        if st.session_state.selected_client_id in ids: idx = ids.index(st.session_state.selected_client_id)
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
                    st.markdown(f"**{client.get('first','')} {client.get('last','')}** {'(Archived)' if client.get('archived') else ''}")
                    st.write(client.get("email","")); st.write(client.get("phone",""))
                with c2:
                    st.write(client.get("home_address","")); st.caption(client.get("notes",""))

                # Archive / Unarchive toggle
                arch_col1, arch_col2 = st.columns([1,3])
                with arch_col1:
                    if not client.get("archived", False):
                        if st.button("📦 아카이브", key="btn_archive"):
                            cs = load_clients()
                            c = get_client(cs, client["id"])
                            if c:
                                c["archived"] = True
                                save_clients(cs)
                                st.success("아카이브로 이동했습니다.")
                                st.session_state.selected_client_id = None
                                st.rerun()
                    else:
                        if st.button("♻️ 아카이브 해제", key="btn_unarchive"):
                            cs = load_clients()
                            c = get_client(cs, client["id"])
                            if c:
                                c["archived"] = False
                                save_clients(cs)
                                st.success("아카이브를 해제했습니다.")
                                st.rerun()

                # ===== Export buttons =====
                expander = st.expander("📤 내보내기 (다운로드)", expanded=False)
                with expander:
                    fin = load_client_finance(client["id"])
                    json_bytes = json.dumps(fin, ensure_ascii=False, indent=2).encode("utf-8")
                    st.download_button(
                        "클라이언트 재무데이터 (JSON)",
                        data=json_bytes, file_name=f"client_{client['id']}_finance.json", mime="application/json",
                        key=f"dl_fin_json_{client['id']}"
                    )

                    def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
                        buf = io.StringIO()
                        df.to_csv(buf, index=False)
                        return buf.getvalue().encode("utf-8")

                    for sec, cols, title in [
                        ("income_details", ["category","desc","amount","date"], "Income"),
                        ("expense_details", ["category","desc","amount","date"], "Expense"),
                        ("assets", ["category","amount","date"], "Assets"),
                        ("liabilities", ["category","amount","date"], "Liabilities"),
                    ]:
                        sec_rows = fin.get(sec, [])
                        sec_df = pd.DataFrame(sec_rows, columns=cols)
                        st.download_button(
                            f"{title} (CSV)",
                            data=df_to_csv_bytes(sec_df),
                            file_name=f"client_{client['id']}_{sec}.csv",
                            mime="text/csv",
                            key=f"dl_{sec}_{client['id']}"
                        )

            # ===== Edit / Delete =====
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

                    allow_dup_edit = st.checkbox("중복 무시하고 저장", value=False)

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

                        cs = load_clients()
                        dup_list = find_duplicates(cs, st.session_state.edit_email, st.session_state.edit_phone, exclude_id=client["id"])
                        if dup_list and not allow_dup_edit:
                            errs.append("이미 동일 Email 또는 Phone을 가진 클라이언트가 존재합니다. (아래 표 참고)")

                        if errs:
                            st.markdown("<div style='color:#c1121f;font-size:0.9rem;'>"+ "<br>".join([f"• {e}" for e in errs]) +"</div>", unsafe_allow_html=True)
                            if dup_list:
                                st.dataframe(pd.DataFrame(dup_list), use_container_width=True, hide_index=True)
                        else:
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

        # 전체 클라이언트 CSV 다운로드
        st.markdown("---")
        df_all = pd.DataFrame(load_clients())
        if not df_all.empty:
            buf = io.StringIO(); df_all.to_csv(buf, index=False)
            st.download_button("📥 전체 클라이언트 목록 (CSV)", data=buf.getvalue().encode("utf-8"),
                               file_name="clients.csv", mime="text/csv")

    else:
        st.info("등록된 클라이언트가 없습니다. ‘신규 등록’ 탭에서 먼저 등록하세요.")

# -------- TAB 3: 재무 입력 (표 직접 편집 + 편의 기능 + 자동 저장) --------
with TAB3:
    st.subheader("2) 재무 입력 (클라이언트별 저장)")
    sel_id = st.session_state.selected_client_id
    if not sel_id:
        st.info("클라이언트를 먼저 선택하세요 (리스트/선택 탭).")
    else:
        finance = load_client_finance(sel_id)

        # 프리셋
        PRESETS = {
            "income_details": ["Salary","Bonus","Interest","Dividend","Rental","Side Hustle","Other"],
            "expense_details": ["Rent","Mortgage","Utilities","Groceries","Dining","Transport","Insurance","Medical",
                                "Education","Childcare","Entertainment","Travel","Debt Payment","Taxes","Misc"],
            "assets": ["Cash","Checking","Savings","Brokerage","Retirement","Real Estate","Vehicle","Crypto","Other"],
            "liabilities": ["Credit Card","Mortgage","Student Loan","Auto Loan","Personal Loan","Tax Owed","Other"],
        }

        def _df_from_rows(section_key: str, rows: list) -> pd.DataFrame:
            if section_key in ("income_details","expense_details"):
                df = pd.DataFrame(rows, columns=["category","desc","amount","date"])
            else:
                df = pd.DataFrame(rows, columns=["category","amount","date"])
            return coerce_date_col(df, "date")

        def _empty_row(section_key: str) -> dict:
            if section_key in ("income_details","expense_details"):
                return {"category":"", "desc":"", "amount":0.0, "date": date.today()}
            return {"category":"", "amount":0.0, "date": date.today()}

        def get_working_df(section_key: str) -> pd.DataFrame:
            sskey = f"{section_key}_working_{sel_id}"
            if sskey not in st.session_state:
                st.session_state[sskey] = _df_from_rows(section_key, finance.get(section_key, []))
            df = st.session_state[sskey]
            need_cols = ["category","amount","date"] if section_key not in ("income_details","expense_details") else ["category","desc","amount","date"]
            for c in need_cols:
                if c not in df.columns:
                    if c == "date":
                        df[c] = date.today()
                    elif c == "amount":
                        df[c] = 0.0
                    else:
                        df[c] = ""
            df = df[need_cols]
            df = coerce_date_col(df, "date")
            st.session_state[sskey] = df
            return st.session_state[sskey]

        def set_working_df(section_key: str, df: pd.DataFrame):
            sskey = f"{section_key}_working_{sel_id}"
            st.session_state[sskey] = coerce_date_col(df.copy(), "date")

        def _clean_and_validate_df(title: str, edited: pd.DataFrame, has_desc: bool):
            errs = []
            clean_rows = []
            if isinstance(edited, pd.Series):
                edited = edited.to_frame().T
            fillmap = {"category": "", "date": date.today()}
            if has_desc:
                fillmap["desc"] = ""
            ed = edited.fillna(fillmap)
            ed = coerce_date_col(ed, "date")
            for i, r in ed.iterrows():
                cat = str(r.get("category", "")).strip()
                if cat == "":
                    continue
                # amount
                try:
                    amt = float(r.get("amount", 0))
                    if amt < 0:
                        errs.append(f"{title} 행 {i}: Amount는 0 이상이어야 합니다.")
                        continue
                except Exception:
                    errs.append(f"{title} 행 {i}: Amount가 올바르지 않습니다.")
                    continue
                # date -> ISO string
                d_str = to_iso_date(r.get("date"))

                row = {"category": cat, "amount": amt, "date": d_str}
                if has_desc:
                    row["desc"] = str(r.get("desc", "")).strip()
                clean_rows.append(row)
            return clean_rows, errs

        def _rows_equal(a: list, b: list) -> bool:
            return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

        def editor_section(title: str, section_key: str, has_desc: bool, key_prefix: str):
            st.markdown(f"### {title}")

            lcol, rcol = st.columns([1, 3])

            with lcol:
                st.caption("프리셋 추가")
                presets = PRESETS.get(section_key, [])
                preset_sel = st.multiselect("카테고리", presets, key=f"{key_prefix}_presel_{sel_id}")
                if st.button("프리셋 행 추가", key=f"{key_prefix}_addpreset_{sel_id}"):
                    df = get_working_df(section_key)
                    for p in preset_sel:
                        row = _empty_row(section_key); row["category"] = p
                        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
                    set_working_df(section_key, df)
                    st.success("프리셋을 추가했습니다."); st.rerun()

                st.divider()
                st.caption("빠른 입력")
                q_cat = st.selectbox("Category", options=[""] + PRESETS.get(section_key, []), key=f"{key_prefix}_quick_cat_{sel_id}")
                q_desc = st.text_input("Description", key=f"{key_prefix}_quick_desc_{sel_id}") if has_desc else ""
                q_amt = st.number_input("Amount", min_value=0.0, step=100.0, key=f"{key_prefix}_quick_amt_{sel_id}")
                q_date = st.date_input("Date", value=date.today(), key=f"{key_prefix}_quick_date_{sel_id}")
                if st.button("➕ 한 행 추가", key=f"{key_prefix}_quick_add_{sel_id}"):
                    if (q_cat or "").strip() == "":
                        st.warning("Category를 선택하세요.")
                    else:
                        df = get_working_df(section_key)
                        row = {"category": q_cat.strip(), "amount": float(q_amt), "date": q_date}
                        if has_desc: row["desc"] = (q_desc or "").strip()
                        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
                        set_working_df(section_key, df)
                        # 안전 초기화: 직접 대입 대신 pop으로 비우기
                        st.session_state.pop(f"{key_prefix}_quick_cat_{sel_id}", None)
                        if has_desc:
                            st.session_state.pop(f"{key_prefix}_quick_desc_{sel_id}", None)
                        st.session_state.pop(f"{key_prefix}_quick_amt_{sel_id}", None)
                        st.session_state.pop(f"{key_prefix}_quick_date_{sel_id}", None)
                        st.success("추가되었습니다."); st.rerun()

                st.divider()
                st.caption("기타")
                if st.button("빈 행 5개 추가", key=f"{key_prefix}_addblank_{sel_id}"):
                    df = get_working_df(section_key)
                    blanks = pd.DataFrame([_empty_row(section_key) for _ in range(5)])
                    df = pd.concat([df, blanks], ignore_index=True)
                    set_working_df(section_key, df); st.success("빈 행을 추가했습니다."); st.rerun()

                df_current = get_working_df(section_key)
                if len(df_current) > 0:
                    dup_idx = st.number_input("복제할 행 index", min_value=0, max_value=max(0, len(df_current)-1), value=0, step=1, key=f"{key_prefix}_dupidx_{sel_id}")
                    if st.button("선택 행 복제", key=f"{key_prefix}_duprow_{sel_id}"):
                        df = get_working_df(section_key)
                        row = df.iloc[int(dup_idx)].to_dict()
                        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
                        set_working_df(section_key, df); st.success("복제했습니다."); st.rerun()

                if st.button("원본으로 되돌리기", key=f"{key_prefix}_reset_{sel_id}"):
                    set_working_df(section_key, _df_from_rows(section_key, finance.get(section_key, [])))
                    st.info("저장 전 상태로 되돌렸습니다."); st.rerun()

            with rcol:
                df = get_working_df(section_key)

                col_cfg = {
                    "category": st.column_config.TextColumn("Category", required=True, help="필수"),
                    "amount": st.column_config.NumberColumn("Amount", min_value=0.0, step=100.0, format="%.2f"),
                    "date": st.column_config.DateColumn("Date"),
                }
                if has_desc:
                    col_cfg["desc"] = st.column_config.TextColumn("Description")

                edited = st.data_editor(
                    df,
                    key=f"{key_prefix}_editor_{sel_id}",
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=False,
                    column_config=col_cfg,
                )

                if isinstance(edited, pd.Series):
                    edited = edited.to_frame().T
                set_working_df(section_key, edited)

                # 섹션 합계
                try:
                    sec_sum = float(pd.to_numeric(edited["amount"], errors="coerce").fillna(0).sum())
                except Exception:
                    sec_sum = 0.0
                st.caption(f"섹션 합계: ${sec_sum:,.2f}")

                # ====== 자동 저장 처리 ======
                if st.session_state.autosave:
                    clean_rows, errs = _clean_and_validate_df(title, edited, has_desc)
                    if not errs and not _rows_equal(clean_rows, finance.get(section_key, [])):
                        finance[section_key] = clean_rows
                        save_client_finance(sel_id, finance)
                        set_working_df(section_key, _df_from_rows(section_key, clean_rows))
                        st.success("자동 저장 완료")
                    elif errs:
                        st.warning("자동 저장 보류: " + "; ".join(errs))

                # 수동 저장 버튼
                if st.button("변경 사항 저장", key=f"{key_prefix}_save_{sel_id}"):
                    clean_rows, errs = _clean_and_validate_df(title, edited, has_desc)
                    if errs:
                        st.markdown("<div style='color:#c1121f;font-size:0.9rem;'>" + "<br>".join([f"• {e}" for e in errs]) + "</div>", unsafe_allow_html=True)
                    else:
                        finance[section_key] = clean_rows
                        save_client_finance(sel_id, finance)
                        set_working_df(section_key, _df_from_rows(section_key, clean_rows))
                        st.success("저장되었습니다."); st.rerun()

            st.markdown("---")

        # 섹션별 에디터
        editor_section("Income", "income_details", has_desc=True,  key_prefix="income")
        editor_section("Expense", "expense_details", has_desc=True, key_prefix="expense")
        editor_section("Assets",  "assets",          has_desc=False, key_prefix="assets")
        editor_section("Liabilities", "liabilities", has_desc=False, key_prefix="liabilities")

        # Summary (Etc)
        st.markdown("### Summary")
        etc_val = float(finance.get("summary", {}).get("etc", 0.0))
        etc_key = f"summary_etc_{sel_id}"
        new_etc = st.number_input("Etc", min_value=0.0, value=float(etc_val), step=100.0, key=etc_key)
        if st.button("Etc 저장"):
            finance.setdefault("summary", {})["etc"] = float(new_etc)
            save_client_finance(sel_id, finance)
            st.session_state.pop(etc_key, None)
            st.success("저장되었습니다."); st.rerun()

        # Quick summary (all-time)
        income_sum = float(sum(x.get("amount", 0.0) for x in finance.get("income_details", [])))
        expense_sum = float(sum(x.get("amount", 0.0) for x in finance.get("expense_details", [])))
        remaining = max(income_sum - expense_sum, 0.0)
        etc_val = float(finance.get("summary", {}).get("etc", 0.0))
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Income", f"${income_sum:,.2f}")
        c2.metric("Expense", f"${expense_sum:,.2f}")
        c3.metric("Remaining", f"${remaining:,.2f}")
        c4.metric("Etc", f"${etc_val:,.2f}")

# -------- TAB 4: 시각화 (기간 필터 적용) --------
with TAB4:
    st.subheader("4) 시각화 (파이 그래프)")
    sel_id = st.session_state.selected_client_id
    if not sel_id:
        st.info("클라이언트를 먼저 선택하세요 (리스트/선택 탭).")
    else:
        finance = load_client_finance(sel_id)

        # ===== 기간 필터 UI =====
        st.sidebar.markdown("### 그래프 설정")
        pie_size = st.sidebar.slider("파이 크기 (inches)", 4, 12, 6)
        title_fs = st.sidebar.slider("제목 글씨 크기", 12, 32, 18)
        pct_fs   = st.sidebar.slider("퍼센트 글씨 크기", 8, 18, 12)
        pct_dist = st.sidebar.slider("퍼센트 위치 (중심→가장자리)", 0.4, 1.2, 0.7)

        st.sidebar.markdown("### 기간 필터")
        period = st.sidebar.selectbox("기간", ["전체", "이번 달", "올해", "직접 범위"])
        start_date = None
        end_date = None
        if period == "이번 달":
            today = date.today()
            start_date = date(today.year, today.month, 1)
            if today.month == 12:
                end_date = date(today.year+1, 1, 1)
            else:
                end_date = date(today.year, today.month+1, 1)
        elif period == "올해":
            today = date.today()
            start_date = date(today.year, 1, 1)
            end_date = date(today.year+1, 1, 1)
        elif period == "직접 범위":
            c1, c2 = st.sidebar.columns(2)
            with c1:
                start_date = st.sidebar.date_input("시작일", value=date.today().replace(month=1, day=1))
            with c2:
                end_date = st.sidebar.date_input("종료일(포함)", value=date.today())
                end_date = end_date + pd.Timedelta(days=1)

        def filter_rows(rows: list) -> list:
            if period == "전체":
                return rows
            filtered = []
            for r in rows:
                d = r.get("date")
                if not d:
                    continue
                try:
                    dt = pd.to_datetime(d).date()
                except Exception:
                    continue
                if start_date and end_date:
                    if start_date <= dt < end_date:
                        filtered.append(r)
            return filtered

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

        # 1) Income/Expense Mix (기간 필터 적용)
        inc_rows = filter_rows(finance.get("income_details", []))
        exp_rows = filter_rows(finance.get("expense_details", []))
        income_sum = float(sum(x.get("amount", 0.0) for x in inc_rows))
        expense_sum = float(sum(x.get("amount", 0.0) for x in exp_rows))
        remaining = max(income_sum - expense_sum, 0.0)
        etc_val = float(finance.get("summary", {}).get("etc", 0.0))  # Etc는 기간 필터 미적용
        draw_pie([income_sum, expense_sum, remaining, etc_val], ["Income","Expense","Remaining","Etc"], "Income / Expense Mix")

        st.markdown("---")

        # 2) Assets by Category
        assets = filter_rows(finance.get("assets", []))
        if assets:
            df = pd.DataFrame(assets)
            grouped = df.groupby("category", dropna=False)["amount"].sum().reset_index()
            draw_pie(grouped["amount"].tolist(), grouped["category"].astype(str).tolist(), "Assets by Category")
        else:
            st.info("자산 항목이 없습니다(선택한 기간 내).")

        st.markdown("---")

        # 3) Liabilities by Category
        liabs = filter_rows(finance.get("liabilities", []))
        if liabs:
            df = pd.DataFrame(liabs)
            grouped = df.groupby("category", dropna=False)["amount"].sum().reset_index()
            draw_pie(grouped["amount"].tolist(), grouped["category"].astype(str).tolist(), "Liabilities by Category")
        else:
            st.info("부채 항목이 없습니다(선택한 기간 내).")

# =====================
# Footer
# =====================
st.caption("Demo storage: JSON files (clients.json, data/client_{id}.json). Future: SQLite.")
