import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sqlite3
from datetime import datetime
import re

# ---------------------- 기본 설정 ----------------------
st.set_page_config(page_title="PFC App v1", layout="wide")
st.title("📊 Personal Finance Checkup (v1)")

plt.rcParams["font.family"] = ["AppleGothic","Malgun Gothic","NanumGothic","DejaVu Sans","Arial","sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

DB_PATH = "pfc.db"

DEFAULT_COLORS_SUMMARY = {"Income":"#4E79A7","Expense":"#E15759","Remaining Balance":"#59A14F","Etc":"#9AA0A6"}
DEFAULT_COLORS_ASSETS  = {"Stock":"#4E79A7","Mutual Fund":"#59A14F","Real Estate":"#F28E2B","Savings":"#76B7B2",
                          "Bond":"#EDC948","Insurance":"#B07AA1","Annuity":"#9C755F","401K":"#E15759",
                          "403B":"#FF9DA7","Etc":"#9AA0A6"}
DEFAULT_COLORS_LIAB    = {"CC Debt":"#E15759","Car Loan":"#F28E2B","Personal Loan":"#EDC948","Mortgage":"#4E79A7","Etc":"#9AA0A6"}

# ---------------------- DB ----------------------
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with get_conn() as con:
        cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS clients(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            home_address TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS client_settings(
            client_id INTEGER PRIMARY KEY,
            etc_amount REAL DEFAULT 0,
            use_income_details INTEGER DEFAULT 1,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS incomes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            category TEXT,
            description TEXT,
            amount REAL,
            ts TEXT,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            category TEXT,
            description TEXT,
            amount REAL,
            ts TEXT,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS assets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            category TEXT,
            amount REAL,
            ts TEXT,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS liabilities(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            category TEXT,
            amount REAL,
            ts TEXT,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        );
        """)
        con.commit()

def list_clients():
    with get_conn() as con:
        return pd.read_sql_query("SELECT id, name, email, phone, home_address FROM clients ORDER BY id DESC", con)

def get_client(client_id):
    with get_conn() as con:
        row = con.execute(
            "SELECT id,name,phone,email,home_address,notes FROM clients WHERE id=?",
            (client_id,)
        ).fetchone()
        return row

def insert_client(name, phone, email, home_address, notes):
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as con:
        cur = con.cursor()
        cur.execute("""INSERT INTO clients(name,phone,email,home_address,notes,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (name, phone, email, home_address, notes, now, now))
        new_id = cur.lastrowid
        cur.execute("INSERT OR IGNORE INTO client_settings(client_id, etc_amount, use_income_details) VALUES(?,?,?)",
                    (new_id, 0, 1))
        con.commit()
        return new_id

def update_client(client_id, name, phone, email, home_address, notes):
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as con:
        con.execute("""UPDATE clients
                       SET name=?, phone=?, email=?, home_address=?, notes=?, updated_at=?
                       WHERE id=?""",
                    (name, phone, email, home_address, notes, now, client_id))
        con.commit()

def delete_client(client_id):
    with get_conn() as con:
        cur = con.cursor()
        for t in ["incomes","expenses","assets","liabilities","client_settings"]:
            cur.execute(f"DELETE FROM {t} WHERE client_id=?", (client_id,))
        cur.execute("DELETE FROM clients WHERE id=?", (client_id,))
        con.commit()

def get_settings(client_id):
    with get_conn() as con:
        row = con.execute(
            "SELECT etc_amount, use_income_details FROM client_settings WHERE client_id=?",
            (client_id,)
        ).fetchone()
        return (float(row[0]), int(row[1])) if row else (0.0, 1)

def update_settings(client_id, etc_amount, use_income_details):
    with get_conn() as con:
        con.execute("""
            INSERT INTO client_settings(client_id,etc_amount,use_income_details)
            VALUES(?,?,?)
            ON CONFLICT(client_id) DO UPDATE SET etc_amount=?, use_income_details=?
        """, (client_id, etc_amount, use_income_details, etc_amount, use_income_details))
        con.commit()

def df_query(sql, client_id):
    with get_conn() as con:
        return pd.read_sql_query(sql, con, params=(client_id,))

def insert_row(table, client_id, data: dict):
    keys = ",".join(["client_id"]+list(data.keys()))
    qs   = ",".join(["?"]*(1+len(data)))
    vals = [client_id]+list(data.values())
    with get_conn() as con:
        con.execute(f"INSERT INTO {table} ({keys}) VALUES ({qs})", vals)
        con.commit()

def delete_rows(table, ids):
    if not ids: return
    with get_conn() as con:
        q = f"DELETE FROM {table} WHERE id IN ({','.join(['?']*len(ids))})"
        con.execute(q, ids)
        con.commit()

# ---------------------- 세션 ----------------------
def init_state():
    ss = st.session_state
    ss.setdefault("current_client_id", None)
    ss.setdefault("fig_size", 4.0)
    ss.setdefault("title_fs", 14)
    ss.setdefault("pct_min_fs", 7)
    ss.setdefault("pct_max_fs", 16)
    ss.setdefault("list_top_n", 12)
    ss.setdefault("pct_distance", 0.68)
    ss.setdefault("focus_next", None)
    # 신규 등록 입력 상태
    ss.setdefault("new_phone", "")
    ss.setdefault("new_email", "")
    ss.setdefault("addr_street", ""); ss.setdefault("addr_unit","")
    ss.setdefault("addr_city",""); ss.setdefault("addr_state",""); ss.setdefault("addr_zip","")
    ss.setdefault("new_first",""); ss.setdefault("new_last","")
init_state()
init_db()

# ---------------------- 유틸 ----------------------
def compute_summary(client_id):
    if not client_id:
        return pd.DataFrame({"Category":["Income","Expense","Remaining Balance","Etc"], "Amount":[0,0,0,0]})
    inc = df_query("SELECT amount FROM incomes WHERE client_id=?", client_id)["amount"].sum()
    exp = df_query("SELECT amount FROM expenses WHERE client_id=?", client_id)["amount"].sum()
    etc_amount, _use_inc = get_settings(client_id)
    remain = max(inc-exp, 0)
    return pd.DataFrame({"Category":["Income","Expense","Remaining Balance","Etc"],
                         "Amount":[inc, exp, remain, etc_amount]})

def metrics_block(df_sum):
    vals = {r["Category"]: float(r["Amount"]) for _,r in df_sum.iterrows()}
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Income", f'{vals.get("Income",0):,.2f}')
    m2.metric("Expense", f'{vals.get("Expense",0):,.2f}')
    m3.metric("Remaining", f'{vals.get("Remaining Balance",0):,.2f}')
    m4.metric("Etc", f'{vals.get("Etc",0):,.2f}')

def draw_pie_with_list(df, title, base_colors, key_tag):
    if df is None or df.empty or df["Amount"].sum()==0:
        st.info(f"'{title}'에 표시할 데이터가 없습니다."); return
    df = df.groupby("Category", as_index=False)["Amount"].sum()
    df = df[df["Amount"]>0]
    with st.sidebar.expander(f"🎨 색상 변경: {title}", expanded=False):
        color_map = {cat: st.color_picker(cat, base_colors.get(cat, "#9AA0A6"), key=f"{key_tag}_color_{cat}") for cat in df["Category"]}
    colors = [color_map[c] for c in df["Category"]]
    values = df["Amount"].to_numpy(); labels = df["Category"].tolist()
    total  = float(values.sum()); fracs = values/total; percents = fracs*100
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

def focus_field_by_label(label_text: str):
    st.components.v1.html(
        f"""
        <script>
        setTimeout(function(){{
          if (document.activeElement) {{ document.activeElement.blur(); }}
          const root = window.parent.document;
          const labels = [...root.querySelectorAll('label')];
          const target = labels.find(l => l.textContent.trim() === '{label_text}');
          if (target){{
             const wrapper = target.parentElement.parentElement;
             const input = wrapper.querySelector('input,textarea');
             if (input){{ input.focus(); input.select(); }}
          }}
        }}, 80);
        </script>
        """, height=0
    )

# ---- 입력 검사/포맷 ----
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
def is_valid_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match(email.strip())) if email else False

def format_phone_live_local(raw: str) -> str:
    # 000-000-0000 포맷 (최대 10자리)
    digits = "".join([c for c in raw if c.isdigit()])[:10]
    if len(digits) <= 3:
        return digits
    elif len(digits) <= 6:
        return f"{digits[:3]}-{digits[3:]}"
    else:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:10]}"

