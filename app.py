from flask import Flask, render_template, request, redirect, url_for, jsonify
import json, os, time
from datetime import datetime
import pytz

app = Flask(__name__)
LOCK_DURATION = 60  # giây
DB_FILE = "db.json"
ANNOUNCE_FILE = 'data/announcements.json'

def load_announcements():
    if os.path.exists(ANNOUNCE_FILE):
        with open(ANNOUNCE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_announcements(data):
    with open(ANNOUNCE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Kiểm tra và tạo db.json nếu chưa tồn tại
if not os.path.exists(DB_FILE):
    initial_data = {
        "schedules": [],
        "players": []
    }
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(initial_data, f, ensure_ascii=False, indent=2)

def load_data():
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_schedule(date):
    data = load_data()
    for s in data["schedules"]:
        if s["id"] == date:
            return s
    return None

def get_players_for_schedule(date):
    data = load_data()
    schedule = get_schedule(date)
    if not schedule:
        return []

    players = data["players"]
    result = []
    for p in players:
        pid = str(p["id"])
        status = schedule["status"].get(pid)
        if status:
            result.append({
                "id": p["id"],
                "name": p["name"],
                "number": p["number"],
                "position": p["position"],
                "state": status.get("state", "")
            })
    return result

@app.route("/")
def index():
    data = load_data()
    admin_mode = request.args.get("admin") == "1"

    sorted_schedules = sorted(
        data["schedules"],
        key=lambda s: datetime.strptime(f"{s['date']} {s['time']}", "%Y-%m-%d %H:%M"),
        reverse=True
    )
    newest_id = sorted_schedules[0]["id"] if sorted_schedules else None

    # ✅ THÊM: Load thông báo nổi bật
    announcements = load_announcements()
    banner_announcement = next((a for a in announcements if a.get("is_banner")), None)

    banner_announcement = None
    all_announcements = load_announcements()
    for ann in all_announcements:
        if ann.get("is_banner"):
            banner_announcement = ann
            break

    return render_template(
        "index.html",
        schedules=sorted_schedules,
        admin=admin_mode,
        newest_id=newest_id,
        banner_announcement=banner_announcement
    )
@app.route("/register/<date>", methods=["GET", "POST"])
def register(date):
    data = load_data()
    schedule = next((s for s in data["schedules"] if s["id"] == date), None)
    if not schedule:
        return f"Không tìm thấy ngày {date}", 404

    players = sorted(data["players"], key=lambda p: p["order"])
    statuses = schedule["status"]
    admin_mode = request.args.get("admin") == "1"
    vn_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    now = time.time()

    locked_at_ts = schedule.get("locked_at", 0)

    # Nếu có locked_at thì chuyển sang datetime có timezone
    if locked_at_ts:
        locked_at_utc = datetime.utcfromtimestamp(locked_at_ts).replace(tzinfo=pytz.utc)
        locked_at_vn = locked_at_utc.astimezone(vn_tz)
        locked_at_global = int(locked_at_vn.timestamp())
    else:
        locked_at_global = 0
    
    is_locked = not admin_mode and now > locked_at_global
         
    if request.method == "POST":
        for player in players:
            pid = str(player["id"])
            current = statuses.get(pid, {})
            lock_time = current.get("locked_at", 0)
            is_player_locked = lock_time and (now - lock_time > LOCK_DURATION)

            # Nếu không phải admin và đã bị khóa thì bỏ qua
            if not admin_mode and is_player_locked:
                continue

            # Lấy dữ liệu mới từ form
            state = request.form.get(f"state_{pid}", current.get("state", ""))
            note = request.form.get(f"note_{pid}", current.get("note", ""))
            reason = request.form.get(f"reason_{pid}", current.get("reason", ""))

            # Nếu trạng thái thay đổi và chưa từng bị khóa, cập nhật locked_at
            if not admin_mode:
                if state in ["join", "busy"]:
                    # Nếu trước đó chưa bị khoá thì bắt đầu tính thời gian
                    if not lock_time:
                        lock_time = now
                elif state == "":
                    # Nếu chọn lại thành "chưa chọn", reset thời gian khoá
                    lock_time = 0

            statuses[pid] = {
                "state": state,
                "note": note,
                "reason": reason,
                "locked_at": lock_time or 0
            }

        save_data(data)
        return redirect(url_for("register", date=date) + ("?admin=1" if admin_mode else ""))

    if locked_at_global:
        locked_at_dt = datetime.fromtimestamp(locked_at_global).astimezone(vn_tz)
        locked_datetime_str = locked_at_dt.strftime("%Y-%m-%d %H:%M")
    else:
        locked_datetime_str = "Chưa đặt"
    return render_template(
        "register.html",
        players=players,
        schedule=schedule,
        statuses=statuses,
        lock_duration=LOCK_DURATION,
        admin=admin_mode,
        now=now,
        locked_at_global=locked_at_global,
        is_locked=is_locked,
        locked_datetime_str=locked_datetime_str
    )

@app.route("/register/<date>/remove/<int:player_id>", methods=["POST"])
def remove_player_from_session(date, player_id):
    admin_mode = request.args.get("admin") == "1"
    if not admin_mode:
        return "Không có quyền xoá", 403

    data = load_data()
    schedule = next((s for s in data["schedules"] if s["id"] == date), None)
    if not schedule:
        return f"Không tìm thấy buổi đá {date}", 404

    pid = str(player_id)
    if pid in schedule["status"]:
        del schedule["status"][pid]

    save_data(data)
    return redirect(url_for("register", date=date) + "?admin=1")

@app.route("/register/<date>/add/<int:player_id>", methods=["POST"])
def add_player_to_session(date, player_id):
    admin_mode = request.args.get("admin") == "1"
    if not admin_mode:
        return "Không có quyền thêm", 403

    data = load_data()
    player = next((p for p in data["players"] if p["id"] == player_id), None)
    if not player:
        return f"Không tìm thấy cầu thủ", 404

    schedule = next((s for s in data["schedules"] if s["id"] == date), None)
    if not schedule:
        return f"Không tìm thấy buổi đá", 404

    pid = str(player_id)
    if pid not in schedule["status"]:
        schedule["status"][pid] = {
            "state": "",
            "note": "",
            "reason": "",
            "locked_at": 0
        }

    save_data(data)
    return redirect(url_for("register", date=date) + "?admin=1")

@app.route("/create", methods=["GET", "POST"])
def create():
    data = load_data()
    if request.method == "POST":
        date = request.form.get("date")
        time_ = request.form.get("time")
        field = request.form.get("location")       # ✅ khớp name="location"
        map_link = request.form.get("map_link")    # ✅ khớp name="map_link"
        locked_at_str = request.form.get("locked_at")

        vn_tz = pytz.timezone("Asia/Ho_Chi_Minh")
        locked_at_naive = datetime.fromisoformat(locked_at_str)
        locked_at_local = vn_tz.localize(locked_at_naive)
        locked_at = int(locked_at_local.astimezone(pytz.utc).timestamp())  # lưu UTC


        status = {
            str(player["id"]): {
                "state": "",
                "note": "",
                "reason": "",
                "locked_at": 0
            } for player in data["players"]
        }

        data["schedules"].append({
            "id": date,
            "date": date,
            "time": time_,
            "field": field,
            "map": map_link,
            "locked_at": locked_at,
            "status": status
        })

        save_data(data)
        return redirect(url_for("index"))

    return render_template("create.html")

@app.route("/admin/players", methods=["GET", "POST"])
def admin_players():
    data = load_data()
    players = data["players"]

    if request.method == "POST":
        updated_players = []
        for player in players:
            pid = str(player["id"])
            if request.form.get(f"delete_{pid}"):
                continue
            updated_players.append({
                "id": player["id"],
                "name": request.form.get(f"name_{pid}", ""),
                "position": ",".join(request.form.getlist(f"position_{pid}[]")),
                "number": int(request.form.get(f"number_{pid}", 0)),
                "order": int(request.form.get(f"order_{pid}", 0))
            })

        if request.form.get("new_name"):
            # Tìm ID lớn nhất hiện có và tăng lên 1
            new_id = 1
            if updated_players:
                new_id = max([p["id"] for p in updated_players]) + 1
            
            new_player = {
                "id": new_id,
                "name": request.form["new_name"],
                "position": ",".join(request.form.getlist("new_position[]")),
                "number": int(request.form.get("new_number", 0)),
                "order": int(request.form.get("new_order", 0))
            }
            updated_players.append(new_player)

            # Thêm cầu thủ mới vào tất cả các lịch trình hiện có
            for schedule in data["schedules"]:
                schedule["status"][str(new_id)] = {
                    "state": "",
                    "note": "",
                    "reason": "",
                    "locked_at": 0
                }

        data["players"] = updated_players
        save_data(data)
        return redirect(url_for("admin_players"))

    return render_template("admin_players.html", players=players)

@app.route("/delete/<date>", methods=["POST"])
def delete_schedule(date):
    admin_mode = request.args.get("admin") == "1"
    if not admin_mode:
        return "Không có quyền xoá", 403

    data = load_data()
    data["schedules"] = [s for s in data["schedules"] if s["id"] != date]
    save_data(data)
    return redirect(url_for("index") + "?admin=1")

@app.route("/coach/<date>")
def coach_mode(date):
    schedule = get_schedule(date)
    if not schedule:
        return "Không tìm thấy buổi đá", 404

    data = load_data()
    players = data["players"]
    statuses = schedule.get("status", {})

    # Lấy những người tham gia
    joined_players = [
        p for p in players
        if str(p["id"]) in statuses and statuses[str(p["id"])]["state"] == "join"
    ]

    # Gom theo vị trí
    players_by_position = {}
    for player in joined_players:
        # Đảm bảo position không rỗng để tránh lỗi split
        if player.get("position"):
            for pos in player["position"].split(","):
                pos = pos.strip().upper()
                players_by_position.setdefault(pos, []).append({
                    "id": player["id"],
                    "name": player["name"],
                    "number": player["number"],
                    "position": player["position"]
                })

    return render_template(
        "coach_mode.html",
        schedule=schedule,
        players_by_position=players_by_position,
        all_joined_players=joined_players # THÊM DÒNG NÀY ĐỂ TRUYỀN TẤT CẢ NGƯỜI CHƠI ĐÃ THAM GIA
    )
@app.context_processor
def inject_helpers():
    def get_line_color(pos):
        if pos.startswith("CB") or pos in ["LB", "RB"]:
            return "DEF"
        elif pos in ["GK"]:
            return "GK"
        elif pos in ["CM", "LM", "RM", "DM", "AM"]:
            return "MID"
        elif pos in ["ST", "CF", "SS", "LW", "RW"]:
            return "FWD"
        else:
            return ""

    def format_date_with_weekday(date_str):
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            weekday_vi = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
            weekday = weekday_vi[dt.weekday()]
            return f"{weekday} | {dt.strftime('%d-%m-%Y')}"
        except:
            return date_str

    return dict(get_line_color=get_line_color, format_date_with_weekday=format_date_with_weekday)
@app.route("/about.html")
def about():
    return render_template("about.html")
@app.route('/announcements')
def announcements():
    announcements = load_announcements()
    is_admin = request.args.get('admin') == '1'
    return render_template('announcements.html', announcements=announcements, is_admin=is_admin)
@app.route('/add_announcement', methods=['POST'])
def add_announcement():
    if request.args.get('admin') != '1':
        return "Không có quyền", 403

    announcements = load_announcements()
    new_item = {
        "title": request.form['title'],
        "content": request.form['content'],
        "date": datetime.now().strftime("%d/%m/%Y"),
        "is_banner": 'is_banner' in request.form
    }
    announcements.insert(0, new_item)
    save_announcements(announcements)
    return redirect(url_for('announcements', admin=1))

@app.route('/delete_announcement/<int:index>', methods=['POST'])
def delete_announcement(index):
    if request.args.get('admin') != '1':
        return "Không có quyền", 403

    announcements = load_announcements()
    if 0 <= index < len(announcements):
        del announcements[index]
        save_announcements(announcements)
    return redirect(url_for('announcements', admin=1))
@app.route('/toggle_banner/<int:index>', methods=['POST'])
def toggle_banner(index):
    if request.args.get('admin') != '1':
        return "Không có quyền", 403

    announcements = load_announcements()
    if 0 <= index < len(announcements):
        # Đảo trạng thái ghim nổi
        announcements[index]['is_banner'] = not announcements[index].get('is_banner', False)
        save_announcements(announcements)

    return redirect(url_for('announcements', admin=1))
# Route để lấy đội hình theo ngày thi đấu
@app.route('/get_lineup/<schedule_id>')
def get_lineup(schedule_id):
    with open('db.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    lineup = data.get('lineups', {}).get(schedule_id, {})
    return jsonify(lineup)

# Route để lưu đội hình
@app.route('/save_lineup/<schedule_id>', methods=['POST'])
def save_lineup(schedule_id):
    lineup_data = request.json
    with open('db.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    if 'lineups' not in data:
        data['lineups'] = {}

    data['lineups'][schedule_id] = lineup_data

    with open('db.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({'status': 'ok'})
if __name__ == "__main__":
    app.run(debug=True)