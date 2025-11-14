# Zing MP3 MCP Server

Một máy chủ Model Context Protocol (MCP) cho phép tìm kiếm, lấy link stream và lời bài hát từ Zing MP3.

## Tính năng

- Tìm kiếm bài hát theo từ khóa.
- Lấy link stream 128kbps.
- Lấy lời bài hát (lyric) dưới dạng JSON có timestamp (giống hệt `index.html` của bạn).
- Hoạt động với bất kỳ máy khách MCP nào.

## Sử dụng

Trong tệp cấu hình MCP Hub của bạn (ví dụ `xiaozhi-mcphub`):

```json
"mcpServers": {
    "zingmp3": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/quyenpv/mcp-zingmp3", "mcp-zingmp3"]
    },
    "youtube": {
       ...
    }
}