def compose_address(street, unit, city, state, zipc):
    parts = []
    if street: parts.append(street.strip())
    if unit: parts.append(unit.strip())
    line1 = " ".join(parts).strip()
    line2 = ", ".join([p for p in [city.strip() if city else "", state.strip() if state else ""] if p])
    zipc = zipc.strip() if zipc else ""
    full = line1
    if line2: full = f"{full}, {line2}" if full else line2
    if zipc:  full = f"{full} {zipc}" if full else zipc
    return full

def split_name(fullname: str):
    fullname = (fullname or "").strip()
    if not fullname:
        return "", ""
    parts = fullname.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])

# ---------------------- Sidebar (그래프 스타일) ----------------------
with st.sidebar:
    st.markdown("### ⚙️ 그래프 스타일")
    st.session_state["fig_size"] = st.slider("그래프 크기(인치)", 3.0, 8.0, st.session_state["fig_size"], 0.5)
    st.session_state["title_fs"] = st.slider("제목 글씨 크기", 10, 28, st.session_state["title_fs"], 1)
    c1,c2 = st.columns(2)
    with c1: st.session_state["pct_min_fs"] = st.slider("퍼센트 최소 글씨", 6, 14, st.session_state["pct_min_fs"], 1)
    with c2: st.session_state["pct_max_fs"] = st.slider("퍼센트 최대 글씨", 12, 28, st.session_state["pct_max_fs"], 1)
    st.session_state["pct_distance"] = st.slider("퍼센트 위치(중심↔테두리)", 0.55, 0.85, st.session_state["pct_distance"], 0.01)
    st.session_state["list_top_n"] = st.slider("우측 리스트 항목 수", 5, 20, st.session_state["list_top_n"], 1)

