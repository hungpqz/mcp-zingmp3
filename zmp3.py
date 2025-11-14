# cre by TomDev211
# Đã sửa đổi bởi Gemini để hỗ trợ Biến Môi trường cho MCP

import time, hashlib, hmac, requests, json, os, sys
from urllib.parse import quote

URL = "https://zingmp3.vn"

# --- Logic tải cấu hình an toàn ---

# 1. Ưu tiên đọc từ biến môi trường (an toàn cho server/MCP Hub)
ZING_VERSION = os.environ.get("ZING_VERSION")
ZING_AKEY = os.environ.get("ZING_AKEY_R") # Tên biến 'r' trong config.json
ZING_SKEY = os.environ.get("ZING_SKEY_I") # Tên biến 'i' trong config.json

# 2. Kiểm tra xem các biến có tồn tại không
if all([ZING_VERSION, ZING_AKEY, ZING_SKEY]):
    # Nếu tất cả đều có, gán giá trị từ biến môi trường
    version, akey, skey = ZING_VERSION, ZING_AKEY, ZING_SKEY
else:
    # 3. Nếu không có, thử đọc từ file config.json (để chạy local)
    try:
        cfg = json.load(open("config.json", encoding="utf-8"))
        version, akey, skey = cfg["version"], cfg["r"], cfg["i"]
    except FileNotFoundError:
        # 4. Nếu cả hai đều thất bại, in lỗi và thoát
        print(
            "LỖI NGHIÊM TRỌNG: Không thể tải cấu hình Zing MP3.",
            file=sys.stderr
        )
        print(
            "Hãy đảm bảo file 'config.json' tồn tại",
            "hoặc đặt các biến môi trường: ZING_VERSION, ZING_AKEY_R, ZING_SKEY_I",
            file=sys.stderr
        )
        sys.exit(1) # Thoát tiến trình với mã lỗi

# --- Kết thúc logic tải cấu hình ---


p = {"ctime", "id", "type", "page", "count", "version"}

session, _cookie = requests.Session(), None

# utils
def hash256(s): return hashlib.sha256(s.encode()).hexdigest()
def hmac512(s, key): return hmac.new(key.encode(), s.encode(), hashlib.sha512).hexdigest()

def str_params(params):
    return "".join(f"{quote(k)}={quote(str(v))}" for k, v in sorted(params.items()) if k in p and v not in [None, ""] and len(str(v)) <= 5000)

def get_sig(path, params): 
    return hmac512(path + hash256(str_params(params)), skey)

def get_cookie(force=False):
    global _cookie
    if _cookie and not force: return _cookie
    r = session.get(URL, timeout=5)
    _cookie = "; ".join(f"{k}={v}" for k, v in r.cookies.items()) or None
    return _cookie

def zingmp3(path, extra=None):
    now = str(int(time.time()))
    params = {"ctime": now, "version": version, "apiKey": akey, **(extra or {})}
    params["sig"] = get_sig(path, params)
    headers = {"Cookie": get_cookie()} if get_cookie() else {}
    return session.get(f"{URL}{path}", headers=headers, params=params, timeout=10).json()

# api
chart_home = lambda: zingmp3("/api/v2/page/get/chart-home")
search_song = lambda q, count=10: zingmp3("/api/v2/search", {"q": q, "type": "song", "count": count, "allowCorrect": 1})
get_song = lambda song_id: zingmp3("/api/v2/song/get/info", {"id": song_id})
get_stream = lambda song_id: zingmp3("/api/v2/song/get/streaming", {"id": song_id})
get_lyric = lambda song_id: zingmp3("/api/v2/lyric/get/lyric", {"id": song_id})