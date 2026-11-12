"""WardRounds: temperature, visit and discharge tracking for a 74-room quarantine ward.

Run locally:  pip install -r requirements.txt  then  streamlit run app.py
"""
import html
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

FEVER, BEDS = 38.0, 74
START = date(2026, 11, 12)
# shortcut: one JSON file shared by everyone using this server; move to a real database before real use
DATA = Path(__file__).with_name("ward_data.json")
STAFF = {
    "Nurse": ("Nurse Asha", "thermo", "Record each patient's daily temperature"),
    "Doctor": ("Dr. Mehra", "steth", "Visit patients, record treatment, sign off discharges"),
    "Admin staff": ("Ravi (Admin)", "bed", "Admit patients, assign rooms, complete discharges"),
    "Head doctor": ("Dr. Iyer", "pulse", "Ward overview and quality against the 85% benchmark"),
}
ICON = {
    "steth": '<path d="M5 3v6a4 4 0 0 0 8 0V3"/><path d="M9 13v2a5 5 0 0 0 10 0v-2"/><circle cx="19" cy="11" r="2"/>',
    "thermo": '<path d="M14 14.8V4.5a2.5 2.5 0 0 0-5 0v10.3a4.5 4.5 0 1 0 5 0z"/><path d="M11.5 9v7"/>',
    "bed": '<path d="M3 5v14"/><path d="M3 9h15a3 3 0 0 1 3 3v7"/><path d="M3 16h18"/><path d="M7 9v7"/>',
    "pulse": '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
}


def icon(name, size=24):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICON[name]}</svg>')


# ---------- data ----------
def seed():
    r = random.Random(7)
    first = ["Aarav", "Priya", "Rohan", "Sneha", "Vikram", "Ananya", "Kabir", "Meera", "Arjun", "Isha", "Farhan", "Lakshmi",
             "Neel", "Pooja", "Sameer", "Divya", "Karan", "Nisha", "Rahul", "Zoya", "Tara", "Imran", "Kavya", "Manoj"]
    last = ["Sharma", "Patel", "Iyer", "Khan", "Reddy", "Nair", "Das", "Joshi", "Gupta", "Menon", "Shetty", "Bose", "Rao",
            "Kulkarni", "Singh", "Pillai"]
    patients = []
    for i in range(1, BEDS + 1):
        stay = 1 + int(r.random() * 11)
        fever_days = max(1, stay - int(r.random() * r.random() * 4))
        p = dict(id=i, name=f"{r.choice(first)} {r.choice(last)}", age=18 + int(r.random() * 62), sex=r.choice("MF"),
                 kin="", room=i, admit=-stay, temps={}, visits={}, dis_req=False)
        for d in range(-stay, 0):
            t = 38.2 + r.random() * 1.8 if d - p["admit"] < fever_days else 36.4 + r.random()
            p["temps"][str(d)] = {"t": round(t, 1), "by": "Nurse Asha", "at": "08:30"}
            p["visits"][str(d)] = {"note": "Reviewed. Continue current treatment.", "by": "Dr. Mehra", "at": "11:00"}
        patients.append(p)
    for i, p in enumerate(patients[:30]):  # part of today's round already done
        prev = p["temps"]["-1"]["t"]
        t = prev - r.random() * 0.6 if prev >= FEVER else 36.5 + r.random() * 0.8
        p["temps"]["0"] = {"t": round(t, 1), "by": "Nurse Asha", "at": f"08:{10 + i:02d}"}
        if i < 12:
            p["visits"]["0"] = {"note": "Reviewed. Continue current treatment.", "by": "Dr. Mehra", "at": "11:00"}
    archive = [{"outcome": "deceased" if i < 6 else "discharged", "los": 4 + int(r.random() * 10)} for i in range(47)]
    return dict(day=0, next_id=BEDS + 1, patients=patients, archive=archive)


def save(s):
    DATA.write_text(json.dumps(s))


