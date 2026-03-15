"""
삐삐 Android 백그라운드 서비스
==============================
- 포그라운드 서비스로 실행 (알림 바에 상시 위젯 표시)
- 이벤트 시간이 되면 메인 액티비티 자동 실행
- 1시간마다 캘린더 자동 동기화
- 삼성 알림 바에 12:9 비율 커스텀 뷰 표시 (미디어 스타일)
"""

import os
import sys
import json
import time as _time
from datetime import datetime, timedelta

# Android 경로 설정
def _get_data_dir():
    try:
        from android.storage import app_storage_path
        return app_storage_path()
    except ImportError:
        return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = _get_data_dir()
MESSAGES_FILE = os.path.join(BASE_DIR, "messages.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# jnius import
try:
    from jnius import autoclass, cast
    PythonService = autoclass("org.kivy.android.PythonService")
    Context = autoclass("android.content.Context")
    Intent = autoclass("android.content.Intent")
    PendingIntent = autoclass("android.app.PendingIntent")
    NotificationCompat = autoclass("androidx.core.app.NotificationCompat")
    NotificationCompat_Builder = autoclass("androidx.core.app.NotificationCompat$Builder")
    NotificationManager = autoclass("android.app.NotificationManager")
    NotificationChannel = autoclass("android.app.NotificationChannel")
    Build_VERSION = autoclass("android.os.Build$VERSION")
    Build_VERSION_CODES = autoclass("android.os.Build$VERSION_CODES")
    RemoteViews = autoclass("android.widget.RemoteViews")
    Color = autoclass("android.graphics.Color")
    PowerManager = autoclass("android.os.PowerManager")
    ANDROID_AVAILABLE = True
except ImportError:
    ANDROID_AVAILABLE = False
    print("[서비스] Android 환경이 아닙니다")


CHANNEL_ID = "pager_channel"
NOTIFICATION_ID = 1001
SYNC_INTERVAL = 3600  # 1시간


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_messages():
    if not os.path.exists(MESSAGES_FILE):
        return []
    with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    for item in data:
        if "messages" not in item and "message" in item:
            item["messages"] = [
                {"text": line, "time_info": ""}
                for line in item["message"].split("\n") if line.strip()
            ]
    data.sort(key=lambda x: x["stage"])
    return data


def get_upcoming_events(messages):
    """현재 시간 기준으로 다가오는 이벤트들을 시간순으로 반환"""
    now = datetime.now()
    upcoming = []

    for stage in messages:
        for msg in stage.get("messages", []):
            if not isinstance(msg, dict):
                continue
            time_info = msg.get("time_info", "")
            text = msg.get("text", "")
            if not time_info or time_info == "종일":
                upcoming.append({"text": text, "time_info": time_info, "dt": None})
                continue

            # "HH:MM - HH:MM" 파싱
            try:
                parts = time_info.split("-")
                start_str = parts[0].strip()
                start_h, start_m = map(int, start_str.split(":"))
                event_dt = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
                upcoming.append({"text": text, "time_info": time_info, "dt": event_dt})
            except (ValueError, IndexError):
                upcoming.append({"text": text, "time_info": time_info, "dt": None})

    # 시간 있는 이벤트 정렬
    upcoming.sort(key=lambda x: x["dt"] or datetime.max)
    return upcoming


def get_next_event(messages):
    """다음 이벤트 (현재 시간 이후) 반환"""
    now = datetime.now()
    for evt in get_upcoming_events(messages):
        if evt["dt"] and evt["dt"] > now:
            return evt
    return None


def get_current_event(messages):
    """현재 진행 중인 이벤트 반환"""
    now = datetime.now()
    for stage in messages:
        for msg in stage.get("messages", []):
            if not isinstance(msg, dict):
                continue
            time_info = msg.get("time_info", "")
            if not time_info or "-" not in time_info:
                continue
            try:
                parts = time_info.split("-")
                sh, sm = map(int, parts[0].strip().split(":"))
                eh, em = map(int, parts[1].strip().split(":"))
                start = now.replace(hour=sh, minute=sm, second=0)
                end = now.replace(hour=eh, minute=em, second=0)
                if start <= now <= end:
                    return {"text": msg.get("text", ""), "time_info": time_info}
            except (ValueError, IndexError):
                continue
    return None


class PagerService:
    """백그라운드 포그라운드 서비스"""

    def __init__(self):
        if not ANDROID_AVAILABLE:
            print("[서비스] Android가 아니므로 콘솔 모드로 실행")
            return

        self.service = PythonService.mService
        self.context = cast("android.content.Context", self.service)
        self.package_name = str(self.context.getPackageName())

        self._create_notification_channel()
        self._start_foreground()

    def _create_notification_channel(self):
        """알림 채널 생성 (Android 8+)"""
        if Build_VERSION.SDK_INT >= Build_VERSION_CODES.O:
            channel = NotificationChannel(
                CHANNEL_ID,
                "삐삐 알림",
                NotificationManager.IMPORTANCE_LOW,  # 소리 없이 상시 표시
            )
            channel.setDescription("삐삐 시뮬레이터 일정 알림")
            channel.setShowBadge(False)

            nm = cast(
                "android.app.NotificationManager",
                self.context.getSystemService(Context.NOTIFICATION_SERVICE),
            )
            nm.createNotificationChannel(channel)

    def _build_notification(self, title="삐삐", content="일정 모니터링 중", events_text=""):
        """커스텀 알림 빌드 — 12:9 비율 위젯처럼 표시"""

        # 탭시 메인 액티비티 실행
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        intent = Intent(self.context, PythonActivity)
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)

        pending = PendingIntent.getActivity(
            self.context, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE,
        )

        builder = NotificationCompat_Builder(self.context, CHANNEL_ID)
        builder.setSmallIcon(self.context.getApplicationInfo().icon)
        builder.setContentTitle(title)
        builder.setContentText(content)
        builder.setContentIntent(pending)
        builder.setOngoing(True)  # 지울 수 없게
        builder.setPriority(NotificationCompat.PRIORITY_LOW)
        builder.setCategory("service")

        # 큰 텍스트 스타일 (12:9 비율처럼 넓게)
        if events_text:
            BigTextStyle = autoclass("androidx.core.app.NotificationCompat$BigTextStyle")
            big_style = BigTextStyle()
            big_style.bigText(events_text)
            big_style.setBigContentTitle(title)
            builder.setStyle(big_style)

        # 색상
        builder.setColorized(True)
        builder.setColor(Color.parseColor("#001a2e"))

        return builder.build()

    def _start_foreground(self):
        """포그라운드 서비스 시작하면서 알림 등록"""
        messages = load_messages()
        title, content, big = self._format_notification_text(messages)
        notification = self._build_notification(title, content, big)
        self.service.startForeground(NOTIFICATION_ID, notification)

    def _format_notification_text(self, messages):
        """알림에 표시할 텍스트 포맷"""
        now = datetime.now()
        title = f"삐삐 — {now.strftime('%m/%d %H:%M')}"

        current = get_current_event(messages)
        next_evt = get_next_event(messages)

        if current:
            content = f"▶ {current['text']} ({current['time_info']})"
        elif next_evt:
            content = f"다음: {next_evt['text']} ({next_evt['time_info']})"
        else:
            content = "오늘 일정 완료"

        # 큰 텍스트: 전체 일정 목록
        lines = []
        for stage in messages:
            for msg in stage.get("messages", []):
                if isinstance(msg, dict):
                    t = msg.get("text", "")
                    ti = msg.get("time_info", "")
                    prefix = "▶" if current and current["text"] == t else "·"
                    lines.append(f"{prefix} {ti}  {t}" if ti else f"{prefix} {t}")

        big_text = "\n".join(lines) if lines else ""
        return title, content, big_text

    def update_notification(self, messages):
        """알림 위젯 업데이트"""
        title, content, big = self._format_notification_text(messages)
        notification = self._build_notification(title, content, big)

        nm = cast(
            "android.app.NotificationManager",
            self.context.getSystemService(Context.NOTIFICATION_SERVICE),
        )
        nm.notify(NOTIFICATION_ID, notification)

    def launch_main_activity(self):
        """메인 액티비티를 화면에 띄우기 (이벤트 시간에 호출)"""
        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            intent = Intent(self.context, PythonActivity)
            intent.setFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK
                | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT
            )
            self.context.startActivity(intent)

            # 화면 깨우기 (잠금 화면 위에 표시)
            pm = cast(
                "android.os.PowerManager",
                self.context.getSystemService(Context.POWER_SERVICE),
            )
            wl = pm.newWakeLock(
                PowerManager.ACQUIRE_CAUSES_WAKEUP | PowerManager.FULL_WAKE_LOCK,
                "pager:wakeup",
            )
            wl.acquire(5000)  # 5초
            wl.release()
        except Exception as e:
            print(f"[서비스] 액티비티 시작 실패: {e}")

    def do_sync(self):
        """캘린더 동기화"""
        try:
            # calendar_sync_android 모듈 사용
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from calendar_sync_android import is_configured, sync_calendar
            if is_configured():
                return sync_calendar()
        except Exception as e:
            print(f"[서비스 동기화] 오류: {e}")
        return False

    def run(self):
        """서비스 메인 루프"""
        print("[서비스] 시작됨")
        last_sync = 0
        last_check_minute = -1

        while True:
            now = _time.time()

            # 1시간마다 캘린더 동기화
            if now - last_sync > SYNC_INTERVAL:
                self.do_sync()
                last_sync = now

            # 매분 체크: 이벤트 시간 도달 여부
            current_minute = datetime.now().minute
            if current_minute != last_check_minute:
                last_check_minute = current_minute
                messages = load_messages()

                # 알림 업데이트
                if ANDROID_AVAILABLE:
                    self.update_notification(messages)

                # 현재 이벤트 시작 시점이면 액티비티 실행
                current_evt = get_current_event(messages)
                if current_evt and ANDROID_AVAILABLE:
                    # 이벤트 시작 시간의 정각(±1분)이면 화면 띄움
                    dt_now = datetime.now()
                    time_info = current_evt["time_info"]
                    try:
                        start_str = time_info.split("-")[0].strip()
                        sh, sm = map(int, start_str.split(":"))
                        if dt_now.hour == sh and dt_now.minute == sm:
                            print(f"[서비스] 이벤트 시작! → {current_evt['text']}")
                            self.launch_main_activity()
                    except (ValueError, IndexError):
                        pass

            _time.sleep(30)  # 30초마다 체크


def main():
    """서비스 엔트리포인트"""
    if ANDROID_AVAILABLE:
        svc = PagerService()
        svc.run()
    else:
        # PC에서 테스트용
        print("[서비스] PC 테스트 모드")
        while True:
            messages = load_messages()
            current = get_current_event(messages)
            next_evt = get_next_event(messages)
            print(f"  현재: {current}, 다음: {next_evt}")
            _time.sleep(30)


if __name__ == "__main__":
    main()
