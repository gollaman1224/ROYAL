import json
import os
import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from collections import defaultdict, Counter
from functools import wraps
import re

# ★ 닉네임 색상 인덱스 함수 추가
def calc_nick_color_index(nick, color_count=10):
    """닉네임의 첫 글자 유니코드로 색상 인덱스 반환 (1~color_count)"""
    if not nick:
        return 1
    first = nick.strip()[0]
    return (ord(first) % color_count) + 1

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "very_secret_admin_key")

DATA_FILE = "members.json"
ATTENDANCE_FILE = "attendance.json"
ASSIGNMENT_FILE = "current_assignment.json"
MAX_PER_PARTY = 5
SERVERS = ["피데스", "모르스", "메투스", "호노르", "돌도르", "살루스"]
ADMIN_CODE = "ROYAL777"
EXCLUDED_BOSSES = {"차원의 틈"}

def normalize_boss_name(boss):
    if not boss:
        return ""
    s = str(boss).replace(" ", "").replace("-", "").replace("_", "").lower()
    s = re.sub(r"(어비스|abys?)[\s\-]*([0-9]+)[\s\-]*(층|f)?", lambda m: f"어비스{m.group(2)}층", s)
    return s

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        code = request.form.get("access_code", "")
        if code == ADMIN_CODE:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        else:
            error = "접근 코드가 올바르지 않습니다."
    return render_template("login.html", error=error)

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

def load_json(filename, default=[]):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return default.copy()

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_members():
    members = load_json(DATA_FILE, [])
    for m in members:
        try:
            m["신화개수"] = int(m.get("신화개수", 0))
        except:
            m["신화개수"] = 0
        if "파티번호" not in m or m["파티번호"] is None:
            m["파티번호"] = 1
        if "서버" not in m or not m["서버"]:
            m["서버"] = SERVERS[0]
        if "전설스킬" not in m:
            m["전설스킬"] = "없음"
        if "나침반" not in m:
            m["나침반"] = ""
    return members

def save_members(members):
    save_json(DATA_FILE, members)

def assign_parties(members):
    for m in members:
        m["파티번호"] = 0
        try:
            m["신화개수"] = int(m.get("신화개수", 0))
        except:
            m["신화개수"] = 0
    party_count = (len(members) + MAX_PER_PARTY - 1) // MAX_PER_PARTY
    parties = [[] for _ in range(party_count)]
    def strength(m):
        score = m["신화개수"]
        if m.get("전설스킬", "없음") == "있음":
            score += 0.1
        if m.get("나침반", "") == "O":
            score += 0.05
        return score
    sorted_members = sorted(members, key=strength, reverse=True)
    for i, member in enumerate(sorted_members):
        party_idx = i // MAX_PER_PARTY
        if party_idx >= party_count:
            party_idx = party_count - 1
        parties[party_idx].append(member)
        member["파티번호"] = party_idx + 1
    save_members(members)

def get_parties_by_number(members):
    grouped = defaultdict(list)
    for m in members:
        pnum = m.get("파티번호", 1)
        grouped[pnum].append(m)
    return [grouped[i] for i in sorted(grouped.keys())]

def strength_score(m):
    score = m["신화개수"]
    if m.get("전설스킬", "없음") == "있음":
        score += 0.1
    if m.get("나침반", "") == "O":
        score += 0.05
    return score

def load_server_assignment(members):
    if not os.path.exists(ASSIGNMENT_FILE):
        return
    assignment = load_json(ASSIGNMENT_FILE, {})
    for m in members:
        if m["닉네임"] in assignment:
            m["서버"] = assignment[m["닉네임"]]

def save_server_assignment(members):
    assignment = {m["닉네임"]: m["서버"] for m in members}
    save_json(ASSIGNMENT_FILE, assignment)

