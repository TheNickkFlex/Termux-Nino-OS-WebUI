#!/data/data/com.termux/files/usr/bin/bash

echo "=== Instalando dependencias ==="
apt update -y
apt install -y python3 ttyd tigervnc lxqt root-repo x11-repo termux-api tmux make golang npm udocker

echo "A Aplicacao Depende Do Termux-API, Tenha Certeza De Ter-lo Instalado Em Seu Android!"

echo "=== Instalando cryptography (API 24) ==="
export ANDROID_API_LEVEL=24
pip install cryptography

echo "=== Instalando websockify (API 28) ==="
export ANDROID_API_LEVEL=28
pip install websockify

echo "=== Iniciando filebrowser dentro do proot (background) ==="
cd ~/Nano-OS-Interface/FileBrowserQuantum/backend
./filebrowser &

sleep 2

echo "=== Iniciando VNC ==="
cd ~/Nano-OS-Interface/noVNC
vncserver -kill :0 2>/dev/null || true
vncserver :0 -xstartup "lxqt-session" &
sleep 3

echo "=== Iniciando websockify ==="
nohup websockify --web . 6080 localhost:5900 >/dev/null 2>&1 &
sleep 1

echo "=== Iniciando ttyd (Termux) ==="
cd $HOME
nohup ttyd --writable -p 7681 bash -c 'SHELL=$(which bash) tmux new-session -A -s remote' >/dev/null 2>&1 &
sleep 1

echo "=== Iniciando server.py ==="
cd ~/Nano-OS-Interface
exec python3 server.py
