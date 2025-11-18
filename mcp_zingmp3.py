# File: mcp_zingmp3.py
# PHIÊN BẢN MỞ RỘNG: Hỗ trợ Tải & Convert MP3 tự động (không cần cài FFmpeg thủ công)

import mcp.types as types
from mcp.server.fastmcp import FastMCP
import re
import requests
import json
import sys
import os
import subprocess
import shutil
from typing import List, Dict, Any

# --- 1. TÍCH HỢP STATIC-FFMPEG (QUAN TRỌNG NHẤT) ---
# Đoạn này sẽ tự tải FFmpeg nếu máy chưa có (chạy tốt trên GitHub Action/Codespaces)
try:
    import static_ffmpeg
    static_ffmpeg.add_paths() # Tự động thêm ffmpeg vào PATH
    print("SYSTEM: Đã tích hợp static-ffmpeg thành công.")
except ImportError:
    print("CẢNH BÁO: Chưa cài 'static-ffmpeg'. Hãy thêm vào pyproject.toml", file=sys.stderr)
# ---------------------------------------------------

import cloudscraper 

try:
    from ytmusicapi import YTMusic
    import yt_dlp
except ImportError:
    print("LỖI NGHIÊM TRỌNG: Thiếu thư viện ytmusicapi hoặc yt-dlp.", file=sys.stderr)
    sys.exit(1)

# ===================================================================
# NỘI DUNG TỪ zmp3.py (LOGIC CỦA ZING MP3 - GIỮ NGUYÊN)
# ===================================================================
import time, hashlib, hmac
from urllib.parse import quote

URL = "https://zingmp3.vn"

# --- Logic tải cấu hình (ĐÃ FIX CỨNG) ---
try:
    version = "1.16.5"
    akey = "X5BM3w8N7MKozC0B85o4KMlzLZKhV00y"
    skey = "acOrvUS15XRW2o9JksiK1KgQ6Vbds8ZW"
    
    if not all([version, akey, skey]):
        raise ValueError("Giá trị fix cứng bị thiếu")

except Exception as e:
    print(f"LỖI NGHIÊM TRỌNG: Không thể tải cấu hình fix cứng Zing: {e}", file=sys.stderr)
    sys.exit(1)

# --- LOGIC SIGNATURE ---
p = {"ctime", "id", "type", "page", "count", "version"}
session = cloudscraper.create_scraper() 
_cookie = None

# Khởi tạo YTMusic
try:
    ytmusic = YTMusic()
except Exception as e:
    print(f"LỖI: Không thể khởi tạo YTMusic: {e}", file=sys.stderr)

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
    r = session.get(URL, timeout=10) 
    _cookie = "; ".join(f"{k}={v}" for k, v in r.cookies.items()) or None
    return _cookie

def zingmp3(path, extra=None):
    now = str(int(time.time()))
    params = {"ctime": now, "version": version, "apiKey": akey, **(extra or {})}
    params["sig"] = get_sig(path, params)
    cookie_header = get_cookie()
    headers = {"Cookie": cookie_header} if cookie_header else {}
    return session.get(f"{URL}{path}", headers=headers, params=params, timeout=10).json()

# api wrapper
search_song = lambda q, count=10: zingmp3("/api/v2/search", {"q": q, "type": "song", "count": count, "allowCorrect": 1})
get_song = lambda song_id: zingmp3("/api/v2/song/get/info", {"id": song_id})
get_stream = lambda song_id: zingmp3("/api/v2/song/get/streaming", {"id": song_id})
get_lyric = lambda song_id: zingmp3("/api/v2/lyric/get/lyric", {"id": song_id})

# ===================================================================
# NỘI DUNG HỖ TRỢ
# ===================================================================

def parse_lrc_to_json(lrc_content: str) -> List[Dict[str, Any]]:
    lines_json = []
    lrc_line_regex = re.compile(r'\[(\d{2}):(\d{2})[.:]?(\d{2,3})?\](.*)')
    for line in lrc_content.splitlines():
        match = lrc_line_regex.match(line)
        if match:
            minutes, seconds = int(match.group(1)), int(match.group(2))
            hundredths = int(match.group(3) or 0)
            lyric_text = match.group(4).strip()
            start_time_ms = (minutes * 60 * 1000) + (seconds * 1000)
            start_time_ms += (hundredths * 10) if len(str(hundredths)) == 2 else hundredths
            if lyric_text:
                lines_json.append({"startTime": start_time_ms, "data": lyric_text})
    return lines_json

# Khởi tạo server
server = FastMCP("music-tools-server") 

# ===================================================================
# === CÔNG CỤ TÌM KIẾM & THÔNG TIN (CŨ) ===
# ===================================================================

@server.tool()
def search_zing_songs(query: str, count: int = 5) -> List[Dict[str, str]]:
    """Tìm kiếm bài hát trên Zing MP3."""
    try:
        search_data = search_song(query, count=count) 
        if search_data.get("err", 0) != 0 or not search_data.get("data"): return []
        items = search_data["data"].get("items", [])
        return [{"id": s.get("encodeId"), "title": s.get("title"), "artists": s.get("artistsNames")} for s in items]
    except Exception as e:
        print(f"Lỗi search Zing: {e}", file=sys.stderr)
        return []