# ---------------------- Sticky Summary & 에러 스타일 ----------------------
st.markdown("""
<style>
.sticky-summary {position: sticky; top: 0; z-index: 999;
 background-color: var(--background-color); padding-top: .5rem; padding-bottom:.5rem;}
.input-error input {border: 1px solid #e74c3c !important;}
.small-error {color:#e74c3c; font-size:12px; margin-top:4px;}
</style>
""", unsafe_allow_html=True)

# ---------------------- 👥 클라이언트 관리 ----------------------
st.markdown("## 👥 클라이언트 선택 / 관리")
tab_list, tab_new = st.tabs(["리스트/선택","신규 등록"])

with tab_list:
    st.markdown("#### 등록된 클라이언트")
    clients_df = list_clients()
    if clients_df.empty:
        st.info("등록된 클라이언트가 없습니다. '신규 등록' 탭에서 추가하세요.")
        selected_id = None
    else:
        st.dataframe(clients_df, use_container_width=True, height=260)
        ids = clients_df["id"].tolist()
        labels = [f'{r["name"]} — {r["email"] or ""} ({r["phone"] or ""})' for _,r in clients_df.iterrows()]
        idx_default = 0 if st.session_state.current_client_id not in ids else ids.index(st.session_state.current_client_id)
        idx = st.selectbox("클라이언트 선택", options=list(range(len(ids))),
                           format_func=lambda i: labels[i], index=idx_default)
        selected_id = ids[idx]
        st.session_state.current_client_id = selected_id
        st.success("선택되었습니다. 아래에서 입력/수정/삭제를 진행하세요.")

    st.divider()
    st.markdown("#### 선택된 클라이언트 프로필 (수정/삭제)")
    if selected_id:
        row = get_client(selected_id)
        _, name0, phone0, email0, addr0, notes0 = row if row else (None,"","","","","")
        first0, last0 = split_name(name0)
        phone0 = format_phone_live_local(phone0 or "")

        with st.form("form_edit_client_inline"):
            n1, n2 = st.columns(2)
            with n1: first_name = st.text_input("First Name", value=first0 or "")
            with n2: last_name  = st.text_input("Last Name",  value=last0 or "")
            c1,c2 = st.columns(2)
            with c1:
                phone = st.text_input("Phone (자동 포맷)", value=phone0 or "", placeholder="000-000-0000")
                phone = format_phone_live_local(phone)
            with c2:
                email = st.text_input("Email", value=email0 or "", placeholder="name@example.com")
            home_address = st.text_input("Home address", value=addr0 or "")
            notes = st.text_area("Notes", value=notes0 or "", height=80)

            colA, colB = st.columns([1,1])
            with colA:
                full_name = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()
                save_ok = st.form_submit_button("저장/업데이트",
                                                disabled=(not full_name) or (email and not is_valid_email(email)))
            with colB:
                st.markdown("⚠️ 삭제는 되돌릴 수 없습니다.")
                confirm = st.checkbox("정말 삭제합니다.")
                del_ok = st.form_submit_button("선택 클라이언트 삭제", disabled=not confirm)

        if save_ok:
            update_client(selected_id, full_name, phone.strip(), email.strip(), home_address.strip(), notes.strip())
            st.success("프로필 저장 완료!")
            st.rerun()
        if del_ok and confirm:
            delete_client(selected_id)
            st.session_state.current_client_id = None
            st.success("클라이언트 및 관련 데이터가 모두 삭제되었습니다.")
            st.rerun()