def assign_servers(members):
    healers = [m for m in members if m["직업"] == "디바인캐스터"]
    others = [m for m in members if m["직업"] != "디바인캐스터"]
    healers.sort(key=strength_score, reverse=True)
    for i, server in enumerate(SERVERS):
        if i < len(healers):
            healers[i]["서버"] = server
    remaining_healers = healers[len(SERVERS):] if len(healers) > len(SERVERS) else []
    remaining_members = remaining_healers + others
    remaining_members.sort(key=lambda m: m["신화개수"], reverse=True)
    for idx, member in enumerate(remaining_members):
        member["서버"] = SERVERS[idx % len(SERVERS)]
    save_members(members)
    save_server_assignment(members)

@app.route("/index")
@login_required
def index():
    members = load_members()
    query = request.args.get("q", "").strip().lower()
    if query:
        filtered = [m for m in members if
                    query in m["닉네임"].lower() or
                    query in m["직업"].lower() or
                    query in str(m["신화개수"]) or
                    query in m.get("나침반", "").lower() or
                    query in m.get("전설스킬", "").lower()]
    else:
        filtered = members
    filtered_sorted = sorted(filtered, key=lambda x: x["신화개수"], reverse=True)
    grouped = defaultdict(list)
    for m in filtered_sorted:
        grouped[m["직업"]].append(m)
    total_count = len(filtered_sorted)
    return render_template("index.html", grouped_members=grouped, total_count=total_count, query=query)

@app.route("/party")
@login_required
def party():
    members = load_members()
    parties = get_parties_by_number(members)
    job_colors = {
        "뱅가드": "#ff0000", "버서커": "#ff5c5c", "나이트레인져": "#0099ff", "어쌔신": "#ff9900",
        "디바인캐스터": "#cc66ff", "엘리멘탈": "#33cccc", "데스브링어": "#990000", "디스트로이어": "#660066"
    }
    return render_template("party.html", parties=parties, job_colors=job_colors)

@app.route("/swap_members", methods=["POST"])
@login_required
def swap_members():
    members = load_members()
    nick1 = request.form.get("nick1")
    nick2 = request.form.get("nick2")
    m1 = next((m for m in members if m["닉네임"] == nick1), None)
    m2 = next((m for m in members if m["닉네임"] == nick2), None)
    if not m1 or not m2:
        return "멤버를 찾을 수 없습니다", 404
    p1 = m1.get("파티번호", 1)
    p2 = m2.get("파티번호", 1)
    m1["파티번호"], m2["파티번호"] = p2, p1
    save_members(members)
    return redirect(url_for("party"))

@app.route("/reset_parties")
@login_required
def reset_parties():
    members = load_members()
    assign_parties(members)
    assign_servers(members)
    return redirect(url_for("party"))

@app.route("/servers")
@login_required
def servers():
    members = load_members()
    load_server_assignment(members)
    server_allocation = defaultdict(list)
    # 닉네임 컬러 인덱스 계산해서 멤버 dict에 추가
    for m in members:
        m["nick_color"] = calc_nick_color_index(m["닉네임"])
        server_allocation[m["서버"]].append(m)
    job_colors = {
        "뱅가드": "#ff0000", "버서커": "#ff5c5c", "나이트레인져": "#0099ff", "어쌔신": "#ff9900",
        "디바인캐스터": "#cc66ff", "엘리멘탈": "#33cccc", "데스브링어": "#990000", "디스트로이어": "#660066"
    }
    return render_template("servers.html",
                           servers=SERVERS,
                           server_allocation=server_allocation,
                           job_colors=job_colors)

@app.route("/change_server", methods=["POST"])
@login_required
def change_server():
    data = request.get_json()
    nick = data.get("nick")
    new_server = data.get("new_server")
    members = load_members()
    load_server_assignment(members)
    member = next((m for m in members if m["닉네임"] == nick), None)
    if member:
        member["서버"] = new_server
        save_members(members)
        save_server_assignment(members)
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "멤버를 찾을 수 없습니다."}), 404

@app.route("/reassign_servers", methods=["POST"])
@login_required
def reassign_servers():
    members = load_members()
    assign_servers(members)
    return jsonify({"success": True})

