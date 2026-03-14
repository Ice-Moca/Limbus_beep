"""
Google Calendar 연동 모듈 (ICS URL 방식)
====================================================================

OAuth 불필요! Google Calendar의 비공개 iCal URL만 있으면 동작.
오늘 하루의 일정을 가져와서 3개씩 묶어 단계별 메시지로 변환한다.

사용자 설정 방법:
  1. Google Calendar (calendar.google.com) 접속
  2. 좌측 캘린더 목록에서 원하는 캘린더 옆 ⋮ (점 세개) -> 설정
  3. iCal 형식의 비공개 주소 URL 복사
  4. 프로그램 설정(S키)에서 URL 붙여넣기

또는 config.json 파일에 직접 입력:
  { "ics_url": "https://calendar.google.com/calendar/ical/...basic.ics" }
"""

import os
import json
import math
import urllib.request
import ssl
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
MESSAGES_FILE = os.path.join(BASE_DIR, "messages.json")


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)


def get_ics_url():
    config = load_config()
    return config.get("ics_url")


def set_ics_url(url: str):
    config = load_config()
    config["ics_url"] = url
    save_config(config)


def clear_ics_url():
    config = load_config()
    config.pop("ics_url", None)
    save_config(config)


def is_configured() -> bool:
    url = get_ics_url()
    return url is not None and len(url) > 10


def fetch_ics_data(url: str) -> str:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "PagerSimulator/1.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
        return response.read().decode("utf-8")


def _is_today_event(event, today):
    dtstart = event.get("DTSTART", "")
    if not dtstart:
        return False
    try:
        if len(dtstart) == 8:
            return datetime.strptime(dtstart, "%Y%m%d").date() == today
        elif "T" in dtstart:
            dt_str = dtstart.replace("Z", "")
            event_dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%S")
            if dtstart.endswith("Z"):
                event_dt = event_dt + timedelta(hours=9)
            return event_dt.date() == today
    except ValueError:
        pass
    return False


def parse_ics_events(ics_text: str):
    today = datetime.now().date()
    events = []
    in_event = False
    current = {}

    for line in ics_text.replace("\r\n ", "").replace("\r\n\t", "").splitlines():
        line = line.strip()
        if line == "BEGIN:VEVENT":
            in_event = True
            current = {}
        elif line == "END:VEVENT":
            in_event = False
            if _is_today_event(current, today):
                events.append(current)
        elif in_event and ":" in line:
            key_part, _, value = line.partition(":")
            key = key_part.split(";")[0]
            current[key] = value

    events.sort(key=lambda e: e.get("DTSTART", ""))
    return events


def _format_event(event):
    """이벤트를 {text, time_info} 딕셔너리로 변환"""
    summary = event.get("SUMMARY", "(제목 없음)")
    dtstart = event.get("DTSTART", "")
    dtend = event.get("DTEND", "")
    time_info = ""

    try:
        if len(dtstart) == 8:
            time_info = "종일"
        elif "T" in dtstart:
            dt_str = dtstart.replace("Z", "")
            start_dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%S")
            if dtstart.endswith("Z"):
                start_dt = start_dt + timedelta(hours=9)
            start_str = start_dt.strftime("%H:%M")

            if dtend and "T" in dtend:
                end_str_raw = dtend.replace("Z", "")
                end_dt = datetime.strptime(end_str_raw, "%Y%m%dT%H%M%S")
                if dtend.endswith("Z"):
                    end_dt = end_dt + timedelta(hours=9)
                end_str = end_dt.strftime("%H:%M")
                time_info = start_str + " - " + end_str
            else:
                time_info = start_str
    except ValueError:
        pass

    return {"text": summary, "time_info": time_info}


def events_to_messages(events):
    """
    이벤트를 고정 3단계로 균등 분배.
    각 stage의 messages는 개별 딕셔너리 리스트.
    예: 5개 이벤트 → 해금1(2개), 해금2(2개), 해금3(1개)
    """
    if not events:
        return [{"stage": 1, "messages": [{"text": "오늘 일정이 없습니다", "time_info": ""}]}]

    formatted = [_format_event(e) for e in events]
    num_stages = 3
    # 균등 분배: 앞 단계부터 1개씩 더
    base, extra = divmod(len(formatted), num_stages)
    stages = []
    idx = 0
    for s in range(num_stages):
        count = base + (1 if s < extra else 0)
        if count == 0:
            continue
        chunk = formatted[idx : idx + count]
        stages.append({
            "stage": s + 1,
            "messages": chunk
        })
        idx += count

    return stages


def save_messages(messages):
    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=4)


def sync_calendar():
    url = get_ics_url()
    if not url:
        print("ICS URL이 설정되지 않았습니다.")
        return False

    print("캘린더 동기화 시작...")
    try:
        ics_data = fetch_ics_data(url)
    except Exception as e:
        print("데이터 가져오기 실패: " + str(e))
        return False

    events = parse_ics_events(ics_data)
    print("   오늘 일정: " + str(len(events)) + "개")

    messages = events_to_messages(events)
    print("   생성 단계: " + str(len(messages)) + "단계")

    save_messages(messages)
    print("저장 완료!")
    return True


if __name__ == "__main__":
    if not is_configured():
        url = input("Google Calendar 비공개 iCal URL을 입력하세요: ").strip()
        if url:
            set_ics_url(url)
    sync_calendar()
