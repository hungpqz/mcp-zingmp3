# File: mcp_zingmp3.py
# Máy chủ MCP cho Zing MP3
# Yêu cầu: Đặt file này chung thư mục với zmp3.py và config.json
# Yêu cầu cài đặt thư viện: pip install mcp requests

import mcp.types as types
from mcp.server.fastmcp import FastMCP
import re
import requests
import json
import sys
from typing import List, Dict, Any

# Import các hàm từ file zmp3.py của bạn
try:
    from zmp3 import search_song, get_song, get_stream, get_lyric
except ImportError:
    print("LỖI NGHIÊM TRỌNG: Không tìm thấy file zmp3.py.", file=sys.stderr)
    print("Hãy đảm bảo file zmp3.py và config.json nằm chung thư mục với mcp_zingmp3.py", file=sys.stderr)
    sys.exit(1) # Dừng nếu không có thư viện zmp3

# --- HÀM HỖ TRỢ PHÂN TÍCH LYRIC ---
# (Lấy từ file app.py của bạn, rất quan trọng để xử lý file .lrc)
def parse_lrc_to_json(lrc_content: str) -> List[Dict[str, Any]]:
    """
    Hàm này phân tích nội dung file .lrc thô
    thành một cấu trúc JSON { startTime, data }
    """
    lines_json = []
    # Regex để tìm [phút:giây.miligiây]lời
    # Hỗ trợ cả [mm:ss.xx] và [mm:ss]
    lrc_line_regex = re.compile(r'\[(\d{2}):(\d{2})[.:]?(\d{2,3})?\](.*)')
    
    for line in lrc_content.splitlines():
        match = lrc_line_regex.match(line)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            hundredths = int(match.group(3) or 0)
            lyric_text = match.group(4).strip()

            # Chuyển đổi tất cả sang miligiây
            start_time_ms = (minutes * 60 * 1000) + (seconds * 1000)
            if len(str(hundredths)) == 2: # dạng .xx
                start_time_ms += (hundredths * 10)
            elif len(str(hundredths)) == 3: # dạng .xxx
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
        search_data = search_song(query, count=count)
        if not search_data.get("data") or not search_data["data"].get("items"):
            return []  # Trả về mảng rỗng nếu không có kết quả
        
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
        return [] # Trả về mảng rỗng khi có lỗi

@server.tool()
def get_zing_song_details(song_id: str) -> Dict[str, Any]:
    """
    Lấy thông tin chi tiết, link stream 128kbps và lời bài hát (dạng JSON)
    cho một song_id cụ thể của Zing MP3.
    """
    if not song_id:
        return {"error": "Thiếu song_id"}

    try:
        # 1. Lấy thông tin cơ bản
        song_info = get_song(song_id)
        if song_info.get("err") != 0:
            return {"error": song_info.get("msg", "Lỗi khi lấy thông tin bài hát")}
        data = song_info.get("data", {})
        
        # Lấy tên tác giả
        composers = data.get("composers", [])
        author_names = ", ".join([c["name"] for c in composers if c.get("name")]) or "Không rõ"

        # 2. Lấy link stream
        stream_info = get_stream(song_id)
        stream_url = stream_info.get("data", {}).get("128")
        if not stream_url:
            stream_url = f"Không thể lấy link (Lỗi: {stream_info.get('msg', 'Không khả dụng')})"
        elif stream_url == "VIP":
            stream_url = "Đây là bài hát VIP, cần tài khoản Premium."

        # 3. Lấy lyric (sử dụng logic từ app.py)
        lyric_info = get_lyric(song_id)
        lyric_json = []  # Mặc định là mảng rỗng
        
        if lyric_info.get("err") == 0 and lyric_info.get("data"):
            lyric_data = lyric_info.get("data", {})

            if lyric_data.get("lines"):
                # Cách 1: API trả về sẵn JSON, chỉ cần lấy
                lyric_json = lyric_data["lines"]
            
            elif lyric_data.get("file"):
                # Cách 2: API trả về file .lrc, server sẽ tải và phân tích
                file_url = lyric_data["file"]
                try:
                    resp = requests.get(file_url, timeout=5)
                    if resp.ok:
                        lrc_content = resp.text
                        lyric_json = parse_lrc_to_json(lrc_content)
                except Exception as e:
                    print(f"Lỗi khi phân tích file LRC: {e}", file=sys.stderr)
                    # Để lyric_json là mảng rỗng

        # 4. Tổng hợp kết quả
        full_details = {
            "id": data.get("encodeId"),
            "title": data.get("title"),
            "artists": data.get("artistsNames", "Không rõ"),
            "author": author_names,
            "thumbnail": data.get("thumbnailM"),
            "stream_url": stream_url,
            "lyric": lyric_json  # <-- TRẢ VỀ MẢNG JSON
        }
        
        return full_details

    except Exception as e:
        print(f"Lỗi khi lấy chi tiết bài hát: {e}", file=sys.stderr)
        return {"error": str(e)}

def main():
    """Hàm main để chạy server."""
    print("Đang khởi động Zing MP3 MCP Server...")
    print("Đảm bảo zmp3.py và config.json ở cùng thư mục.")
    server.run()

if __name__ == "__main__":
    main()