@app.route("/add")
@login_required
def add_member_form():
    return render_template("add.html")

@app.route("/add", methods=["POST"])
@login_required
def add_member():
    members = load_members()
    nick = request.form.get("닉네임")
    job = request.form.get("직업")
    myth = request.form.get("신화개수")
    compass = request.form.get("나침반", "")
    legend = request.form.get("전설스킬", "없음")
    server = request.form.get("서버", SERVERS[0])
    if nick and job and myth is not None:
        try:
            myth_num = int(myth)
        except:
            myth_num = 0
        members.append({
            "닉네임": nick,
            "직업": job,
            "신화개수": myth_num,
            "나침반": compass,
            "전설스킬": legend,
            "파티번호": 1,
            "서버": server
        })
        assign_parties(members)
        assign_servers(members)
    return redirect(url_for("index"))

@app.route("/delete/<nick>")
@login_required
def delete_member(nick):
    members = load_members()
    members = [m for m in members if m["닉네임"] != nick]
    save_members(members)
    assign_parties(members)
    assign_servers(members)
    return redirect(url_for("index"))

@app.route("/edit/<nick>")
@login_required
def edit_member(nick):
    members = load_members()
    member = next((m for m in members if m["닉네임"] == nick), None)
    if not member:
        return "멤버가 없습니다", 404
    return render_template("edit.html", member=member)

@app.route("/edit/<nick>", methods=["POST"])
@login_required
def update_member(nick):
    members = load_members()
    member = next((m for m in members if m["닉네임"] == nick), None)
    if not member:
        return "멤버가 없습니다", 404
    member["닉네임"] = request.form.get("닉네임")
    member["직업"] = request.form.get("직업")
    try:
        member["신화개수"] = int(request.form.get("신화개수"))
    except:
        member["신화개수"] = 0
    member["나침반"] = request.form.get("나침반", "")
    member["전설스킬"] = request.form.get("전설스킬", "없음")
    member["서버"] = request.form.get("서버", SERVERS[0])
    save_members(members)
    assign_parties(members)
    assign_servers(members)
    return redirect(url_for("index"))

@app.route("/toggle_field", methods=["POST"])
@login_required
def toggle_field():
    data = request.get_json()
    nick = data.get("nick")
    field = data.get("field")
    value = data.get("value")
    members = load_members()
    member = next((m for m in members if m["닉네임"] == nick), None)
    if not member or field not in ["나침반", "전설스킬"]:
        return jsonify({"success": False, "error": "대상 멤버/필드 없음"})
    if field == "나침반":
        member["나침반"] = "O" if value == "O" else ""
    elif field == "전설스킬":
        member["전설스킬"] = "있음" if value == "있음" else "없음"
    save_members(members)
    return jsonify({"success": True})

def get_all_dates():
    attendance = load_json(ATTENDANCE_FILE, [])
    return sorted({record["date"] for record in attendance})

@app.route("/calendar")
@login_required
def calendar():
    attendance = load_json(ATTENDANCE_FILE, [])
    for a in attendance:
        a["boss"] = normalize_boss_name(a["boss"])
    all_dates = get_all_dates()
    date = request.args.get("date")
    if not date:
        date = datetime.date.today().isoformat()
    return render_template(
        "calendar.html",
        attendance=attendance,
        all_dates=all_dates,
        date=date
    )

