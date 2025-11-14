# File: mcp_zingmp3.py
# ĐÃ GỘP CHUNG TỪ zmp3.py và mcp_zingmp3.py

import mcp.types as types
from mcp.server.fastmcp import FastMCP
import re
import requests
import json
import sys
from typing import List, Dict, Any

# ===================================================================
# NỘI DUNG TỪ zmp3.py (ĐÃ DÁN TRỰC TIẾP VÀO ĐÂY)
# ===================================================================
import time, hashlib, hmac, os
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

# ===================================================================
# NỘI DUNG TỪ mcp_zingmp3.py (ĐÃ BỎ IMPORT LỖI)
# ===================================================================

# --- HÀM HỖ TRỢ PHÂN TÍCH LYRIC ---
def parse_lrc_to_json(lrc_content: str) -> List[Dict[str, Any]]:
    """
    Hàm này phân tích nội dung file .lrc thô
    thành một cấu trúc JSON { startTime, data }
    """
    lines_json = []
    lrc_line_regex = re.compile(r'\[(\d{2}):(\d{2})[.:]?(\d{2,3})?\](.*)')
    
    for line in lrc_content.splitlines():
        match = lrc_line_regex.match(line)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            hundredths = int(match.group(3) or 0)
            lyric_text = match.group(4).strip()
            
            start_time_ms = (minutes * 60 * 1000) + (seconds * 1000)
            if len(str(hundredths)) == 2:
                start_time_ms += (hundredths * 10)
            elif len(str(hundredths)) == 3:
                start_time_ms += hundredths

            if lyric_text:
                lines_json.append({
                    "startTime": start_time_ms,
                    "data": lyric_text
                })
    return lines_json
# --- KẾT THÚC HÀM HỖ TRỢ ---


# Khởi tạo máy chủ MCP
server = FastMCP("zingmp3-tools")

@server.tool()
def search_zing_songs(query: str, count: int = 5) -> List[Dict[str, str]]:
    """
    Tìm kiếm bài hát trên Zing MP3.
    Trả về một danh sách các bài hát khớp với từ khóa.
    """
    try:
        # HÀM search_song() GIỜ ĐÃ TỒN TẠI TRONG CÙNG FILE NÀY
        search_data = search_song(query, count=count) 
        if not search_data.get("data") or not search_data["data"].get("items"):
            return []
        
        songs_list = search_data["data"]["items"]
        results = []
        for song in songs_list:
            results.append({
                "id": song.get("encodeId"),
                "title": song.get("title"),
                "artists": song.get("artistsNames"),
                "thumbnail": song.get("thumbnailM")
            })
        return results
    except Exception as e:
        print(f"Lỗi khi tìm kiếm Zing MP3: {e}", file=sys.stderr)
        return []

@server.tool()
def get_zing_song_details(song_id: str) -> Dict[str, Any]:
    """
    Lấy thông tin chi tiết, link stream 128kbps và lời bài hát (dạng JSON)
    cho một song_id cụ thể của Zing MP3.
    """
    if not song_id:
        return {"error": "Thiếu song_id"}

    try:
        # CÁC HÀM get_song(), get_stream(), get_lyric() GIỜ ĐÃ TỒN TẠI Ở TRÊN
        song_info = get_song(song_id)
        if song_info.get("err") != 0:
            return {"error": song_info.get("msg", "Lỗi khi lấy thông tin bài hát")}
        data = song_info.get("data", {})
        
        composers = data.get("composers", [])
        author_names = ", ".join([c["name"] for c in composers if c.get("name")]) or "Không rõ"

        stream_info = get_stream(song_id)
        stream_url = stream_info.get("data", {}).get("128")
        if not stream_url:
            stream_url = f"Không thể lấy link (Lỗi: {stream_info.get('msg', 'Không khả dụng')})"
        elif stream_url == "VIP":
            stream_url = "Đây là bài hát VIP, cần tài khoản Premium."

        lyric_info = get_lyric(song_id)
        lyric_json = []
        
        if lyric_info.get("err") == 0 and lyric_info.get("data"):
            lyric_data = lyric_info.get("data", {})
            if lyric_data.get("lines"):
                lyric_json = lyric_data["lines"]
            elif lyric_data.get("file"):
                file_url = lyric_data["file"]
                try:
                    resp = requests.get(file_url, timeout=5)
                    if resp.ok:
                        lrc_content = resp.text
                        lyric_json = parse_lrc_to_json(lrc_content)
                except Exception as e:
                    print(f"Lỗi khi phân tích file LRC: {e}", file=sys.stderr)

        full_details = {
            "id": data.get("encodeId"),
            "title": data.get("title"),
            "artists": data.get("artistsNames", "Không rõ"),
            "author": author_names,
            "thumbnail": data.get("thumbnailM"),
            "stream_url": stream_url,
            "lyric": lyric_json
        }
        
        return full_details

    except Exception as e:
        print(f"Lỗi khi lấy chi tiết bài hát: {e}", file=sys.stderr)
        return {"error": str(e)}

def main():
    """Hàm main để chạy server."""
    print("Đang khởi động Zing MP3 MCP Server (Phiên bản GỘP)...")
    server.run()

if __name__ == "__main__":
    main()