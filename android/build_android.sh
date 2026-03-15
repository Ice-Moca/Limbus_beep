#!/bin/bash
# ============================================
#  삐삐 (Pager) Android APK 빌드 스크립트
# ============================================
#  WSL Ubuntu 또는 Linux에서 실행
#
#  사전 준비:
#    sudo apt update
#    sudo apt install -y python3-pip git zip unzip openjdk-17-jdk \
#      autoconf automake libtool pkg-config zlib1g-dev libncurses5-dev \
#      libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev
#    pip3 install --user buildozer cython virtualenv
#
#  사용법:
#    cd android/
#    bash build_android.sh
# ============================================

set -e

echo "=== 삐삐 Android APK 빌드 시작 ==="

# .buildozer 캐시가 기존에 있으면 삭제 (크래시 원인 제거)
if [ -d ".buildozer" ]; then
    echo ">>> 이전 빌드 캐시 삭제 중..."
    rm -rf .buildozer
fi

# Buildozer 빌드 실행
echo ">>> buildozer android debug 실행..."
buildozer android debug

echo ""
echo "=== 빌드 완료! ==="
echo "APK 위치: bin/ 폴더를 확인하세요"
echo ""
echo "APK를 폰에 설치하려면:"
echo "  adb install bin/*.apk"
echo "또는 bin/*.apk 파일을 폰으로 전송하여 설치"