@app.route("/attendance_manage", methods=["GET", "POST"])
@login_required
def attendance_manage():
    members = load_members()
    attendance = load_json(ATTENDANCE_FILE, [])

    date = request.values.get("date")
    if not date:
        date = datetime.date.today().isoformat()
    time = request.values.get("time", "")
    boss = request.values.get("boss", "")

    boss_norm = normalize_boss_name(boss)
    day_attendance = [a for a in attendance if a["date"] == date]

    search = request.values.get("search", "").strip()
    filtered_members = members
    if search:
        filtered_members = [m for m in members if search.lower() in m["닉네임"].lower()]

    if request.method == "POST":
        action = request.form.get("action", "save")
        form_time = request.form.get("time", "")
        form_boss = request.form.get("boss", "")
        form_boss_norm = normalize_boss_name(form_boss)
        form_participants = request.form.getlist("participants")
        if action == "delete" and form_boss:
            attendance = [a for a in attendance if not (a["date"] == date and a["time"] == form_time and normalize_boss_name(a["boss"]) == form_boss_norm)]
            save_json(ATTENDANCE_FILE, attendance)
            return redirect(url_for("calendar", date=date))
        elif form_boss:
            record = next((a for a in attendance if a["date"] == date and a["time"] == form_time and normalize_boss_name(a["boss"]) == form_boss_norm), None)
            if record:
                record["participants"] = form_participants
            else:
                attendance.append({"date": date, "time": form_time, "boss": form_boss_norm, "participants": form_participants})
            save_json(ATTENDANCE_FILE, attendance)
            redirect_args = {"date": date, "time": form_time, "boss": form_boss}
            if search:
                redirect_args["search"] = search
            return redirect(url_for("attendance_manage", **redirect_args))

    record = next((a for a in attendance if a["date"] == date and a["time"] == time and normalize_boss_name(a["boss"]) == boss_norm), None)
    participants = record["participants"] if record else []

    return render_template(
        "attendance_manage.html",
        date=date, time=time, boss=boss,
        day_attendance=day_attendance,
        members=filtered_members,
        participants=participants
    )

@app.route("/save_participant", methods=["POST"])
@login_required
def save_participant():
    data = request.json
    date = data["date"]
    time = data["time"]
    boss = data["boss"]
    nick = data["nick"]
    checked = data["checked"]

    attendance = load_json(ATTENDANCE_FILE, [])
    boss_norm = normalize_boss_name(boss)
    record = next((a for a in attendance if a["date"] == date and a["time"] == time and normalize_boss_name(a["boss"]) == boss_norm), None)
    if record:
        if checked:
            if nick not in record["participants"]:
                record["participants"].append(nick)
        else:
            if nick in record["participants"]:
                record["participants"].remove(nick)
        save_json(ATTENDANCE_FILE, attendance)
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/attendance/participants")
@login_required
def attendance_participants():
    date = request.args.get("date")
    time = request.args.get("time")
    boss = request.args.get("boss")
    if not date or not time or not boss:
        return "필수 값 누락", 400

    attendance = load_json(ATTENDANCE_FILE, [])
    boss_norm = normalize_boss_name(boss)
    record = next(
        (a for a in attendance if a["date"] == date and a["time"] == time and normalize_boss_name(a["boss"]) == boss_norm),
        None,
    )
    members = load_members()

    if not record:
        return render_template(
            "attendance_participants.html",
            boss_name=boss,
            date=date,
            time=time,
            members=members,
            participants=[],
        )
    return render_template(
        "attendance_participants.html",
        boss_name=boss,
        date=date,
        time=time,
        members=members,
        participants=record["participants"],
    )

def get_ranking(start_date, end_date, bosses=None):
    attendance = load_json(ATTENDANCE_FILE, [])
    counter = Counter()
    bosses_norm = set([normalize_boss_name(b) for b in bosses]) if bosses else None
    for a in attendance:
        adate = a["date"]
        boss_norm = normalize_boss_name(a["boss"])
        if start_date <= adate <= end_date:
            if not bosses_norm or boss_norm in bosses_norm:
                counter.update(a["participants"])
    return counter.most_common()

