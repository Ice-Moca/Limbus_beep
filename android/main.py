"""삐삐 (Pager/Beeper) 시뮬레이터 — Android Kivy 버전"""

import os
import json
import random
import string
import math
import traceback

# Kivy 환경변수 — import 전에 설정해야 함
os.environ.setdefault('KIVY_LOG_LEVEL', 'debug')

from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, Line
from kivy.core.audio import SoundLoader
from kivy.logger import Logger


# ───────────────────────── 경로 유틸 ─────────────────────────

def _app_dir():
    """APK 번들 리소스 디렉토리 (Kivy 방식)"""
    # Android에서는 App().directory 사용. 아직 App이 없으면 __file__ fallback
    try:
        app = App.get_running_app()
        if app:
            return app.directory
    except Exception:
        pass
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return '.'


def _data_dir():
    """쓰기 가능한 앱 데이터 디렉토리"""
    try:
        app = App.get_running_app()
        if app:
            return app.user_data_dir
    except Exception:
        pass
    try:
        from android.storage import app_storage_path
        return app_storage_path()
    except Exception:
        return _app_dir()


# ───────────────────────── 폰트 (지연 로딩) ──────────────────

FONT_NAME = 'Roboto'

def _init_font():
    """App.build() 내부에서 호출 — Kivy 초기화 후 폰트 등록"""
    global FONT_NAME
    try:
        from kivy.core.text import LabelBase
        for d in (_app_dir(), '.'):
            fp = os.path.join(d, 'neodgm.ttf')
            if os.path.exists(fp):
                LabelBase.register(name='NeoDGM', fn_regular=fp)
                FONT_NAME = 'NeoDGM'
                Logger.info('Pager: font loaded from %s', fp)
                return
        Logger.warning('Pager: neodgm.ttf not found, using Roboto')
    except Exception as e:
        Logger.warning('Pager: font load error: %s', e)


# ───────────────────────── 색상 (Kivy: 0~1 range) ───────────

C_BG     = (0, 0, 0, 1)
C_TEXT   = (0, 0.627, 1, 1)         # (0, 160, 255)
C_DIM    = (0, 0.314, 0.51, 1)      # (0, 80, 130)
C_ACCENT = (0, 0.863, 1, 1)         # (0, 220, 255)


# ───────────────────────── 메시지 로드 ───────────────────────

def _ensure_data_files():
    """번들된 파일을 쓰기 가능한 data_dir로 복사 (최초 실행 시)"""
    try:
        import shutil
        data = _data_dir()
        app = _app_dir()
        if data == app:
            return
        for fname in ('messages.json', 'config.json'):
            dst = os.path.join(data, fname)
            src = os.path.join(app, fname)
            if not os.path.exists(dst) and os.path.exists(src):
                try:
                    shutil.copy2(src, dst)
                except Exception:
                    pass
    except Exception as e:
        Logger.warning('Pager: data copy error: %s', e)


def load_messages():
    """messages.json 로드 — data_dir → app_dir → 현재 디렉토리 순으로 탐색"""
    _ensure_data_files()
    for d in (_data_dir(), _app_dir(), '.'):
        p = os.path.join(d, 'messages.json')
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for it in data:
                    if 'messages' not in it and 'message' in it:
                        it['messages'] = [
                            {'text': ln, 'time_info': ''}
                            for ln in it['message'].split('\n') if ln.strip()
                        ]
                data.sort(key=lambda x: x.get('stage', 0))
                if data:
                    return data
            except Exception:
                pass
    return [{'stage': 1, 'messages': [{'text': '메시지 없음', 'time_info': ''}]}]


def _rand_chars(n=None):
    """랜덤 암호화 텍스트 생성"""
    if n is None:
        n = random.randint(9, 13)
    pool = string.ascii_uppercase + string.digits + '!@#$%&*+-=?<>'
    return ''.join(random.choice(pool) for _ in range(n))


# ───────────────────────── 상태 상수 ─────────────────────────

ST_IDLE     = 0
ST_BEEPING  = 1
ST_DECODING = 2
ST_REVEALED = 3
ST_CLEAR    = 4
ST_COMPLETE = 5
ST_SETTINGS = 6

LONG_PRESS_TIME = 0.8   # 초
SWIPE_THRESHOLD = 80    # 픽셀


# ───────────────────────── 메인 위젯 ─────────────────────────

