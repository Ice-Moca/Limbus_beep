# 삐삐 Android APK 빌드 가이드

## 프로젝트 구조

```
android/
├── main.py                    # Kivy 메인 앱 (삐삐 시뮬레이터)
├── messages.json              # 메시지 데이터 (APK에 번들)
├── config.json                # 설정 (캘린더 URL 등)
├── neodgm.ttf                 # 폰트 파일
├── calendar_sync_android.py   # 캘린더 동기화 (Android 호환)
├── buildozer.spec             # APK 빌드 설정
├── build_android.sh           # 빌드 스크립트
└── service/
    └── main.py                # 백그라운드 서비스 (선택)
```

## 조작법

- **터치**: 다음 단계로 진행
- 상태 흐름: 대기 → 비프(암호텍스트) → 복호화 애니메이션 → 메시지 표시 → CLEAR → 다음 단계

## 빌드 환경 준비

### 방법 1: WSL2 (Windows에서 권장)

```bash
# WSL2 Ubuntu 설치 후:
sudo apt update
sudo apt install -y python3 python3-pip git zip unzip openjdk-17-jdk autoconf automake libtool pkg-config
sudo apt install -y zlib1g-dev libncurses5-dev libffi-dev libssl-dev

# Buildozer 설치
pip3 install buildozer cython

# Android SDK/NDK는 Buildozer가 자동 다운로드
```

### 방법 2: Google Colab (클라우드, 가장 쉬움)

```python
# Colab 노트북에서:
!pip install buildozer cython
!sudo apt install -y git zip unzip openjdk-17-jdk autoconf automake libtool

# 프로젝트 파일 업로드 후:
!cd /content/android && buildozer android debug
```

### 방법 3: Linux 네이티브

```bash
pip install buildozer cython
sudo apt install -y git zip unzip openjdk-17-jdk autoconf automake libtool
```

## 빌드 전 준비

### 1. 리소스 파일 복사

`android/` 폴더에 아래 파일들을 복사하세요:

```bash
# 상위 폴더에서 폰트 복사
cp ../neodgm.ttf ./

# 비프음 복사 (있으면)
cp ../beep.wav ./    # 또는 beep.ogg, beep.mp3
```

### 2. config.json 초기 설정 (선택)

앱 내에서 설정하거나, 미리 만들어두기:

```json
{
    "ics_url": "https://calendar.google.com/calendar/ical/...basic.ics"
}
```

## APK 빌드

```bash
cd android/

# 디버그 APK (테스트용)
buildozer android debug

# 릴리즈 APK (배포용)
buildozer android release

# 빌드 + 연결된 기기에 설치
buildozer android debug deploy run
```

빌드 완료 후 APK 파일: `android/bin/pager-1.0.0-arm64-v8a-debug.apk`

## 핸드폰에 설치

### USB 설치
```bash
# ADB가 설치되어 있다면:
adb install bin/pager-1.0.0-arm64-v8a-debug.apk
```

### 직접 설치
1. APK 파일을 핸드폰으로 전송 (카카오톡, 이메일, USB 등)
2. 핸드폰에서 파일 열기
3. "출처를 알 수 없는 앱 설치" 허용
4. 설치 완료

## 삼성 알림 바 위젯

앱 실행 후 알림 바를 내리면:
- **접힌 상태**: `삐삐 — 03/15 14:00` + 현재/다음 이벤트
- **펼친 상태**: 오늘의 전체 일정 목록 (BigTextStyle)
  - 현재 진행 중 이벤트에 ▶ 표시
  - 미래 이벤트에 · 표시

알림을 탭하면 메인 앱이 열립니다.

## 자동 화면 표시

- 이벤트 시작 시간이 되면 자동으로 화면이 켜지고 앱이 앞으로 옴
- 잠금 화면 위에도 표시 (WakeLock 사용)
- 30초마다 시간 체크

## 트러블슈팅

### 빌드 실패 시
```bash
# 캐시 정리 후 재시도
buildozer android clean
buildozer android debug
```

### 서비스가 시작되지 않을 때
- 삼성 기기: 설정 → 배터리 → 앱 절전 → 삐삐를 "제한 없음"으로 설정
- 설정 → 앱 → 삐삐 → 배터리 최적화 → 최적화하지 않음

### 알림이 보이지 않을 때
- 설정 → 알림 → 삐삐 → 알림 허용 ON
- Android 13+에서는 POST_NOTIFICATIONS 권한 필요 (앱 첫 실행 시 요청됨)

### 화면 자동 표시가 안 될 때
- 설정 → 앱 → 삐삐 → "다른 앱 위에 표시" 허용
- 삼성: 설정 → 앱 → 특별한 접근 → "다른 앱 위에 표시"