with tab_new:
    st.markdown("#### 새 클라이언트 등록")
    st.session_state.new_phone = format_phone_live_local(st.session_state.new_phone)
    with st.form("form_new_client", clear_on_submit=False):
        n1, n2 = st.columns(2)
        with n1: first_name = st.text_input("First Name", key="new_first")
        with n2: last_name  = st.text_input("Last Name",  key="new_last")
        c1,c2 = st.columns(2)
        with c1: phone = st.text_input("Phone (자동 포맷)", key="new_phone", placeholder="000-000-0000")
        with c2: email = st.text_input("Email", key="new_email", placeholder="name@example.com")
        st.markdown("**Home address**")
        a1,a2 = st.columns([2,1])
        with a1: addr_street = st.text_input("Street Address", key="addr_street")
        with a2: addr_unit   = st.text_input("Ste#/Apt#/Unit#", key="addr_unit")
        a3,a4,a5 = st.columns([2,1,1])
        with a3: addr_city  = st.text_input("City", key="addr_city")
        with a4: addr_state = st.text_input("State", key="addr_state")
        with a5: addr_zip   = st.text_input("Zip Code", key="addr_zip")
        notes = st.text_area("Notes", key="new_notes", height=80)

        valid_email = is_valid_email(email) if email.strip() else False
        if email.strip() and not valid_email:
            st.markdown("<div class='small-error'>이메일 형식이 아닙니다. 예: name@example.com</div>", unsafe_allow_html=True)

        full_name = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()
        submit_new = st.form_submit_button("등록", disabled=(not full_name) or (email.strip() and not valid_email))

    # 이메일 빨간 테두리
    if st.session_state.get("new_email","").strip() and (not is_valid_email(st.session_state["new_email"])):
        st.markdown("""
        <script>
        const root = window.parent.document;
        const labels = [...root.querySelectorAll('label')];
        const target = labels.find(l => l.textContent.trim() === 'Email');
        if (target){
            const wrapper = target.closest('div');
            if (wrapper){ wrapper.classList.add('input-error'); }
        }
        </script>
        """, unsafe_allow_html=True)

    if submit_new:
        full_address = compose_address(addr_street, addr_unit, addr_city, addr_state, addr_zip)
        new_id = insert_client(full_name, st.session_state.new_phone.strip(), email.strip(), full_address, st.session_state.get("new_notes","").strip())
        st.session_state.current_client_id = new_id
        st.success("등록 완료! 리스트/선택 탭에서 확인되며, 아래 입력 탭이 활성화됩니다.")
        for k in ["new_first","new_last","new_phone","new_email","addr_street","addr_unit","addr_city","addr_state","addr_zip","new_notes"]:
            st.session_state[k] = ""
        st.rerun()

