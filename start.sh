#!/data/data/com.termux/files/usr/bin/bash

export GALLIUM_DRIVER=llvmpipe

# 1. FUNÇÃO DE INSTALAÇÃO INTELIGENTE (apt com fallback para pkg)
instalar_pacotes() {
    local pacotes=("$@")
    echo "Verificando e instalando dependências do sistema..."
    
    # Tenta atualizar e instalar com apt
    if ! apt update -y && apt install -y "${pacotes[@]}"; then
        echo "Apt falhou ou não está disponível. Tentando com pkg..."
        pkg update -y && pkg install -y "${pacotes[@]}"
    fi
}

# Lista de pacotes necessários
pacotes_sistema=(
    python3 ttyd tigervnc xfce4 xfce-goodies root-repo x11-repo 
    termux-api tmux make golang npm udocker python-cryptography openssl
)

# Só roda a instalação se um pacote essencial (ex: tigervnc ou tmux) não estiver no sistema
if ! command -v vncserver &> /dev/null || ! command -v tmux &> /dev/null; then
    instalar_pacotes "${pacotes_sistema[@]}"
else
    echo "Pacotes de sistema já parecem estar instalados. Pulando..."
fi

# 2. INSTALAÇÃO INTELIGENTE DO PIP (Só roda se não estiver instalado)
if ! python3 -c "import cryptography" &> /dev/null; then
    export ANDROID_API_LEVEL=24
    pip install cryptography --break-system-packages 2>/dev/null || pip install cryptography
fi

if ! python3 -c "import websockify" &> /dev/null; then
    export ANDROID_API_LEVEL=28
    pip install websockify --break-system-packages 2>/dev/null || pip install websockify
fi

# 3. COMPILAÇÃO DO FRONTEND (Só roda se a pasta 'dist' não existir)
cd ~/Termux-Nino-OS-WebUI/FileBrowserQuantum/frontend
if [ ! -d "../backend/http/dist" ]; then
    echo "Pasta 'dist' não encontrada. Iniciando build do Frontend..."
    if [ ! -d "node_modules" ]; then
        npm install
    fi
    npx vite build --outDir ../backend/http/dist
    mkdir -p ../backend/http/embed
    cp -r ../backend/http/dist/* ../backend/http/embed/ 2>/dev/null || true
else
    echo "Frontend já compilado (pasta dist encontrada). Pulando..."
fi

# 4. COMPILAÇÃO E EXECUÇÃO DO BACKEND (FILEBROWSER)
cd ~/Termux-Nino-OS-WebUI/FileBrowserQuantum/backend
if [ ! -f ./filebrowser ]; then
    go build -o filebrowser main.go
fi

# Só inicia o filebrowser se ele já não estiver rodando
if ! pgrep -x "filebrowser" &> /dev/null; then
    ./filebrowser &
    sleep 2
else
    echo "FileBrowser já está rodando."
fi

# 5. CONFIGURAÇÃO E INICIALIZAÇÃO DO VNC
cd ~/Termux-Nino-OS-WebUI/noVNC

# Verifica se o VNC na tela :0 já está ativo
if ! vncserver -list | grep -q "^:0"; then
    vncserver -kill :0 2>/dev/null || true
    rm -rf /tmp/.X0-lock /tmp/.X11-unix/X0

    XSTARTUP_TEMP=$(mktemp)
    echo "#!/bin/sh" > $XSTARTUP_TEMP
    echo "exec startxfce4" >> $XSTARTUP_TEMP
    chmod +x $XSTARTUP_TEMP

    vncserver :0 -xstartup $XSTARTUP_TEMP -SecurityTypes none &
    sleep 5
    rm $XSTARTUP_TEMP
else
    echo "VNC Server já está rodando na tela :0."
fi

# 6. INICIALIZAÇÃO DOS SERVIÇOS EM BACKGROUND (Com trava para não duplicar)
if ! pgrep -f "websockify" &> /dev/null; then
    nohup websockify --web . 6080 localhost:5900 >/dev/null 2>&1 &
    sleep 1
fi

if ! pgrep -x "ttyd" &> /dev/null; then
    cd $HOME
    nohup ttyd --writable -p 7681 bash -c 'SHELL=$(which bash) tmux new-session -A -s remote' >/dev/null 2>&1 &
    sleep 1
fi

# 7. EXECUÇÃO DO SERVIDOR FINAL
cd ~/Nano-OS-Interface 2>/dev/null || cd ~/Termux-Nino-OS-WebUI
exec python3 server.py
