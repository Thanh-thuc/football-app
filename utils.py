import json
import os

DB_FILE = "db.json"

# Đọc dữ liệu từ db.json
def load_data():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump({"players": [], "sessions": []}, f, ensure_ascii=False, indent=2)
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# Ghi dữ liệu vào db.json
def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Lấy danh sách người chơi
def get_players():
    return load_data().get("players", [])

# Lấy danh sách phiên đăng ký
def get_sessions():
    return load_data().get("sessions", [])

# Thêm người chơi mới
def add_player(player):
    data = load_data()
    data["players"].append(player)
    save_data(data)

# Thêm phiên đăng ký mới
def add_session(session):
    data = load_data()
    data["sessions"].append(session)
    save_data(data)