# ---------------------- 선택된 클라이언트 체크 ----------------------
client_id = st.session_state.current_client_id
if not client_id:
    st.stop()

# ---------------------- 실시간 요약(Sticky) ----------------------
with st.container():
    st.markdown('<div class="sticky-summary">', unsafe_allow_html=True)
    st.markdown("### 📌 실시간 요약")
    metrics_block(compute_summary(client_id))
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------- 입력 & 관리 ----------------------
st.markdown("---")
st.header("✍️ 입력 & 관리")
tab_inc, tab_exp, tab_ast, tab_liab, tab_sum = st.tabs(
    ["Income 입력","Expense 입력","Assets","Liabilities","Summary(보기/설정)"]
)

# ===== Income =====
with tab_inc:
    st.subheader("수입 항목 추가")
    with st.form("form_add_income", clear_on_submit=True):
        a,b,c = st.columns([1.2,2,1])
        with a: in_cat  = st.text_input("Category (Income)")
        with b: in_desc = st.text_input("Description (Income)")
        with c: in_amt  = st.number_input("Amount (Income)", min_value=0.0, step=10.0, value=0.0)
        ok = st.form_submit_button("추가")
    if ok:
        if (in_cat or in_desc) or (in_amt>0):
            insert_row("incomes", client_id, {"category":in_cat, "description":in_desc, "amount":in_amt, "ts":datetime.now().isoformat(timespec="seconds")})
            st.success("추가(자동저장) 완료!")
        st.session_state.focus_next = "income"; st.rerun()

    st.markdown("##### 현재 수입 내역")
    df_inc = df_query("SELECT id, category as Category, description as Description, amount as Amount FROM incomes WHERE client_id=? ORDER BY id DESC", client_id)
    if df_inc.empty: st.info("수입 항목이 없습니다.")
    else:
        df_show = df_inc.copy(); df_show.index = range(1, len(df_show)+1)
        del_idx = st.multiselect("삭제할 행 선택 (번호)", options=list(df_show.index), key="ms_del_inc")
        st.dataframe(df_show, use_container_width=True, height=300)
        if st.button("선택 행 삭제", key="btn_del_inc"):
            ids = [int(df_show.loc[i,"id"]) for i in del_idx] if del_idx else []
            delete_rows("incomes", ids); st.success("삭제(자동저장) 완료!"); st.rerun()

# ===== Expense =====
with tab_exp:
    st.subheader("지출 항목 추가")
    with st.form("form_add_expense", clear_on_submit=True):
        a,b,c = st.columns([1.2,2,1])
        with a: exp_cat  = st.text_input("Category (Expense)")
        with b: exp_desc = st.text_input("Description (Expense)")
        with c: exp_amt  = st.number_input("Amount (Expense)", min_value=0.0, step=10.0, value=0.0)
        ok = st.form_submit_button("추가")
    if ok:
        if (exp_cat or exp_desc) or (exp_amt>0):
            insert_row("expenses", client_id, {"category":exp_cat, "description":exp_desc, "amount":exp_amt, "ts":datetime.now().isoformat(timespec="seconds")})
            st.success("추가(자동저장) 완료!")
        st.session_state.focus_next = "expense"; st.rerun()

    st.markdown("##### 현재 지출 내역")
    df_exp = df_query("SELECT id, category as Category, description as Description, amount as Amount FROM expenses WHERE client_id=? ORDER BY id DESC", client_id)
    if df_exp.empty: st.info("지출 항목이 없습니다.")
    else:
        df_show = df_exp.copy(); df_show.index = range(1,len(df_show)+1)
        del_idx = st.multiselect("삭제할 행 선택 (번호)", options=list(df_show.index), key="ms_del_exp")
        st.dataframe(df_show, use_container_width=True, height=300)
        if st.button("선택 행 삭제", key="btn_del_exp"):
            ids = [int(df_show.loc[i,"id"]) for i in del_idx] if del_idx else []
            delete_rows("expenses", ids); st.success("삭제(자동저장) 완료!"); st.rerun()

