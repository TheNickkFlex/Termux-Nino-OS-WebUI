#!/data/data/com.termux/files/usr/bin/bash

apt update -y
apt install -y python3 ttyd tigervnc lxqt root-repo x11-repo termux-api tmux make golang npm udocker python-cryptography openssl

export ANDROID_API_LEVEL=24
pip install cryptography

export ANDROID_API_LEVEL=28
pip install websockify

cd ~/Termux-Nino-OS-WebUI/FileBrowserQuantum/backend
make
make build
./filebrowser &

sleep 2

cd ~/Nano-OS-Interface/noVNC
vncpasswd
vncserver -kill :0 2>/dev/null || true
vncserver :0 -xstartup "lxqt-session" &
sleep 3

nohup websockify --web . 6080 localhost:5900 >/dev/null 2>&1 &
sleep 1

cd $HOME
nohup ttyd --writable -p 7681 bash -c 'SHELL=$(which bash) tmux new-session -A -s remote' >/dev/null 2>&1 &
sleep 1

cd ~/Nano-OS-Interface
exec python3 server.py
