from flask import Flask, render_template, request, redirect, url_for
import json, os, time
from datetime import datetime

app = Flask(__name__)
LOCK_DURATION = 60  # giây
DB_FILE = "db.json"

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
    return render_template("index.html", schedules=data["schedules"], admin=admin_mode)

@app.route("/register/<date>", methods=["GET", "POST"])
def register(date):
    data = load_data()
    schedule = next((s for s in data["schedules"] if s["id"] == date), None)
    if not schedule:
        return f"Không tìm thấy ngày {date}", 404

    players = sorted(data["players"], key=lambda p: p["order"])
    statuses = schedule["status"]
    admin_mode = request.args.get("admin") == "1"
    now = time.time()
    locked_at_global = schedule.get("locked_at", 0)
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
            if not admin_mode and not lock_time and state in ["join", "busy"]:
                lock_time = now  # đánh dấu thời gian khóa

            statuses[pid] = {
                "state": state,
                "note": note,
                "reason": reason,
                "locked_at": lock_time or 0
            }

        save_data(data)
        return redirect(url_for("register", date=date) + ("?admin=1" if admin_mode else ""))

    locked_datetime_str = datetime.fromtimestamp(locked_at_global).strftime("%Y-%m-%d %H:%M") if locked_at_global else "Chưa đặt"
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
        date = request.form["date"]
        time_ = request.form["time"]
        field = request.form["field"]
        map_link = request.form["map"]
        # Chuyển đổi định dạng ngày giờ từ ISO 8601 sang timestamp
        # Thêm múi giờ (ví dụ: +07:00 cho Việt Nam) hoặc để UTC tùy theo nhu cầu
        locked_at_str = request.form["locked_at"]
        locked_at = int(datetime.fromisoformat(locked_at_str).timestamp())

        status = {}
        for player in data["players"]:
            status[str(player["id"])] = {
                "state": "",
                "note": "",
                "reason": "",
                "locked_at": 0
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
    return dict(get_line_color=get_line_color)
if __name__ == "__main__":
    app.run(debug=True)