def load():
    try:
        return json.loads(DATA.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        s = seed()
        save(s)
        return s


S = load()
DAY = S["day"]


def fmt(d):
    return (START + timedelta(days=d)).strftime("%d %b")


def now():
    return datetime.now().strftime("%H:%M")


def temp(p, d=None):
    return p["temps"].get(str(DAY if d is None else d))


def visited(p):
    return str(DAY) in p["visits"]


def streak(p):
    """Consecutive fever-free days counting back from today (or yesterday if today's reading is not in yet)."""
    d = DAY if temp(p) else DAY - 1
    n = 0
    while d >= p["admit"] and temp(p, d) and temp(p, d)["t"] < FEVER:
        n += 1
        d -= 1
    return n


def eligible(p):
    return streak(p) >= 3


def missed_yesterday(p):
    return p["admit"] < DAY and not temp(p, DAY - 1)


def label(p):
    return f"R{p['room']:02d} · {p['name']}"


def by_id(pid):
    return next(p for p in S["patients"] if p["id"] == pid)


def patients():
    return sorted(S["patients"], key=lambda p: p["room"])


def first_free():
    used = {p["room"] for p in S["patients"]}
    return next((r for r in range(1, BEDS + 1) if r not in used), None)


def status(p):
    t = temp(p)
    if p["dis_req"]:
        return "Sent to admin"
    if eligible(p):
        return "Can be discharged"
    if not t:
        return "No reading yet"
    return "Fever" if t["t"] >= FEVER else "Normal"


def table(lst):
    return pd.DataFrame([{
        "Room": p["room"], "Patient": p["name"], "Age": p["age"],
        "Today": f'{temp(p)["t"]:.1f} °C' if temp(p) else "Not taken",
        "Fever-free days": streak(p), "Status": status(p),
        "Missed yesterday": "Yes" if missed_yesterday(p) else "",
    } for p in lst])


def done(msg):
    save(S)
    st.session_state.flash = msg
    st.rerun()


def close_case(p, outcome):
    S["archive"].append({"outcome": outcome, "los": DAY - p["admit"] + 1})
    S["patients"] = [x for x in S["patients"] if x["id"] != p["id"]]


# ---------- look ----------
st.set_page_config(page_title="WardRounds", page_icon="🩺", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700&family=Inter:wght@400;500;600&display=swap');
html, body, [class*="st-"], .stMarkdown, button, input, textarea {font-family: "Inter", system-ui, sans-serif;}
h1, h2, h3, .wr-logo b, [data-testid="stMetricValue"] {font-family: "Montserrat", system-ui, sans-serif !important;}
.stApp {background: #F2F9FD;}
[data-testid="stSidebar"] {background: #FFFFFF; box-shadow: 0 0 30px rgba(14,110,160,.08);}
.block-container {padding-top: 4rem; max-width: 1150px;}
.eyebrow {margin: 0 0 -6px; font-size: 12px; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; color: #1597D3 !important;}
.wr-logo {display: flex; align-items: center; gap: 10px; color: #1597D3; margin-bottom: 4px;}
.wr-logo b {font-size: 22px;}
.stButton > button, .stFormSubmitButton > button {border-radius: 999px; font-weight: 600; padding: .35rem 1.2rem;}
[data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] {background: #FFFFFF; border: 0 !important; border-radius: 20px; box-shadow: 0 12px 30px rgba(14,110,160,.10);}
[data-testid="stMetric"] {background: #FFFFFF; border-radius: 18px; padding: 14px 18px; box-shadow: 0 12px 30px rgba(14,110,160,.10);}
[data-testid="stMetricLabel"] p {text-transform: uppercase; letter-spacing: .06em; font-size: 12px; font-weight: 600; color: #687A8C;}
[data-testid="stDataFrame"] {border-radius: 16px; overflow: hidden;}
.hero {display: grid; grid-template-columns: 1.1fr 1fr; gap: 24px; align-items: center; background: #FFFFFF; border-radius: 28px; padding: 36px; box-shadow: 0 12px 30px rgba(14,110,160,.10); overflow: hidden;}
.hero h1 {font-size: clamp(28px, 3.6vw, 44px); line-height: 1.15; color: #1C2A3A; margin: 8px 0 12px;}
.hero p {color: #687A8C; font-size: 16px;}
.blob {position: relative; aspect-ratio: 1; max-width: 360px; width: 100%; justify-self: center; border-radius: 50%;
       background: radial-gradient(circle at 30% 25%, #5CC7F2, #1597D3 55%, #0A78B4); box-shadow: inset 0 -30px 60px rgba(0,60,100,.18);}
.float {position: absolute; width: 58px; height: 58px; border-radius: 16px; background: #fff; color: #1597D3; display: flex; align-items: center; justify-content: center; box-shadow: 0 14px 30px rgba(0,60,100,.25);}
.reading {position: absolute; background: #fff; border-radius: 16px; padding: 12px 16px; box-shadow: 0 18px 40px rgba(0,60,100,.25); min-width: 160px;}
.reading span {display: block; font-size: 12px; color: #687A8C;} .reading b {display: block; font-family: Montserrat, sans-serif; font-size: 24px; color: #1C2A3A;}
.reading em {font-style: normal; font-size: 12px; font-weight: 600;}
.role-card {background: #fff; border-radius: 22px; padding: 18px; box-shadow: 0 12px 30px rgba(14,110,160,.10); min-height: 150px; margin-bottom: 8px;}
.role-card .ico {width: 44px; height: 44px; border-radius: 14px; background: #E2F2FB; color: #1597D3; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;}
.role-card b {font-family: Montserrat, sans-serif; font-size: 17px; color: #1C2A3A;} .role-card p {color: #687A8C; font-size: 13px; margin: 4px 0 0;}
.role-card.blue {background: linear-gradient(150deg, #2AAEE6, #0A78B4);} .role-card.blue b, .role-card.blue p {color: #fff;}
.role-card.blue .ico {background: rgba(255,255,255,.2); color: #fff;}
.grid {display: grid; grid-template-columns: repeat(auto-fill, minmax(44px, 1fr)); gap: 6px;}
.bed {aspect-ratio: 1; border-radius: 12px; font-size: 12px; font-weight: 600; display: flex; align-items: center; justify-content: center; background: #F2F9FD; color: #8A99A8; border: 1.5px dashed #DCECF5;}
.bed.occ {background: #E2F2FB; color: #0A78B4; border: 0;} .bed.fev {background: #FDEBEC; color: #E0464B;}
.bed.elig {background: #E0F6EE; color: #0E9C75;} .bed.req {background: #1597D3; color: #fff;}
.legend {display: flex; flex-wrap: wrap; gap: 14px; font-size: 12px; color: #687A8C; margin-top: 12px;}
.legend i {display: inline-block; width: 11px; height: 11px; border-radius: 4px; margin-right: 6px; vertical-align: -1px;}
@media (max-width: 760px) {.hero {grid-template-columns: 1fr; padding: 24px;}}
</style>
""", unsafe_allow_html=True)

if "flash" in st.session_state:
    st.toast(st.session_state.pop("flash"))


def heading(eyebrow, title, sub=None):
    st.markdown(f'<p class="eyebrow">{eyebrow}</p>', unsafe_allow_html=True)
    st.markdown(f"## {title}")
    if sub:
        st.caption(sub)


# ---------- screens ----------
def signin():
    st.markdown(f"""
<div class="hero">
  <div>
    <div class="wr-logo">{icon("steth", 30)}<b>WardRounds</b></div>
    <p class="eyebrow" style="margin-top:28px">Quarantine ward · {BEDS} rooms</p>
    <h1>Every patient measured, visited and discharged on time.</h1>
    <p>Nurses record one temperature a day, doctors see who is ready for a visit, and admin gets discharges as soon as they are signed off.</p>
  </div>
  <div class="blob">
    <div class="float" style="left:-4%;top:58%">{icon("thermo", 30)}</div>
    <div class="float" style="right:14%;top:6%">{icon("pulse", 30)}</div>
    <div class="reading" style="left:16%;top:24%"><span>Room 14 · today</span><b>38.6 °C</b><em style="color:#E0464B">Fever</em></div>
    <div class="reading" style="right:12%;bottom:14%"><span>Fever-free streak</span><b>3 of 3 days</b><em style="color:#0E9C75">Ready to discharge</em></div>
  </div>
</div>""", unsafe_allow_html=True)
    st.write("")
    st.markdown('<p class="eyebrow" style="text-align:center">Sign in</p>', unsafe_allow_html=True)
    st.markdown("<h3 style='text-align:center;margin-top:0'>Choose your staff account</h3>", unsafe_allow_html=True)
    st.caption("Each role is a demo account in this prototype.")
    for i, (col, (role, (who, ico, desc))) in enumerate(zip(st.columns(4), STAFF.items())):
        with col:
            st.markdown(f'<div class="role-card {"blue" if i == 0 else ""}"><div class="ico">{icon(ico)}</div>'
                        f'<b>{role}</b><p>{desc}</p></div>', unsafe_allow_html=True)
            if st.button(f"Sign in as {role}", key=f"login{i}", type="primary", width="stretch"):
                st.session_state.role = role
                st.rerun()


def nurse():
    pts = patients()
    measured = [p for p in pts if temp(p)]
    pending = [p for p in pts if not temp(p)]
    heading("Nurse station", "Today's temperature round",
            f"One reading per patient per day. Fever is {FEVER:.1f} °C or higher.")
    st.progress(len(measured) / max(1, len(pts)), text=f"{len(measured)} of {len(pts)} patients measured on {fmt(DAY)}")

    left, right = st.columns([1, 1.5], gap="large")
    with left:
        correctable = [p for p in measured if not visited(p)]
        options = [p["id"] for p in pending + correctable]
        if not options:
            st.success("Round complete. Every patient has today's reading.")
        else:
            with st.form("record", clear_on_submit=True):
                st.markdown("#### Record a temperature")
                pid = st.selectbox("Patient", options, format_func=lambda i: label(by_id(i)) + (
                    f"  (correct {temp(by_id(i))['t']:.1f} °C)" if temp(by_id(i)) else ""))
                t = st.number_input("Temperature (°C)", value=None, step=0.1, format="%.1f", placeholder="e.g. 37.2")
                sure = st.checkbox("I have re-checked a reading above 41.0 °C")
                if st.form_submit_button("Save reading", type="primary", width="stretch"):
                    p = by_id(pid)
                    if t is None:
                        st.error("Enter the temperature in °C.")
                    elif not 34.0 <= t <= 43.0:
                        st.error("Check the reading: it must be between 34.0 and 43.0 °C.")
                    elif t > 41.0 and not sure:
                        st.warning(f"{t:.1f} °C is very high. Re-check it, tick the box and save again.")
                    elif visited(p):
                        st.error("The doctor has already visited today, so only the doctor can change this reading.")
                    else:
                        corrected = bool(temp(p))
                        if corrected:
                            p.setdefault("log", []).append({"day": DAY, "old": temp(p)["t"], "at": now()})
                        p["temps"][str(DAY)] = {"t": round(t, 1), "by": STAFF["Nurse"][0], "at": now()}
                        msg = f"{'Updated' if corrected else 'Saved'} {t:.1f} °C for {p['name']}"
                        if t >= FEVER and p["dis_req"]:
                            p["dis_req"] = False
                            msg += ". Fever after sign-off: discharge cancelled, doctor and admin alerted"
                        done(msg)
        missed = [p for p in pending if missed_yesterday(p)]
        if missed:
            st.warning(f"Missed yesterday: {', '.join('R' + str(p['room']) for p in missed[:15])}"
                       f"{' …' if len(missed) > 15 else ''}. Measure these first.")
    with right:
        a, b = st.tabs([f"To measure ({len(pending)})", f"Measured ({len(measured)})"])
        cols = ["Room", "Patient", "Age", "Missed yesterday"]
        with a:
            st.dataframe(table(pending)[cols] if pending else pd.DataFrame(), hide_index=True, width="stretch", height=420)
        with b:
            st.dataframe(table(measured)[["Room", "Patient", "Today", "Status"]] if measured else pd.DataFrame(),
                         hide_index=True, width="stretch", height=420)


def temp_chart(p):
    rows = [{"Date": fmt(d), "Temperature": temp(p, d)["t"]} for d in range(max(p["admit"], DAY - 9), DAY + 1) if temp(p, d)]
    if not rows:
        st.caption("No readings yet.")
        return
    df = pd.DataFrame(rows)
    base = alt.Chart(df).encode(x=alt.X("Date:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
                                y=alt.Y("Temperature:Q", scale=alt.Scale(domain=[35.5, 41]), title="°C"))
    line = base.mark_line(color="#1597D3", strokeWidth=2.5) + base.mark_circle(size=70).encode(
        color=alt.condition(alt.datum.Temperature >= FEVER, alt.value("#E0464B"), alt.value("#0E9C75")),
        tooltip=["Date", "Temperature"])
    rule = alt.Chart(pd.DataFrame({"y": [FEVER]})).mark_rule(color="#E0464B", strokeDash=[5, 4]).encode(y="y:Q")
    st.altair_chart((line + rule).properties(height=210), width="stretch")


def patient_panel(p, who):
    with st.container(border=True):
        st.markdown(f"### {p['name']}")
        st.caption(f"Room {p['room']} · {p['age']} y · admitted {fmt(p['admit'])} (day {DAY - p['admit'] + 1})")
        t = temp(p)
        c1, c2 = st.columns(2)
        c1.metric("Today", f"{t['t']:.1f} °C" if t else "Not taken")
        c2.metric("Fever-free days", f"{streak(p)} of 3")
        temp_chart(p)

        v = p["visits"].get(str(DAY))
        if v:
            st.success(f"Visited today by {v['by']} at {v['at']}: {v['note']}")
        elif not t:
            st.warning("Visit locked until the nurse records today's temperature.")
        else:
            with st.form(f"visit{p['id']}", clear_on_submit=True):
                note = st.text_area("Assessment and treatment for today", placeholder="e.g. Paracetamol 650 mg every 6 h, oral fluids")
                if st.form_submit_button("Complete visit", type="primary"):
                    if len(note.strip()) < 3:
                        st.error("Add a short note on the assessment or treatment.")
                    else:
                        p["visits"][str(DAY)] = {"note": note.strip(), "by": who, "at": now()}
                        done(f"Visit recorded for {p['name']}")

        if p["dis_req"]:
            st.info("Discharge sent to admin.")
        elif st.button("Send discharge to admin", key=f"dis{p['id']}", disabled=not eligible(p),
                       help=None if eligible(p) else f"Needs 3 fever-free days in a row (now {streak(p)})"):
            p["dis_req"] = True
            done(f"Discharge sent to admin for {p['name']}")

        with st.expander("Record death"):
            ok = st.checkbox(f"I confirm {p['name']} has died. This closes the case and frees room {p['room']}.", key=f"dc{p['id']}")
            if st.button("Record death", key=f"death{p['id']}", disabled=not ok):
                close_case(p, "deceased")
                done("Death recorded and case closed")


def doctor(prefix="d", who=STAFF["Doctor"][0]):
    pts = patients()
    groups = {
        "Ready for visit": [p for p in pts if temp(p) and not visited(p)],
        "Waiting for temperature": [p for p in pts if not temp(p) and not visited(p)],
        "Visited today": [p for p in pts if visited(p)],
        "Fever-free 3+ days": [p for p in pts if eligible(p)],
    }
    if prefix == "d":
        heading("Doctor", "Doctor's rounds",
                f"{len(groups['Visited today'])} of {len(pts)} visited today. Patients become ready once the nurse has taken today's temperature.")
    q = st.radio("Queue", list(groups), horizontal=True, key=prefix + "queue", label_visibility="collapsed",
                 format_func=lambda k: f"{k} ({len(groups[k])})")
    lst = groups[q]
    if not lst:
        st.info("No patients in this list.")
        return
    left, right = st.columns([1, 1.25], gap="large")
    with left:
        pid = st.selectbox("Open patient", [p["id"] for p in lst], format_func=lambda i: label(by_id(i)), key=f"{prefix}sel{q}")
        st.dataframe(table(lst)[["Room", "Patient", "Today", "Fever-free days", "Status"]], hide_index=True,
                     width="stretch", height=440)
    with right:
        patient_panel(by_id(pid), who)


def admin():
    pts = patients()
    free = BEDS - len(pts)
    heading("Admin desk", "Admissions and discharges")
    req = [p for p in pts if p["dis_req"]]
    waiting = [p for p in pts if eligible(p) and not p["dis_req"]]
    c = st.columns(3)
    c[0].metric("Rooms occupied", f"{len(pts)} / {BEDS}")
    c[1].metric("Ready to discharge", len(req))
    c[2].metric("Waiting for doctor sign-off", len(waiting))

    left, right = st.columns([1, 1.2], gap="large")
    with left:
        if not free:
            st.warning("Ward is full. New admissions open as soon as a patient is discharged.")
        else:
            with st.form("admit", clear_on_submit=False):
                st.markdown(f"#### Admit a patient to room {first_free()}")
                name = st.text_input("Full name")
                a, b = st.columns(2)
                age = a.number_input("Age", min_value=0, max_value=120, value=None, step=1)
                sex = b.selectbox("Sex", ["", "Female", "Male", "Other"])
                kin = st.text_input("Next-of-kin phone")
                dup_ok = st.checkbox("Admit even if a patient with the same name and age is already here")
                if st.form_submit_button("Admit patient", type="primary", width="stretch"):
                    dup = any(p["name"].lower() == name.strip().lower() and p["age"] == age for p in pts)
                    if len(name.strip()) < 2 or age is None or not sex or len(kin.strip()) < 6:
                        st.error("Name, age, sex and next-of-kin phone are all required.")
                    elif dup and not dup_ok:
                        st.warning(f"{name} ({age}) is already admitted. Check it isn't a duplicate, tick the box and admit again.")
                    else:
                        room = first_free()
                        S["patients"].append(dict(id=S["next_id"], name=name.strip(), age=int(age), sex=sex[0], kin=kin.strip(),
                                                  room=room, admit=DAY, temps={}, visits={}, dis_req=False))
                        S["next_id"] += 1
                        done(f"{name.strip()} admitted to room {room}")

        st.markdown("#### Ready to discharge")
        if not req:
            st.caption("No discharges waiting.")
        for p in req:
            with st.container(border=True):
                x, y = st.columns([2, 1])
                x.markdown(f"**{label(p)}**  \nSigned off by doctor · stay {DAY - p['admit'] + 1} days")
                if y.button("Complete discharge", key=f"out{p['id']}", type="primary"):
                    close_case(p, "discharged")
                    done(f"{p['name']} discharged. Room {p['room']} is free.")
        if waiting:
            st.caption("Meet the 3-day rule but not signed off yet (remind the doctor): "
                       + ", ".join(f"R{p['room']}" for p in waiting))
    with right:
        st.markdown("#### Rooms")
        rooms = {p["room"]: p for p in pts}
        cells = []
        for r in range(1, BEDS + 1):
            p = rooms.get(r)
            t = p and temp(p)
            cls = "" if not p else "occ req" if p["dis_req"] else "occ elig" if eligible(p) else "occ fev" if t and t["t"] >= FEVER else "occ"
            cells.append(f'<div class="bed {cls}" title="{html.escape(p["name"]) if p else "Free"}">{r}</div>')
        legend = "".join(f'<span><i style="background:{c}"></i>{t}</span>' for c, t in [
            ("#F2F9FD;border:1.5px dashed #DCECF5", "Free"), ("#E2F2FB", "Occupied"), ("#FDEBEC", "Fever today"),
            ("#E0F6EE", "Meets discharge rule"), ("#1597D3", "Discharge sent")])
        st.markdown(f'<div class="grid">{"".join(cells)}</div><div class="legend">{legend}</div>', unsafe_allow_html=True)


def head():
    heading("Head doctor", "Ward overview", f"{fmt(DAY)} · outcomes counted over all closed cases (discharged + deceased)")
    overview, rounds = st.tabs(["Overview", "My rounds"])
    with rounds:
        doctor(prefix="h", who=STAFF["Head doctor"][0])
    with overview:
        pts = patients()
        n = len(pts)
        dead = sum(a["outcome"] == "deceased" for a in S["archive"])
        closed = len(S["archive"])
        mort = dead / closed * 100 if closed else 0.0
        cured = [a["los"] for a in S["archive"] if a["outcome"] == "discharged"]
        if mort > 15:
            st.error(f"Mortality is {mort:.1f}%, above the expected 15%. Review recent deaths and treatment protocols.")
        else:
            st.success(f"Mortality is {mort:.1f}%, within the expected 15% (success rate {100 - mort:.1f}% vs 85% benchmark).")
        temps = sum(bool(temp(p)) for p in pts)
        visits = sum(visited(p) for p in pts)
        c = st.columns(5)
        c[0].metric("Occupancy", f"{n}/{BEDS}")
        c[1].metric("Temperatures today", f"{temps}/{n}")
        c[2].metric("Visits today", f"{visits}/{n}")
        c[3].metric("Success rate", f"{100 - mort:.1f}%", f"{100 - mort - 85:+.1f} pts vs 85%")
        c[4].metric("Average stay", f"{sum(cured) / max(1, len(cured)):.1f} days")
        st.markdown("#### Needs attention")
        rows = [
            ("Missed yesterday's temperature", [p for p in pts if missed_yesterday(p)], "Nurses"),
            ("Fever-free 3+ days, not signed off", [p for p in pts if eligible(p) and not p["dis_req"]], "Doctors"),
            ("Signed off, not yet discharged", [p for p in pts if p["dis_req"]], "Admin"),
        ]
        st.dataframe(pd.DataFrame([{"Issue": i, "Patients": len(l), "Rooms": ", ".join(f"R{p['room']}" for p in l) or "None",
                                    "Follow up with": w} for i, l, w in rows]), hide_index=True, width="stretch")


# ---------- app ----------
role = st.session_state.get("role")
if not role:
    signin()
else:
    with st.sidebar:
        st.markdown(f'<div class="wr-logo">{icon("steth", 28)}<b>WardRounds</b></div>', unsafe_allow_html=True)
        st.caption(f"Signed in as **{role}** · {STAFF[role][0]}")
        if st.button("Switch user", width="stretch"):
            del st.session_state["role"]
            st.rerun()
        st.divider()
        st.markdown(f"**Day {DAY + 1}** · {fmt(DAY)}")
        st.caption("Demo controls")
        if st.button("Next day ▸", width="stretch"):
            S["day"] += 1
            done(f"Moved to {fmt(S['day'])}")
        if st.button("Reset demo data", width="stretch"):
            S = seed()
            done("Demo data reset")
    {"Nurse": nurse, "Doctor": doctor, "Admin staff": admin, "Head doctor": head}[role]()
