"""
Google Calendar 연동 모듈 (Android 호환 버전)
==================================================
원본 calendar_sync.py를 Android 환경에 맞게 수정.
urllib 대신 Android에서도 동작하는 방식 사용.
"""

import os
import json
import sys
from datetime import datetime, timedelta

try:
    import urllib.request
    import ssl
    URLLIB_AVAILABLE = True
except ImportError:
    URLLIB_AVAILABLE = False


def _get_data_dir():
    """Android 또는 PC 데이터 경로 — Kivy App과 동일 경로 사용"""
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app:
            return app.user_data_dir
    except Exception:
        pass
    try:
        from android.storage import app_storage_path
        return app_storage_path()
    except Exception:
        return os.path.dirname(os.path.abspath(__file__))


def _config_file():
    return os.path.join(_get_data_dir(), "config.json")


def _messages_file():
    return os.path.join(_get_data_dir(), "messages.json")


def load_config():
    cf = _config_file()
    if os.path.exists(cf):
        with open(cf, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(config):
    cf = _config_file()
    os.makedirs(os.path.dirname(cf), exist_ok=True)
    with open(cf, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)


def get_ics_url():
    config = load_config()
    return config.get("ics_url")


def set_ics_url(url):
    config = load_config()
    config["ics_url"] = url
    save_config(config)


def clear_ics_url():
    config = load_config()
    config.pop("ics_url", None)
    save_config(config)


def is_configured():
    url = get_ics_url()
    return url is not None and len(url) > 10


def fetch_ics_data(url):
    """ICS 데이터 다운로드"""
    errors = []

    # 1) Android: Java HttpURLConnection (OS가 SSL 인증서 관리)
    try:
        from jnius import autoclass
        URL = autoclass("java.net.URL")
        BufferedReader = autoclass("java.io.BufferedReader")
        InputStreamReader = autoclass("java.io.InputStreamReader")

        java_url = URL(url)
        conn = java_url.openConnection()
        conn.setConnectTimeout(15000)
        conn.setReadTimeout(15000)
        conn.setRequestProperty("User-Agent", "PagerSimulator/1.0")

        reader = BufferedReader(InputStreamReader(conn.getInputStream(), "UTF-8"))
        lines = []
        line = reader.readLine()
        while line is not None:
            lines.append(str(line))
            line = reader.readLine()
        reader.close()
        conn.disconnect()
        return "\n".join(lines)
    except Exception as e:
        errors.append(f"jnius: {e}")

    # 2) urllib — SSL 검증 없이 (Android CA 번들 없음)
    if URLLIB_AVAILABLE:
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={"User-Agent": "PagerSimulator/1.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
                return response.read().decode("utf-8")
        except Exception as e:
            errors.append(f"urllib: {e}")

    raise RuntimeError(" / ".join(errors) if errors else "HTTP 불가")


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


def parse_ics_events(ics_text):
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
    if not events:
        return [{"stage": 1, "messages": [{"text": "오늘 일정이 없습니다", "time_info": ""}]}]

    formatted = [_format_event(e) for e in events]
    num_stages = 3
    base, extra = divmod(len(formatted), num_stages)
    stages = []
    idx = 0
    for s in range(num_stages):
        count = base + (1 if s < extra else 0)
        if count == 0:
            continue
        chunk = formatted[idx : idx + count]
        stages.append({"stage": s + 1, "messages": chunk})
        idx += count

    return stages


def save_messages(messages):
    mf = _messages_file()
    os.makedirs(os.path.dirname(mf), exist_ok=True)
    with open(mf, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=4)


def sync_calendar():
    """동기화 실행. 성공 시 (True, msg), 실패 시 (False, err_msg) 반환"""
    url = get_ics_url()
    if not url:
        return (False, "ICS URL 미설정")

    try:
        ics_data = fetch_ics_data(url)
    except Exception as e:
        return (False, f"다운로드 실패: {str(e)[:40]}")

    events = parse_ics_events(ics_data)

    messages = events_to_messages(events)
    try:
        save_messages(messages)
    except Exception as e:
        return (False, f"저장 실패: {str(e)[:40]}")

    return (True, f"완료! 오늘 일정 {len(events)}개")
