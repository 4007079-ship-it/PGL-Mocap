#!/bin/bash
# Запуск приложения в эмуляторе: старт без падения, камера, отправка OSC и Live Link на хост (10.0.2.2).
set -x
APK=android/app/build/outputs/apk/debug/app-debug.apk
adb install -r "$APK"
adb shell pm grant com.pgl.mocap android.permission.CAMERA
# настройки: отправлять на хост эмулятора, включить OSC и Live Link
PREFS='<?xml version="1.0" encoding="utf-8" standalone="yes" ?><map><string name="targetIp">10.0.2.2</string><boolean name="oscEnabled" value="true" /><boolean name="llEnabled" value="true" /><string name="model">lite</string><boolean name="useGpu" value="false" /></map>'
adb shell "run-as com.pgl.mocap mkdir -p shared_prefs"
echo "$PREFS" | adb shell "run-as com.pgl.mocap sh -c 'cat > shared_prefs/pgl_mocap.xml'"
adb logcat -c
python3 android/ci/udp_listen.py 65 > udp.log 2>&1 &
LISTENER=$!
adb shell am start -n com.pgl.mocap/.MainActivity
sleep 60
adb exec-out screencap -p > emulator_screen.png
adb shell pidof com.pgl.mocap && echo "APP RUNNING" || echo "APP NOT RUNNING"
adb logcat -d > logcat.txt
wait $LISTENER; UDP=$?
cat udp.log
echo "--- crashes:"
grep -E "FATAL EXCEPTION|AndroidRuntime|PGLMocap" logcat.txt | head -40
grep -q "FATAL EXCEPTION" logcat.txt && { echo "CRASH"; exit 1; }
adb shell pidof com.pgl.mocap >/dev/null || { echo "APP DIED"; exit 1; }
adb shell dumpsys package com.pgl.mocap | grep -i "primaryCpuAbi"
adb shell getprop ro.product.cpu.abilist
exit $UDP
