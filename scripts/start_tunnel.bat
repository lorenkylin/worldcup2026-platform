@echo off
echo [tunnel] 启动 Cloudflare Tunnel，映射到 http://127.0.0.1:8000
echo [tunnel] 请确保本地服务已启动：python scripts/start_server.py
echo [tunnel] 如果提示找不到 cloudflared，请把 cloudflared.exe 放到 C:\tools\ 或当前 scripts\ 目录
echo.

if exist "scripts\cloudflared.exe" (
    scripts\cloudflared.exe tunnel --url http://127.0.0.1:8000
) else if exist "cloudflared.exe" (
    cloudflared.exe tunnel --url http://127.0.0.1:8000
) else (
    cloudflared tunnel --url http://127.0.0.1:8000
)

pause
