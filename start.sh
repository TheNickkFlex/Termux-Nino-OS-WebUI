#!/data/data/com.termux/files/usr/bin/bash

# Forçar renderização por software para o VNC não capotar
export GALLIUM_DRIVER=llvmpipe

apt update -y
apt install -y python3 ttyd tigervnc lxqt root-repo x11-repo termux-api tmux make golang npm udocker python-cryptography openssl

export ANDROID_API_LEVEL=24
pip install cryptography --break-system-packages 2>/dev/null || pip install cryptography

export ANDROID_API_LEVEL=28
pip install websockify --break-system-packages 2>/dev/null || pip install websockify

# --- CORREÇÃO DO FRONTEND ---
cd ~/Termux-Nino-OS-WebUI/FileBrowserQuantum/frontend
rm -rf node_modules package-lock.json
npm install --no-bin-links

# CHAMADA DIRETA AO VITE LOCAL (Resolve o "vite: not found")
./node_modules/vite/bin/vite.js build --outDir ../backend/http/dist

cp -r ../backend/http/dist/* ../backend/http/embed 2>/dev/null || true

# Rodar o build sem o '&' para o script esperar ele terminar antes de seguir
npx vite build --outDir ../backend/http/dist
cp -r ../backend/http/dist/* ../backend/http/embed 2>/dev/null || true

# --- COMPILAÇÃO DO BACKEND (Se necessário) ---
cd ~/Termux-Nino-OS-WebUI/FileBrowserQuantum/backend
if [ ! -f ./filebrowser ]; then
    echo "Compilando o executável do FileBrowser..."
    go build -o filebrowser main.go
fi
./filebrowser &

sleep 2

# --- INICIALIZAÇÃO DO VNC ---
cd ~/Termux-Nino-OS-WebUI/noVNC
vncserver -kill :0 2>/dev/null || true
vncserver :0 -xstartup "lxqt-session" -SecurityTypes none &
sleep 3

nohup websockify --web . 6080 localhost:5900 >/dev/null 2>&1 &
sleep 1

cd $HOME
nohup ttyd --writable -p 7681 bash -c 'SHELL=$(which bash) tmux new-session -A -s remote' >/dev/null 2>&1 &
sleep 1

cd ~/Nano-OS-Interface 2>/dev/null || cd ~/Termux-Nino-OS-WebUI
exec python3 server.py