class PagerScreen(FloatLayout):
    """삐삐 시뮬레이터 전체 화면"""

    def __init__(self, **kw):
        super().__init__(**kw)

        # ── 데이터 ──
        self.messages = load_messages()
        self.stage_idx = 0
        self.msg_idx = 0

        # ── 상태 ──
        self.state = ST_IDLE
        self.timer = 0.0
        self.enc_text = ''
        self.dec_progress = 0.0
        self.blink = True
        self.blink_timer = 0.0

        # ── 제스처 감지 ──
        self._touch_start_y = 0
        self._touch_start_time = 0
        self._long_press_event = None
        self._touch_consumed = False  # 제스처로 소비됨

        # ── 설정 화면 ──
        self._settings_sel = 0      # 선택된 메뉴
        self._settings_status = ''
        self._settings_busy = False
        self._prev_state = ST_IDLE
        self._url_input_visible = False  # URL 입력창 표시 여부
        self._url_input = None           # TextInput 위젯

        # ── 사운드 ──
        self._beep_sound = None
        for d in (_app_dir(), '.'):
            fp = os.path.join(d, 'beep.wav')
            if os.path.exists(fp):
                try:
                    self._beep_sound = SoundLoader.load(fp)
                    if self._beep_sound:
                        Logger.info('Pager: beep.wav loaded from %s', fp)
                        break
                except Exception as e:
                    Logger.warning('Pager: sound load error: %s', e)
        if not self._beep_sound:
            Logger.warning('Pager: beep.wav not found, no sound')

        # ── 배경 캔버스 ──
        with self.canvas.before:
            Color(*C_BG)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        # ── 라벨 생성 ──
        common = dict(font_name=FONT_NAME, halign='center', valign='middle')

        self.lbl_header = Label(
            font_size='26sp', color=C_ACCENT,
            pos_hint={'center_x': .5, 'center_y': .91},
            size_hint=(0.9, 0.08), **common)

        self.lbl_status = Label(
            font_size='20sp', color=C_TEXT,
            pos_hint={'center_x': .5, 'center_y': .72},
            size_hint=(0.9, 0.07), **common)

        self.lbl_main = Label(
            font_size='36sp', color=C_ACCENT,
            pos_hint={'center_x': .5, 'center_y': .52},
            size_hint=(0.98, 0.28),
            text_size=(None, None),
            **common)

        self.lbl_sub = Label(
            font_size='20sp', color=C_DIM,
            pos_hint={'center_x': .5, 'center_y': .38},
            size_hint=(0.9, 0.07), **common)

        self.lbl_dots = Label(
            font_size='28sp', color=C_TEXT,
            pos_hint={'center_x': .5, 'center_y': .28},
            size_hint=(0.9, 0.07), **common)

        self.lbl_hint = Label(
            font_size='14sp', color=C_DIM,
            pos_hint={'center_x': .5, 'center_y': .06},
            size_hint=(0.9, 0.05), **common)

        for lbl in (self.lbl_header, self.lbl_status, self.lbl_main,
                     self.lbl_sub, self.lbl_dots, self.lbl_hint):
            lbl.bind(size=lbl.setter('text_size'))
            self.add_widget(lbl)

        # ── 테두리 캔버스 ──
        self.bind(size=self._draw_border, pos=self._draw_border)

        # ── 업데이트 루프 ──
        Clock.schedule_interval(self._tick, 1.0 / 30.0)
        self._refresh_ui()

        # ── 자동 동기화 (1시간마다) ──
        self._auto_sync_interval = 300  # 초 (5분)
        Clock.schedule_once(self._auto_sync_first, 5)  # 앱 시작 5초 후 최초 동기화

    # ───────── 캔버스 헬퍼 ─────────

    def _update_bg(self, *_):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        self._draw_border()

    def _draw_border(self, *_):
        self.canvas.after.clear()
        w, h = self.size
        x, y = self.pos
        with self.canvas.after:
            # 외곽선
            Color(*C_DIM)
            Line(rectangle=(x + 10, y + 10, w - 20, h - 20), width=1)
            # 모서리 장식
            Color(*C_ACCENT)
            cl = 25
            for cx, cy, dx, dy in [
                (x + 10, y + 10, 1, 1),
                (x + w - 10, y + 10, -1, 1),
                (x + 10, y + h - 10, 1, -1),
                (x + w - 10, y + h - 10, -1, -1),
            ]:
                Line(points=[cx, cy, cx + cl * dx, cy], width=1.2)
                Line(points=[cx, cy, cx, cy + cl * dy], width=1.2)
            # 상단/하단 구분선
            Color(*C_DIM)
            Line(points=[x + 35, y + h - 80, x + w - 35, y + h - 80], width=0.7)
            Line(points=[x + 35, y + 50, x + w - 35, y + 50], width=0.7)

    # ───────── 데이터 접근 ─────────

    def _cur_stage(self):
        return self.messages[self.stage_idx] if self.stage_idx < len(self.messages) else None

    def _cur_text(self):
        s = self._cur_stage()
        if not s:
            return None
        ms = s.get('messages', [])
        if self.msg_idx < len(ms):
            m = ms[self.msg_idx]
            return m.get('text', '') if isinstance(m, dict) else str(m)
        return None

    def _cur_time(self):
        s = self._cur_stage()
        if not s:
            return ''
        ms = s.get('messages', [])
        if self.msg_idx < len(ms):
            m = ms[self.msg_idx]
            return m.get('time_info', '') if isinstance(m, dict) else ''
        return ''

    def _msg_count(self):
        s = self._cur_stage()
        return len(s.get('messages', [])) if s else 0

    # ───────── 상태 전이 ─────────

    def _enter_beep(self):
        self.state = ST_BEEPING
        self.timer = 0.0
        self.enc_text = _rand_chars()
        # 비프음 재생
        if self._beep_sound:
            try:
                self._beep_sound.play()
            except Exception:
                pass

    def _enter_decode(self):
        self.state = ST_DECODING
        self.timer = 0.0
        self.dec_progress = 0.0
        # 비프음 정지
        if self._beep_sound:
            try:
                self._beep_sound.stop()
            except Exception:
                pass

    def _enter_reveal(self):
        self.state = ST_REVEALED
        self.timer = 0.0

    def _enter_clear(self):
        self.state = ST_CLEAR
        self.timer = 0.0

    def advance(self):
        """터치 시 다음 상태로 진행"""
        if self.state == ST_IDLE:
            if self._cur_stage():
                self.msg_idx = 0
                self._enter_beep()
        elif self.state == ST_BEEPING:
            self._enter_decode()
        elif self.state == ST_DECODING:
            self._enter_reveal()
        elif self.state == ST_REVEALED:
            if self.msg_idx + 1 < self._msg_count():
                self.msg_idx += 1
                self._enter_beep()
            else:
                self._enter_clear()
        elif self.state == ST_CLEAR:
            self.stage_idx += 1
            self.msg_idx = 0
            if self.stage_idx >= len(self.messages):
                self.state = ST_COMPLETE
            else:
                self.state = ST_IDLE
        elif self.state == ST_COMPLETE:
            self.stage_idx = 0
            self.msg_idx = 0
            self.state = ST_IDLE
        self._refresh_ui()

    def on_touch_down(self, touch):
        # URL 입력창이 떠 있으면 TextInput에 터치 직접 전달
        if self._url_input_visible and self._url_input:
            self._touch_consumed = True  # on_touch_up에서 메뉴 선택 방지
            return super().on_touch_down(touch)
        import time as _time
        self._touch_start_y = touch.y
        self._touch_start_time = _time.time()
        self._touch_consumed = False
        # 롱프레스 타이머
        self._long_press_event = Clock.schedule_once(self._on_long_press, LONG_PRESS_TIME)
        return True

    def on_touch_move(self, touch):
        if self._url_input_visible:
            return super().on_touch_move(touch)
        # 스와이프 감지: 위로 스와이프하면 설정 열기
        dy = touch.y - self._touch_start_y
        if dy > SWIPE_THRESHOLD and not self._touch_consumed:
            self._touch_consumed = True
            if self._long_press_event:
                self._long_press_event.cancel()
            if self.state == ST_SETTINGS:
                self._close_settings()
            else:
                self._open_settings()
        return True

    def on_touch_up(self, touch):
        if self._url_input_visible:
            return super().on_touch_up(touch)
        if self._long_press_event:
            self._long_press_event.cancel()
            self._long_press_event = None
        if self._touch_consumed:
            return True
        # 설정 화면에서는 터치로 메뉴 선택
        if self.state == ST_SETTINGS:
            self._handle_settings_touch(touch)
        else:
            self.advance()
        return True

    def _on_long_press(self, dt):
        """길게 누르기 → 설정 화면 토글"""
        self._touch_consumed = True
        if self.state == ST_SETTINGS:
            self._close_settings()
        else:
            self._open_settings()

    # ───────── 설정 화면 ─────────

    def _open_settings(self):
        self._prev_state = self.state
        self.state = ST_SETTINGS
        self._settings_sel = 0
        self._settings_status = ''
        self._hide_url_input()
        self._refresh_ui()

    def _close_settings(self):
        self._hide_url_input()
        self.state = self._prev_state
        self._refresh_ui()

    def _handle_settings_touch(self, touch):
        """설정 화면 터치 위치로 메뉴 선택 (3분할 버튼)"""
        h = self.height
        y = touch.y
        y_ratio = y / h if h > 0 else 0.5

        # 하단: 닫기 영역 (y < 0.15)
        if y_ratio < 0.15:
            self._close_settings()
            return

        # 상단 85% 영역을 3등분하여 각 버튼에 대응
        # 버튼 영역: center_y=0.52 기준으로 위아래 0.15씩(0.37~0.67)만 인식
        if 0.37 <= y_ratio <= 0.67:
            w = self.width
            x = touch.x
            # 3등분
            if x < w / 3:
                self._show_url_input()
            elif x < w * 2 / 3:
                self._do_sync()
            else:
                self._reload_messages()
        else:
            self._close_settings()

    # ───────── URL 입력 ─────────

    def _show_url_input(self):
        """화면에 TextInput 표시"""
        if self._url_input_visible:
            return
        self._url_input_visible = True

        # 기존 URL
        current_url = ''
        try:
            from calendar_sync_android import get_ics_url
            current_url = get_ics_url() or ''
        except Exception:
            pass

        self._url_input = TextInput(
            text=current_url,
            hint_text='ICS URL here',
            multiline=False,
            font_name='Roboto',
            font_size='14sp',
            size_hint=(0.85, 0.07),
            pos_hint={'center_x': 0.5, 'center_y': 0.52},
            background_color=(0.05, 0.05, 0.15, 1),
            foreground_color=(0, 0.86, 1, 1),
            cursor_color=(0, 0.86, 1, 1),
            hint_text_color=(0.3, 0.3, 0.5, 1),
            padding=[10, 10, 10, 10],
        )
        self._url_input.bind(on_text_validate=self._on_url_submit)
        self.add_widget(self._url_input)
        self._url_input.focus = True

        # 저장/취소 안내
        self._settings_status = 'URL 입력 후 완료(Enter) | 아래 터치 = 취소'
        self._refresh_ui()

    def _hide_url_input(self):
        """TextInput 제거"""
        if self._url_input and self._url_input_visible:
            try:
                self._url_input.focus = False
                self.remove_widget(self._url_input)
            except Exception:
                pass
        self._url_input = None
        self._url_input_visible = False

    def _on_url_submit(self, instance):
        """Enter 누르면 URL 저장"""
        url = instance.text.strip()
        if not url or len(url) < 10:
            self._settings_status = 'URL이 너무 짧습니다'
            self._refresh_ui()
            return
        try:
            from calendar_sync_android import set_ics_url
            set_ics_url(url)
            self._settings_status = 'URL 저장 완료! 동기화 중...'
            self._hide_url_input()
            self._refresh_ui()
            # URL 저장 후 바로 동기화 실행
            self._do_sync()
            return
        except Exception as e:
            self._settings_status = f'저장 실패: {str(e)[:25]}'
        self._hide_url_input()
        self._refresh_ui()

    def _do_sync(self):
        """캘린더 동기화 실행 (백그라운드 스레드)"""
        if self._settings_busy:
            return
        self._settings_busy = True
        self._settings_status = '동기화 중...'
        self._refresh_ui()

        import threading
        def _run():
            try:
                from calendar_sync_android import is_configured, sync_calendar
                if not is_configured():
                    self._settings_status = 'ICS URL 미설정'
                else:
                    ok, msg = sync_calendar()
                    self._settings_status = msg
                    if ok:
                        Clock.schedule_once(lambda dt: self._reload_messages(), 0)
            except Exception as e:
                self._settings_status = f'오류: {str(e)[:30]}'
                Logger.error('Pager sync: %s', traceback.format_exc())
            finally:
                self._settings_busy = False
                Clock.schedule_once(lambda dt: self._refresh_ui(), 0)

        threading.Thread(target=_run, daemon=True).start()

    def _reload_messages(self):
        """messages.json 다시 로드"""
        self.messages = load_messages()
        self.stage_idx = 0
        self.msg_idx = 0
        self._settings_status = f'메시지 로드 완료 ({len(self.messages)}단계)'
        self._refresh_ui()

    # ───────── 자동 동기화 ─────────

    def _auto_sync_first(self, dt):
        """앱 시작 직후 최초 1회 동기화 + 반복 스케줄"""
        self._auto_sync_run()
        Clock.schedule_interval(self._auto_sync_tick, self._auto_sync_interval)

    def _auto_sync_tick(self, dt):
        self._auto_sync_run()

    def _auto_sync_run(self):
        """백그라운드 동기화 — configured일 때만, IDLE일 때만 리로드"""
        import threading
        def _bg():
            try:
                from calendar_sync_android import is_configured, sync_calendar
                if not is_configured():
                    return
                ok, msg = sync_calendar()
                if ok and self.state == ST_IDLE and self.stage_idx == 0:
                    Clock.schedule_once(lambda dt: self._silent_reload(), 0)
                Logger.info('Pager auto-sync: %s', msg)
            except Exception as e:
                Logger.warning('Pager auto-sync error: %s', e)
        threading.Thread(target=_bg, daemon=True).start()

    def _silent_reload(self):
        """상태 표시 없이 메시지만 리로드"""
        self.messages = load_messages()
        self.stage_idx = 0
        self.msg_idx = 0

    # ───────── 메인 루프 ─────────

    def _tick(self, dt):
        self.timer += dt
        self.blink_timer += dt
        if self.blink_timer > 0.5:
            self.blink = not self.blink
            self.blink_timer = 0.0

        changed = False
        if self.state == ST_BEEPING:
            if self.timer >= 1.0:
                self._enter_decode()
            changed = True
        elif self.state == ST_DECODING:
            self.dec_progress = min(1.0, self.timer / 0.9)
            if self.dec_progress >= 1.0:
                self._enter_reveal()
            changed = True
        elif self.state == ST_IDLE:
            changed = True  # 커서 깜빡임

        if changed:
            self._refresh_ui()

    # ───────── UI 갱신 ─────────

    def _refresh_ui(self):
        for lbl in (self.lbl_header, self.lbl_status, self.lbl_main,
                     self.lbl_sub, self.lbl_dots, self.lbl_hint):
            lbl.text = ''

        self.lbl_main.font_size = '36sp'

        if self.state == ST_IDLE:
            self._ui_idle()
        elif self.state == ST_BEEPING:
            self._ui_beep()
        elif self.state == ST_DECODING:
            self._ui_decode()
        elif self.state == ST_REVEALED:
            self._ui_reveal()
        elif self.state == ST_CLEAR:
            self._ui_clear()
        elif self.state == ST_COMPLETE:
            self._ui_complete()
        elif self.state == ST_SETTINGS:
            self._ui_settings()

    def _ui_idle(self):
        stage = self._cur_stage()
        if not stage:
            return
        sn = stage['stage']
        self.lbl_header.text = f'해금 {sn}단계'
        self.lbl_main.text = f'-- 해금 {sn}단계 수신 대기 중 --'
        self.lbl_main.color = list(C_TEXT)
        self.lbl_sub.text = '> 터치하여 수신 시작' if self.blink else ''
        self.lbl_hint.text = '화면을 터치하세요'

    def _ui_beep(self):
        stage = self._cur_stage()
        if stage:
            self.lbl_header.text = f'해금 {stage["stage"]}단계'

        # 펄싱 색상
        pulse = abs(math.sin(self.timer * 6))
        c = [C_TEXT[i] * 0.3 + C_ACCENT[i] * 0.7 * pulse for i in range(3)] + [1.0]
        self.lbl_status.color = c
        self.lbl_status.text = '신호 수신 중...'

        # 글리치 암호 텍스트
        if int(self.timer * 8) % 3 == 0:
            self.lbl_main.text = _rand_chars(len(self.enc_text))
        else:
            self.lbl_main.text = self.enc_text
        self.lbl_main.color = list(C_TEXT)

        # 도트
        interval = 2.14 / 3
        filled = min(3, int(self.timer / interval) + 1)
        self.lbl_dots.text = '● ' * filled + '○ ' * (3 - filled)

    def _ui_decode(self):
        stage = self._cur_stage()
        if stage:
            self.lbl_header.text = f'해금 {stage["stage"]}단계'

        self.lbl_status.text = '-- 복호화 진행 중... --'
        self.lbl_status.color = list(C_DIM)

        original = self._cur_text() or ''
        rc = int(len(original) * self.dec_progress)
        chars = []
        for i, ch in enumerate(original):
            if i < rc:
                chars.append(ch)
            elif ch == ' ':
                chars.append(' ')
            else:
                chars.append(random.choice(string.ascii_uppercase + string.digits))
        self.lbl_main.text = ''.join(chars)
        self.lbl_main.color = list(C_ACCENT)

        # 텍스트 진행 바
        pct = int(self.dec_progress * 100)
        bar_len = 20
        f = int(bar_len * self.dec_progress)
        bar = '#' * f + '-' * (bar_len - f)
        self.lbl_sub.text = f'[{bar}] {pct}%'
        self.lbl_sub.color = list(C_TEXT)

    def _ui_reveal(self):
        stage = self._cur_stage()
        if stage:
            self.lbl_header.text = f'해금 {stage["stage"]}단계'

        # 긴 메시지 요약 표시 (앞 30자 ... 뒤 30자)
        msg = self._cur_text() or ''
        if len(msg) > 80:
            msg = msg[:30] + '\n...\n' + msg[-30:]
        self.lbl_main.text = msg
        self.lbl_main.color = list(C_ACCENT)
        self.lbl_main.text_size = (self.lbl_main.width * 0.98, None)
        self.lbl_main.shorten = False

        ti = self._cur_time()
        if ti:
            self.lbl_sub.text = ti
            self.lbl_sub.color = list(C_DIM)

        remaining = self._msg_count() - self.msg_idx - 1
        if remaining > 0:
            self.lbl_hint.text = f'터치 > 다음 메시지 ({remaining}개 남음)'
        else:
            self.lbl_hint.text = '터치 > 계속'

    def _ui_clear(self):
        self.lbl_main.text = '_CLEAR._'
        self.lbl_main.font_size = '58sp'
        self.lbl_main.color = list(C_ACCENT)
        self.lbl_hint.text = '터치 > 다음 단계'

    def _ui_complete(self):
        self.lbl_main.text = '== 모든 메시지 수신 완료 =='
        self.lbl_main.color = list(C_ACCENT)
        self.lbl_sub.text = f'총 {len(self.messages)}단계 해금 완료'
        self.lbl_sub.color = list(C_TEXT)
        self.lbl_hint.text = '터치 > 처음으로'

    def _ui_settings(self):
        self.lbl_header.text = '설정'
        self.lbl_header.color = list(C_ACCENT)

        # 동기화 상태
        try:
            from calendar_sync_android import is_configured, get_ics_url
            configured = is_configured()
            cur_url = get_ics_url() or ''
        except Exception:
            configured = False
            cur_url = ''

        if configured:
            self.lbl_status.text = '● URL 설정됨'
            self.lbl_status.color = list(C_ACCENT)
        else:
            self.lbl_status.text = '○ ICS URL 미설정'
            self.lbl_status.color = list(C_DIM)

        if not self._url_input_visible:
            # 3개 버튼처럼 보이게
            self.lbl_main.text = '[ URL 입력 ]    [ 동기화 ]    [ 새로고침 ]'
            self.lbl_main.font_size = '24sp'
            self.lbl_main.color = list(C_TEXT)
            self.lbl_sub.text = ''
            self.lbl_sub.color = list(C_TEXT)
        else:
            self.lbl_main.text = ''
            self.lbl_sub.text = ''

        self.lbl_dots.text = self._settings_status
        self.lbl_dots.color = list(C_ACCENT) if '완료' in self._settings_status else list(C_DIM)

        self.lbl_hint.text = '아래 터치 = 닫기 | 위로 스와이프 = 닫기'


# ───────────────────────── 앱 ────────────────────────────────

class PagerApp(App):
    def build(self):
        Logger.info('Pager: build() start')
        Window.clearcolor = (0, 0, 0, 1)
        self.title = 'Beep'
        # 폰트를 Kivy 초기화 후에 등록
        _init_font()
        try:
            return PagerScreen()
        except Exception as e:
            Logger.error('Pager: PagerScreen failed: %s', e)
            Logger.error('Pager: %s', traceback.format_exc())
            # 최소한의 에러 화면
            return Label(text=str(e), color=(1, 0, 0, 1))

    def on_pause(self):
        return True

    def on_resume(self):
        pass


# ───────────────────────── 엔트리포인트 ──────────────────────

if __name__ == '__main__':
    try:
        PagerApp().run()
    except Exception:
        Logger.error('Pager: fatal: %s', traceback.format_exc())