@server.tool()
def get_zing_song_details(song_id: str) -> Dict[str, Any]:
    """Lấy chi tiết bài hát Zing (Stream URL, Lyric, Info)."""
    if not song_id: return {"error": "Thiếu song_id"}
    try:
        # Lấy Info
        s_info = get_song(song_id)
        if s_info.get("err") != 0: return {"error": s_info.get("msg")}
        d = s_info.get("data", {})
        
        # Lấy Stream
        st_info = get_stream(song_id)
        stream_url = st_info.get("data", {}).get("128", "") if st_info.get("err") == 0 else ""
        if not stream_url: stream_url = "VIP/Error"

        # Lấy Lyric (Rút gọn logic cho ngắn)
        lyric_json = []
        l_info = get_lyric(song_id)
        if l_info.get("err") == 0:
            ld = l_info.get("data", {})
            if ld.get("lines"): lyric_json = ld["lines"]
            elif ld.get("file"):
                try:
                    lyric_json = parse_lrc_to_json(session.get(ld["file"]).text)
                except: pass

        return {
            "id": d.get("encodeId"), "title": d.get("title"), "artists": d.get("artistsNames"),
            "stream_url": stream_url, "lyric_json": lyric_json
        }
    except Exception as e: return {"error": str(e)}

@server.tool()
def search_youtube_music(query: str, count: int = 5) -> List[Dict[str, str]]:
    """Tìm kiếm YouTube Music."""
    if 'ytmusic' not in globals(): return [{"error": "YTMusic chưa init"}]
    try:
        res = ytmusic.search(query=query, filter='songs', limit=count)
        return [{"id": s.get('videoId'), "title": s.get('title'), "artists": ", ".join([a['name'] for a in s.get('artists', [])])} for s in res]
    except Exception as e: return [{"error": str(e)}]

# ===================================================================
# === CÁC TOOL MỚI: DOWNLOAD & CONVERT MP3 (AUTO FFMPEG) ===
# ===================================================================

@server.tool()
def download_youtube_as_mp3(video_id: str) -> str:
    """
    Tải audio từ YouTube và convert sang MP3 (128kbps).
    Trả về đường dẫn file trên server.
    """
    if not video_id: return "Lỗi: Thiếu video_id"
    
    output_folder = "downloads"
    os.makedirs(output_folder, exist_ok=True)
    
    try:
        # yt-dlp sẽ tự tìm thấy ffmpeg do static-ffmpeg cài đặt
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{output_folder}/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'quiet': True,
            'noplaylist': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            filename = ydl.prepare_filename(info)
            final_name = os.path.splitext(filename)[0] + ".mp3"
            return f"Thành công! File tại: {final_name}"
            
    except Exception as e:
        return f"Lỗi download YouTube: {str(e)}"

@server.tool()
def download_zing_as_mp3(song_id: str) -> str:
    """
    Tải bài hát từ Zing MP3 và convert stream sang file MP3 vật lý.
    Input: song_id (ví dụ: ZU6ZO8W0)
    """
    # 1. Lấy thông tin để có Stream URL
    details = get_zing_song_details(song_id)
    if "error" in details:
        return f"Lỗi Zing: {details['error']}"
    
    stream_url = details.get("stream_url")
    title = details.get("title", f"zing_song_{song_id}")
    
    if not stream_url or "http" not in stream_url:
        return "Lỗi: Không lấy được link stream (Có thể là bài VIP)."

    # 2. Chuẩn bị đường dẫn lưu
    output_folder = "downloads"
    os.makedirs(output_folder, exist_ok=True)
    safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip()
    output_path = os.path.join(output_folder, f"{safe_title}.mp3")

    # 3. Dùng FFmpeg để tải và convert
    # static-ffmpeg đảm bảo lệnh 'ffmpeg' gọi được
    command = [
        "ffmpeg", "-y",          # Ghi đè
        "-i", stream_url,        # Input từ URL
        "-vn",                   # Bỏ hình
        "-ar", "44100",          # Tần số mẫu
        "-ac", "2",              # Stereo
        "-b:a", "128k",          # Bitrate
        output_path              # Output file
    ]

    try:
        # Chạy lệnh, timeout 60s để tránh treo
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        return f"Thành công! File Zing MP3 tại: {output_path}"
    except subprocess.TimeoutExpired:
        return "Lỗi: Tải quá lâu (Timeout)."
    except subprocess.CalledProcessError as e:
        return f"Lỗi FFmpeg: {e}"
    except FileNotFoundError:
        return "Lỗi: Không tìm thấy lệnh ffmpeg (static-ffmpeg chưa chạy?)"
    except Exception as e:
        return f"Lỗi hệ thống: {str(e)}"

# ===================================================================
# === MAIN ===
# ===================================================================

def main():
    print("Đang khởi động Music MCP Server (Zing + YouTube)...")
    print(f"Thư mục hiện tại: {os.getcwd()}")
    server.run()

if __name__ == "__main__":
    main()
