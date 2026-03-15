[app]

# 앱 기본 정보 (title은 ASCII만 사용 — 한글 title은 빌드 시 인코딩 오류 유발)
title = Beep
package.name = pager
package.domain = org.snucse
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,wav,mp3,ogg,json

# 버전
version = 1.0.0

# 앱 요구사항 (Python 3.11 고정 — 3.14는 Android 미지원)
requirements = python3==3.11.9,kivy,pyjnius

# 안정적인 p4a 릴리즈 사용
p4a.branch = v2024.01.21

# Android 설정
android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 21
android.accept_sdk_license = True

# 가로 모드 강제
orientation = landscape

# 전체 화면
fullscreen = 1

# Presplash (검은 배경)
android.presplash_color = #000000

# 단일 아키텍처 (빌드 안정성 향상)
android.archs = arm64-v8a

# 앱이 백그라운드에서도 유지되도록
android.allow_backup = True

[buildozer]
# 로그 레벨 (0=에러, 1=경고, 2=정보)
log_level = 2

# 빌드 경고 무시
warn_on_root = 1