@app.route("/ranking", methods=["GET"])
@login_required
def ranking():
    today = datetime.date.today()
    week_start = (today - datetime.timedelta(days=today.weekday()))
    week_end = week_start + datetime.timedelta(days=6)
    last_week_start = week_start - datetime.timedelta(days=7)
    last_week_end = week_start - datetime.timedelta(days=1)
    month_start = today.replace(day=1)
    month_end = (month_start + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
    last_month_end = month_start - datetime.timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    period = request.args.get("period", "week")
    start_date = None
    end_date = None
    if period == "week":
        start, end = week_start.isoformat(), week_end.isoformat()
    elif period == "last_week":
        start, end = last_week_start.isoformat(), last_week_end.isoformat()
    elif period == "month":
        start, end = month_start.isoformat(), month_end.isoformat()
    elif period == "last_month":
        start, end = last_month_start.isoformat(), last_month_end.isoformat()
    elif period == "custom":
        start = request.args.get("start_date", week_start.isoformat())
        end = request.args.get("end_date", week_end.isoformat())
        start_date, end_date = start, end
    else:
        start, end = week_start.isoformat(), week_end.isoformat()

    attendance = load_json(ATTENDANCE_FILE, [])
    boss_set = sorted({normalize_boss_name(a["boss"]) for a in attendance})
    bosses = request.args.getlist("boss")
    filter_bosses = bosses if bosses else boss_set

    ranking_list = get_ranking(start, end, filter_bosses)
    return render_template(
        "ranking.html",
        ranking=ranking_list,
        boss_set=boss_set,
        selected_bosses=filter_bosses,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )

@app.route("/boss_schedule")
@login_required
def boss_schedule():
    schedules = load_json("schedule.json", [])
    attendance = load_json("attendance.json", [])
    attendance_map = {(a["date"], a["time"], normalize_boss_name(a["boss"])): len(a["participants"]) for a in attendance}
    return render_template("boss_schedule.html", schedules=schedules, attendance_map=attendance_map)

@app.route("/distribute")
@login_required
def distribute():
    members = load_members()
    return render_template("distribute.html", members=members)

@app.route("/distribute_result", methods=["POST"])
@login_required
def distribute_result():
    members = load_members()

    attend_nicks = request.form.getlist("attend")
    item_dia = int(request.form.get("item_dia", 0))
    strong_dia = int(request.form.get("strong_dia", 0))
    healer_bonus = int(request.form.get("heal_bonus", 0))
    myth_unit = int(request.form.get("myth_unit", 0))

    target_members = []  # 👈 무조건 함수 안에서 선언
    for m in members:
        if m["닉네임"] not in attend_nicks:
            continue
        healer_extra = int(request.form.get(f"healer_bonus_{m['닉네임']}", 0))
        myth_extra = int(request.form.get(f"myth_bonus_{m['닉네임']}", 0))
        donation = int(request.form.get(f"donation_{m['닉네임']}", 0))
        myth_count = int(m.get("신화개수", 0))
        is_healer = m["직업"] == "디바인캐스터"
        # 👇 힐러+신화1개 이상이면 추가금 0
        if is_healer and myth_count >= 1:
            healer_extra = 0
        target_members.append({
            "닉네임": m["닉네임"],
            "직업": m["직업"],
            "신화개수": myth_count,
            "힐러추가": healer_extra if is_healer else 0,
            "신화추가": myth_extra,
            "기부": donation,
        })

    n = len(target_members)
    total_dia = item_dia + strong_dia
    total_healer = sum(x["힐러추가"] for x in target_members)
    total_myth = sum(x["신화추가"] for x in target_members)
    total_donation = sum(x["기부"] for x in target_members)
    base_share = 0
    if n > 0:
        base_share = (total_dia - total_healer - total_myth + total_donation) // n

    for m in target_members:
        m["분배금"] = base_share + m["힐러추가"] + m["신화추가"] - m["기부"]

    missed = [m["닉네임"] for m in members if m["닉네임"] not in attend_nicks]

    result = {
        "members": target_members,
        "total": total_dia,
        "shared": base_share,
        "strong_dia": strong_dia,
        "healer_bonus": healer_bonus,
        "myth_unit": myth_unit,
        "missed": missed,
    }
    return render_template("distribute_result.html", result=result)

@app.route("/download/attendance")
@login_required
def download_attendance():
    return send_file(ATTENDANCE_FILE, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
