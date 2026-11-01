#!/bin/bash
# Сборка PGL Mocap.app и PGL_Mocap_macOS.dmg (запускается в CI на Mac с Apple Silicon).
set -euo pipefail
cd "$(dirname "$0")/../.."
DMG=${1:-PGL_Mocap_macOS.dmg}
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' pglmocap/__init__.py)
BUILD=${GITHUB_RUN_NUMBER:-0}

# иконка .icns из логотипа
ICONSET=build/pgl_mocap.iconset
rm -rf "$ICONSET"; mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s assets/pgl_mocap_logo.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  d=$((s*2)); sips -z $d $d assets/pgl_mocap_logo.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o build/pgl_mocap.icns

python -m PyInstaller --noconfirm --clean --windowed \
  --name "PGL Mocap" \
  --icon build/pgl_mocap.icns \
  --osx-bundle-identifier com.pgl.mocap \
  --add-data "models:models" \
  --add-data "assets:assets" \
  --collect-all mediapipe \
  --collect-all cyndilib \
  --hidden-import selftest \
  --exclude-module jax --exclude-module jaxlib --exclude-module sentencepiece \
  run_pgl_mocap.py

APP="dist/PGL Mocap.app"
PLIST="$APP/Contents/Info.plist"
# доступ к камере и сети, версия
/usr/libexec/PlistBuddy -c "Add :NSCameraUsageDescription string 'PGL Mocap использует камеру для отслеживания движений человека.'" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSLocalNetworkUsageDescription string 'PGL Mocap отправляет данные в Aximmetry и Unreal и принимает видео NDI по локальной сети.'" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSBonjourServices array" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSBonjourServices:0 string _ndi._tcp" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VER" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $BUILD" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 13.0" "$PLIST" 2>/dev/null || true
cp README.md "$APP/Contents/Resources/README.md"

# после правки Info.plist — заново подписываем «ad-hoc» (без сертификата Apple)
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP" && echo "codesign OK"

# образ диска: приложение + ярлык на «Программы»
rm -rf build/dmg; mkdir -p build/dmg
cp -R "$APP" build/dmg/
ln -s /Applications build/dmg/Applications
rm -f "$DMG"
# hdiutil на серверах GitHub иногда отвечает «Resource busy» — повторяем
for i in 1 2 3 4 5 6; do
  if hdiutil create -volname "PGL Mocap" -srcfolder build/dmg -fs HFS+ -ov -format UDZO "$DMG"; then break; fi
  echo "hdiutil: попытка $i не удалась, повтор через 10 с"
  hdiutil info | grep -E "^/dev/disk" | awk '{print $1}' | xargs -I{} hdiutil detach {} -force 2>/dev/null || true
  sleep 10
  [ "$i" = 6 ] && exit 1
done
ls -la "$DMG"
