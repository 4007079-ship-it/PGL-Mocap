#!/bin/bash
# Добавляет PGL Mocap в меню приложений Linux. Запускать из папки программы:  ./install_linux.sh
DIR="$(cd "$(dirname "$0")" && pwd)"
ICON="$DIR/_internal/assets/pgl_mocap.ico"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/pgl-mocap.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=PGL Mocap
Comment=Трекинг позы по видео с отправкой в Aximmetry по OSC
Exec="$DIR/PGL Mocap"
Path=$DIR
Icon=$ICON
Terminal=false
Categories=AudioVideo;Video;
DESK
chmod +x "$DIR/PGL Mocap"
echo "Готово: PGL Mocap добавлен в меню приложений."
