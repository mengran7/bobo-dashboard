@echo off
cd /d "%~dp0"
echo 启动内网穿透中，请稍等...
cloudflared.exe tunnel --url http://localhost:8080
pause