# ===== Assets =====
with tab_ast:
    st.subheader("자산 항목 추가")
    with st.form("form_add_asset", clear_on_submit=True):
        a1,a2 = st.columns([2,1])
        with a1: ast_cat = st.text_input("Category (Assets)")
        with a2: ast_amt = st.number_input("Amount (Assets)", min_value=0.0, step=100.0, value=0.0)
        ok = st.form_submit_button("추가")
    if ok:
        if ast_cat or (ast_amt>0):
            insert_row("assets", client_id, {"category":ast_cat, "amount":ast_amt, "ts":datetime.now().isoformat(timespec="seconds")})
            st.success("추가(자동저장) 완료!")
        st.session_state.focus_next = "asset"; st.rerun()

    st.subheader("Assets 편집")
    df_ast = df_query("SELECT id, category as Category, amount as Amount FROM assets WHERE client_id=? ORDER BY id DESC", client_id)
    st.dataframe(df_ast.drop(columns=["id"]), use_container_width=True, height=260)
    del_ids = st.multiselect("삭제할 자산 ID", options=df_ast["id"].tolist(), key="del_ast_ids")
    if st.button("선택 자산 삭제", key="btn_del_ast"):
        delete_rows("assets", del_ids); st.success("삭제(자동저장) 완료!"); st.rerun()

# ===== Liabilities =====
with tab_liab:
    st.subheader("부채 항목 추가")
    with st.form("form_add_liab", clear_on_submit=True):
        l1,l2 = st.columns([2,1])
        with l1: li_cat = st.text_input("Category (Liabilities)")
        with l2: li_amt = st.number_input("Amount (Liabilities)", min_value=0.0, step=100.0, value=0.0)
        ok = st.form_submit_button("추가")
    if ok:
        if li_cat or (li_amt>0):
            insert_row("liabilities", client_id, {"category":li_cat, "amount":li_amt, "ts":datetime.now().isoformat(timespec="seconds")})
            st.success("추가(자동저장) 완료!")
        st.session_state.focus_next = "liab"; st.rerun()

    st.subheader("Liabilities 편집")
    df_liab = df_query("SELECT id, category as Category, amount as Amount FROM liabilities WHERE client_id=? ORDER BY id DESC", client_id)
    st.dataframe(df_liab.drop(columns=["id"]), use_container_width=True, height=260)
    del_ids = st.multiselect("삭제할 부채 ID", options=df_liab["id"].tolist(), key="del_liab_ids")
    if st.button("선택 부채 삭제", key="btn_del_liab"):
        delete_rows("liabilities", del_ids); st.success("삭제(자동저장) 완료!"); st.rerun()

# ===== Summary / 보기-설정 =====
with tab_sum:
    st.subheader("Summary (보기/설정)")
    etc_amount, use_income_details = get_settings(client_id)
    metrics_block(compute_summary(client_id))
    st.divider()
    use_income_details = st.checkbox("Income을 'Income Details' 합계로 사용", value=bool(use_income_details))
    etc_amount = st.number_input("Etc 금액", min_value=0.0, step=50.0, value=float(etc_amount))
    if st.button("설정 저장"):
        update_settings(client_id, etc_amount, int(use_income_details))
        st.success("설정 저장 완료!")
        st.rerun()

# ---------------------- 시각화 ----------------------
st.markdown("---")
st.header("📈 시각화")
draw_pie_with_list(compute_summary(client_id), "INCOME / EXPENSE", DEFAULT_COLORS_SUMMARY, key_tag="summary")
draw_pie_with_list(df_query("SELECT category as Category, amount as Amount FROM assets WHERE client_id=?", client_id),
                   "ASSET", DEFAULT_COLORS_ASSETS, key_tag="assets")
draw_pie_with_list(df_query("SELECT category as Category, amount as Amount FROM liabilities WHERE client_id=?", client_id),
                   "LIABILITY", DEFAULT_COLORS_LIAB, key_tag="liab")

# ---------------------- 포커스 이동 ----------------------
t = st.session_state.get("focus_next")
if t == "income":
    focus_field_by_label("Category (Income)")
elif t == "expense":
    focus_field_by_label("Category (Expense)")
elif t == "asset":
    focus_field_by_label("Category (Assets)")
elif t == "liab":
    focus_field_by_label("Category (Liabilities)")
st.session_state["focus_next"] = None
