"""
자동 캘린더 동기화 스크립트
====================================================================

Windows 작업 스케줄러(Task Scheduler)에 등록하여
pager.py 실행과 무관하게 주기적으로 Google Calendar → messages.json 동기화.

사용법:
  python auto_sync.py              # 1회 동기화
  python auto_sync.py --loop       # 1시간마다 반복 동기화 (백그라운드)
  python auto_sync.py --interval 30  # 30분마다 반복 동기화

Windows 작업 스케줄러 등록 방법:
  1. Win+R → taskschd.msc 실행
  2. '기본 작업 만들기' 클릭
  3. 이름: "삐삐 캘린더 동기화"
  4. 트리거: 매일 / 반복 간격 1시간
  5. 동작: 프로그램 시작
     - 프로그램: C:\\Users\\c\\AppData\\Local\\Programs\\Python\\Python311\\python.exe
     - 인수: "auto_sync.py"
     - 시작 위치: C:\\Users\\c\\OneDrive\\문서\\SNUCSE\\삐삐
  6. 완료

또는 PowerShell 한 줄로 등록:
  schtasks /create /tn "삐삐_캘린더_동기화" /tr "C:\\Users\\c\\AppData\\Local\\Programs\\Python\\Python311\\python.exe auto_sync.py" /sc HOURLY /mo 1 /f
"""

import sys
import os
import time
import argparse
from datetime import datetime

# 현재 스크립트 위치를 기준으로 calendar_sync 모듈 import
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from calendar_sync import is_configured, sync_calendar


def do_sync() -> bool:
    """1회 동기화 실행"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] 동기화 시작...")

    if not is_configured():
        print(f"[{timestamp}] ❌ ICS URL이 설정되지 않았습니다.")
        print("  → config.json에 ics_url을 설정하거나 pager.py에서 S키로 설정하세요.")
        return False

    try:
        result = sync_calendar()
        if result:
            print(f"[{timestamp}] ✅ 동기화 완료!")
            return True
        else:
            print(f"[{timestamp}] ❌ 동기화 실패")
            return False
    except Exception as e:
        print(f"[{timestamp}] ❌ 오류: {e}")
        return False


def loop_sync(interval_minutes: int = 60):
    """주기적으로 동기화 반복"""
    interval_sec = interval_minutes * 60
    print(f"🔄 자동 동기화 모드: {interval_minutes}분 간격")
    print(f"   Ctrl+C로 중지\n")

    while True:
        do_sync()
        print(f"   다음 동기화: {interval_minutes}분 후\n")
        try:
            time.sleep(interval_sec)
        except KeyboardInterrupt:
            print("\n🛑 자동 동기화 중지됨")
            break


def main():
    parser = argparse.ArgumentParser(description="삐삐 캘린더 자동 동기화")
    parser.add_argument(
        "--loop", action="store_true",
        help="반복 동기화 모드 (기본: 1시간 간격)"
    )
    parser.add_argument(
        "--interval", type=int, default=60,
        help="동기화 간격 (분, 기본: 60)"
    )
    args = parser.parse_args()

    if args.loop:
        loop_sync(args.interval)
    else:
        success = do_sync()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
