 
#!/data/data/com.termux/files/usr/bin/bash

# Forçar renderização por software para o VNC não capotar
export GALLIUM_DRIVER=llvmpipe

apt update -y
apt install -y python3 ttyd tigervnc xfce4 xfce-goodies root-repo x11-repo termux-api tmux make golang npm udocker python-cryptography openssl

export ANDROID_API_LEVEL=24
pip install cryptography --break-system-packages 2>/dev/null || pip install cryptography

export ANDROID_API_LEVEL=28
pip install websockify --break-system-packages 2>/dev/null || pip install websockify

# --- CORREÇÃO DO FRONTEND ---
cd ~/Termux-Nino-OS-WebUI/FileBrowserQuantum/frontend
# Removendo --no-bin-links para que o vite e vue-tsc funcionem corretamente no Termux
if [ ! -d "node_modules" ]; then
    npm install
fi

# Build do frontend
npx vite build --outDir ../backend/http/dist
mkdir -p ../backend/http/embed
cp -r ../backend/http/dist/* ../backend/http/embed/ 2>/dev/null || true

# --- COMPILAÇÃO DO BACKEND ---
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
rm -rf /tmp/.X0-lock /tmp/.X11-unix/X0

# Criando um xstartup temporário para garantir que o LXQt suba
XSTARTUP_TEMP=$(mktemp)
echo "#!/bin/sh" > $XSTARTUP_TEMP
echo "exec startxfce4" >> $XSTARTUP_TEMP
chmod +x $XSTARTUP_TEMP

vncserver :0 -xstartup $XSTARTUP_TEMP -SecurityTypes none &
sleep 5
rm $XSTARTUP_TEMP

nohup websockify --web . 6080 localhost:5900 >/dev/null 2>&1 &
sleep 1

cd $HOME
nohup ttyd --writable -p 7681 bash -c 'SHELL=$(which bash) tmux new-session -A -s remote' >/dev/null 2>&1 &
sleep 1

cd ~/Nano-OS-Interface 2>/dev/null || cd ~/Termux-Nino-OS-WebUI
exec python3 server.py
