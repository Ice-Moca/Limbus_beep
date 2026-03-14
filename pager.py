"""
삐삐 (Pager/Beeper) 시뮬레이터
================================
- 16:9 비율 화면 (검은 배경 + 파란 글자)
- 출력 순서: 비프음 → 암호화 텍스트 → 원본 메시지
- 메시지는 messages.json에서 단계별로 관리

조작법:
  SPACE / ENTER : 다음 단계로 진행
  R             : 현재 단계 다시 재생
  ESC / Q       : 종료
"""

import pygame
import sys
import json
import random
import string
import math
import os
import threading

# ─────────────────────────── 설정 ───────────────────────────
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720  # 16:9

BG_COLOR = (0, 0, 0)             # 검은 배경
TEXT_COLOR = (0, 160, 255)        # 파란 글자
DIM_TEXT_COLOR = (0, 80, 130)     # 어두운 파란색 (암호 텍스트)
ACCENT_COLOR = (0, 220, 255)     # 밝은 하늘색 (강조)

FONT_SIZE_LARGE = 72
FONT_SIZE_XLARGE = 110
FONT_SIZE_MEDIUM = 48
FONT_SIZE_SMALL = 36
FONT_SIZE_TINY = 24

FPS = 60

# 비프음 설정
BEEP_DURATION_SEC = 2.14  # beep.mp4 길이 (초)
DOT_COUNT = 3             # 비프 중 표시할 dot 개수

# ─────────────────────────── 경로 ───────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MESSAGES_FILE = os.path.join(BASE_DIR, "messages.json")
FONT_FILE = os.path.join(BASE_DIR, "neodgm.ttf")
# 비프음 파일 경로 - 아래 이름 중 존재하는 파일을 자동 사용
BEEP_SOUND_CANDIDATES = [
    os.path.join(BASE_DIR, name)
    for name in ["beep.wav", "beep.mp3", "beep.ogg", "beep.flac", "beep.m4a"]
]


def load_messages(filepath: str) -> list[dict]:
    """messages.json에서 메시지 목록을 로드한다.
    새 형식: {"stage": 1, "messages": ["msg1", "msg2"]}
    구 형식: {"stage": 1, "message": "msg"} → 자동 변환
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 구 형식 호환: "message" → "messages" 리스트로 변환
    for item in data:
        if "messages" not in item and "message" in item:
            # 줄바꿈으로 구분된 여러 메시지도 개별 항목으로 분리
            item["messages"] = [{"text": line, "time_info": ""} for line in item["message"].split("\n") if line.strip()]
    # stage 순으로 정렬
    data.sort(key=lambda x: x["stage"])
    return data


def generate_encrypted_text(length: int | None = None) -> str:
    """9~13글자 사이의 랜덤 암호화 텍스트를 생성한다."""
    if length is None:
        length = random.randint(9, 13)
    chars = string.ascii_uppercase + string.digits + "!@#$%&*+-=?<>"
    return "".join(random.choice(chars) for _ in range(length))


def generate_beep_sound() -> pygame.mixer.Sound:
    """프로그래밍적으로 비프음을 생성한다 (외부 파일 없을 때 대체용)."""
    sample_rate = 44100
    freq = 1000
    duration_sec = BEEP_DURATION_SEC
    n_samples = int(sample_rate * duration_sec)

    buf = bytearray(n_samples * 2)  # 16-bit mono
    for i in range(n_samples):
        t = i / sample_rate
        # 사인파 + 약간의 감쇠
        envelope = max(0, 1.0 - (i / n_samples) * 0.3)
        value = int(16000 * envelope * math.sin(2 * math.pi * freq * t))
        # 16-bit signed little-endian
        buf[i * 2] = value & 0xFF
        buf[i * 2 + 1] = (value >> 8) & 0xFF

    sound = pygame.mixer.Sound(buffer=bytes(buf))
    return sound


class PagerSimulator:
    """삐삐 시뮬레이터 메인 클래스"""

    # 상태 정의
    STATE_IDLE = "idle"                # 대기 (스페이스바 누르면 시작)
    STATE_BEEPING = "beeping"          # 1. 비프음 + 암호화 텍스트 + dot
    STATE_DECODING = "decoding"        # 2. 복호화 애니메이션 + 사운드 재생
    STATE_REVEALED = "revealed"        # 3. 복호화된 메시지 표시
    STATE_CLEAR = "clear"              # 4. _CLEAR._ 만 표시
    STATE_COMPLETE = "complete"        # 모든 단계 완료
    STATE_SETTINGS = "settings"        # 설정 화면

    def __init__(self):
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)

        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("삐삐 - Pager Simulator")

        self.clock = pygame.time.Clock()

        # 폰트 로드 (Neo둥근모 픽셀 폰트)
        self.font_xlarge = pygame.font.Font(FONT_FILE, FONT_SIZE_XLARGE)
        self.font_large = pygame.font.Font(FONT_FILE, FONT_SIZE_LARGE)
        self.font_medium = pygame.font.Font(FONT_FILE, FONT_SIZE_MEDIUM)
        self.font_small = pygame.font.Font(FONT_FILE, FONT_SIZE_SMALL)
        self.font_tiny = pygame.font.Font(FONT_FILE, FONT_SIZE_TINY)

        # 메시지 로드
        self.messages = load_messages(MESSAGES_FILE)
        self.current_stage_idx = 0
        self.current_msg_idx = 0   # 현재 단계 내 메시지 인덱스

        # 비프음 - 폴더 내 beep.* 파일 자동 탐색
        self.beep_sound = None
        for path in BEEP_SOUND_CANDIDATES:
            if os.path.exists(path):
                self.beep_sound = pygame.mixer.Sound(path)
                print(f"🔊 사운드 파일 로드: {os.path.basename(path)}")
                break
        if self.beep_sound is None:
            self.beep_sound = generate_beep_sound()
            print("🔊 내장 비프음 사용 (beep.* 파일 없음)")

        # 상태
        self.state = self.STATE_IDLE
        self.state_timer = 0
        self.encrypted_text = ""
        self.decode_progress = 0.0  # 0.0 ~ 1.0

        # 스캔라인 효과용
        self.scanline_offset = 0

        # 깜빡임 커서
        self.cursor_visible = True
        self.cursor_timer = 0

        # 설정 화면 관련
        self.settings_selection = 0       # 현재 선택된 메뉴 인덱스
        self.settings_status = ""         # 상태 메시지
        self.settings_busy = False        # 작업 중 여부
        self.prev_state = self.STATE_IDLE # 설정 이전 상태 복귀용

    def get_current_stage(self) -> dict | None:
        """현재 단계 데이터를 반환"""
        if self.current_stage_idx < len(self.messages):
            return self.messages[self.current_stage_idx]
        return None

    def get_current_message_text(self) -> str | None:
        """현재 단계 내 현재 메시지 문자열을 반환"""
        stage = self.get_current_stage()
        if not stage:
            return None
        msgs = stage.get("messages", [stage.get("message", "")])
        if self.current_msg_idx < len(msgs):
            item = msgs[self.current_msg_idx]
            # dict 형식: {"text": "...", "time_info": "..."} 또는 단순 문자열
            if isinstance(item, dict):
                return item.get("text", "")
            return item
        return None

    def get_current_time_info(self) -> str:
        """현재 메시지의 시간 정보를 반환"""
        stage = self.get_current_stage()
        if not stage:
            return ""
        msgs = stage.get("messages", [stage.get("message", "")])
        if self.current_msg_idx < len(msgs):
            item = msgs[self.current_msg_idx]
            if isinstance(item, dict):
                return item.get("time_info", "")
        return ""

    def get_current_stage_msg_count(self) -> int:
        """현재 단계의 메시지 수"""
        stage = self.get_current_stage()
        if not stage:
            return 0
        msgs = stage.get("messages", [stage.get("message", "")])
        return len(msgs)

    def start_beeping(self):
        """비프음 단계 시작 - 사운드 1회 + dot 3개 + 암호화 텍스트 동시 표시"""
        self.state = self.STATE_BEEPING
        self.state_timer = 0
        self.encrypted_text = generate_encrypted_text()
        self.beep_sound.play()  # 1회만 재생

    def start_decoding(self):
        """디코딩 애니메이션 단계 시작 - 사운드 다시 재생"""
        self.state = self.STATE_DECODING
        self.state_timer = 0
        self.decode_progress = 0.0
        self.beep_sound.play()  # 복호화 중 사운드 다시 재생

    def start_revealed(self):
        """복호화된 메시지 출력 단계"""
        self.state = self.STATE_REVEALED
        self.state_timer = 0

    def start_clear(self):
        """_CLEAR._ 표시 단계"""
        self.state = self.STATE_CLEAR
        self.state_timer = 0

    def advance(self):
        """다음 상태로 진행 (SPACE 키)"""
        if self.state == self.STATE_IDLE:
            if self.get_current_stage():
                self.current_msg_idx = 0
                self.start_beeping()
        elif self.state == self.STATE_BEEPING:
            # 비프 스킵 → 바로 디코딩으로
            pygame.mixer.stop()
            self.start_decoding()
        elif self.state == self.STATE_DECODING:
            # 디코딩 스킵 → 메시지 표시
            pygame.mixer.stop()
            self.start_revealed()
        elif self.state == self.STATE_REVEALED:
            # 같은 단계 내에 다음 메시지가 있으면 → 다시 비프부터
            if self.current_msg_idx + 1 < self.get_current_stage_msg_count():
                self.current_msg_idx += 1
                self.start_beeping()
            else:
                # 단계 내 마지막 메시지 → CLEAR 표시
                self.start_clear()
        elif self.state == self.STATE_CLEAR:
            # SPACE → 다음 단계로
            self.current_stage_idx += 1
            self.current_msg_idx = 0
            if self.current_stage_idx >= len(self.messages):
                self.state = self.STATE_COMPLETE
            else:
                self.state = self.STATE_IDLE
        elif self.state == self.STATE_COMPLETE:
            # SPACE → 처음으로 돌아가기
            self.current_stage_idx = 0
            self.current_msg_idx = 0
            self.state = self.STATE_IDLE

    def update(self, dt: float):
        """상태 업데이트 (dt: 초 단위)"""
        self.state_timer += dt
        self.scanline_offset = (self.scanline_offset + dt * 30) % 4
        self.cursor_timer += dt
        if self.cursor_timer > 0.5:
            self.cursor_visible = not self.cursor_visible
            self.cursor_timer = 0

        if self.state == self.STATE_BEEPING:
            # 사운드(2.14초) 끝나면 자동으로 디코딩 시작
            if self.state_timer > BEEP_DURATION_SEC + 0.3:
                self.start_decoding()

        elif self.state == self.STATE_DECODING:
            # 2.14초에 걸쳐 디코딩 (사운드 길이에 맞춤)
            self.decode_progress = min(1.0, self.state_timer / BEEP_DURATION_SEC)
            if self.decode_progress >= 1.0:
                self.start_revealed()

    def draw_scanlines(self):
        """CRT 스캔라인 효과"""
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        for y in range(0, WINDOW_HEIGHT, 4):
            adjusted_y = int(y + self.scanline_offset) % WINDOW_HEIGHT
            pygame.draw.line(overlay, (0, 0, 0, 30), (0, adjusted_y), (WINDOW_WIDTH, adjusted_y))
        self.screen.blit(overlay, (0, 0))

    def draw_border(self):
        """화면 테두리"""
        border_rect = pygame.Rect(10, 10, WINDOW_WIDTH - 20, WINDOW_HEIGHT - 20)
        pygame.draw.rect(self.screen, DIM_TEXT_COLOR, border_rect, 2)

        # 모서리 장식
        corner_len = 30
        corners = [
            (10, 10), (WINDOW_WIDTH - 10, 10),
            (10, WINDOW_HEIGHT - 10), (WINDOW_WIDTH - 10, WINDOW_HEIGHT - 10)
        ]
        for cx, cy in corners:
            dx = 1 if cx == 10 else -1
            dy = 1 if cy == 10 else -1
            pygame.draw.line(self.screen, ACCENT_COLOR, (cx, cy), (cx + corner_len * dx, cy), 2)
            pygame.draw.line(self.screen, ACCENT_COLOR, (cx, cy), (cx, cy + corner_len * dy), 2)

    def draw_header(self):
        """상단 헤더 - 해금 N단계만 크게 표시"""
        stage = self.get_current_stage()
        stage_num = stage["stage"] if stage else "?"

        stage_text = f"해금 {stage_num}단계"
        stage_surf = self.font_medium.render(stage_text, True, ACCENT_COLOR)
        stage_rect = stage_surf.get_rect(centerx=WINDOW_WIDTH // 2, y=35)
        self.screen.blit(stage_surf, stage_rect)

        # 구분선
        pygame.draw.line(self.screen, DIM_TEXT_COLOR, (40, 100), (WINDOW_WIDTH - 40, 100), 1)

    def draw_footer(self):
        """하단 장식선만 표시 (안내 텍스트 제거)"""
        pygame.draw.line(self.screen, DIM_TEXT_COLOR, (30, WINDOW_HEIGHT - 60), (WINDOW_WIDTH - 30, WINDOW_HEIGHT - 60), 1)

    def draw_state_idle(self):
        """대기 상태 화면"""
        stage = self.get_current_stage()
        if not stage:
            return

        # 중앙에 대기 메시지
        text = f"── 해금 {stage['stage']}단계 수신 대기 중 ──"
        surf = self.font_medium.render(text, True, TEXT_COLOR)
        rect = surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 40))
        self.screen.blit(surf, rect)

        # 깜빡이는 커서
        if self.cursor_visible:
            cursor_text = "▶ 신호 수신 준비 완료"
            cursor_surf = self.font_small.render(cursor_text, True, DIM_TEXT_COLOR)
            cursor_rect = cursor_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 40))
            self.screen.blit(cursor_surf, cursor_rect)

    def draw_state_beeping(self):
        """비프음 + dot 3개 + 암호화 텍스트 동시 표시"""
        # 상단: 신호 수신 중 (펄스)
        pulse = abs(math.sin(self.state_timer * 6))
        color = (
            int(TEXT_COLOR[0] * 0.3 + ACCENT_COLOR[0] * 0.7 * pulse),
            int(TEXT_COLOR[1] * 0.3 + ACCENT_COLOR[1] * 0.7 * pulse),
            int(TEXT_COLOR[2] * 0.3 + ACCENT_COLOR[2] * 0.7 * pulse),
        )

        text = "신호 수신 중..."
        surf = self.font_small.render(text, True, color)
        rect = surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 100))
        self.screen.blit(surf, rect)

        # 중앙: 암호화 텍스트 (글리치 효과)
        if int(self.state_timer * 8) % 3 == 0:
            display_text = generate_encrypted_text(len(self.encrypted_text))
        else:
            display_text = self.encrypted_text

        enc_surf = self.font_large.render(display_text, True, TEXT_COLOR)
        enc_rect = enc_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
        self.screen.blit(enc_surf, enc_rect)

        # 하단: dot 3개가 2.14초에 걸쳐 순차 채워짐
        dot_interval = BEEP_DURATION_SEC / DOT_COUNT
        filled = min(DOT_COUNT, int(self.state_timer / dot_interval) + 1)
        beep_indicator = "● " * filled + "○ " * (DOT_COUNT - filled)
        beep_surf = self.font_medium.render(beep_indicator.strip(), True, TEXT_COLOR)
        beep_rect = beep_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 80))
        self.screen.blit(beep_surf, beep_rect)

    def draw_state_decoding(self):
        """디코딩 애니메이션 화면"""
        original = self.get_current_message_text()
        if not original:
            return

        label = "▼ 복호화 진행 중... ▼"
        label_surf = self.font_small.render(label, True, DIM_TEXT_COLOR)
        label_rect = label_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 80))
        self.screen.blit(label_surf, label_rect)

        # 글자 하나씩 복호화되는 효과
        revealed_count = int(len(original) * self.decode_progress)
        display_chars = []
        for i, ch in enumerate(original):
            if i < revealed_count:
                display_chars.append(ch)
            else:
                if ch == ' ':
                    display_chars.append(' ')
                else:
                    display_chars.append(random.choice(string.ascii_uppercase + string.digits))

        display_text = "".join(display_chars)

        # 암호화 화면과 동일한 y 위치 (WINDOW_HEIGHT // 2)
        text_y = WINDOW_HEIGHT // 2 - self.font_large.get_height() // 2
        x_start = WINDOW_WIDTH // 2 - self.font_large.size(display_text)[0] // 2

        for i, ch in enumerate(display_chars):
            color = ACCENT_COLOR if i < revealed_count else DIM_TEXT_COLOR
            ch_surf = self.font_large.render(ch, True, color)
            self.screen.blit(ch_surf, (x_start, text_y))
            x_start += ch_surf.get_width()

        # 진행 바
        bar_width = 600
        bar_height = 12
        bar_x = (WINDOW_WIDTH - bar_width) // 2
        bar_y = WINDOW_HEIGHT // 2 + 70
        pygame.draw.rect(self.screen, DIM_TEXT_COLOR, (bar_x, bar_y, bar_width, bar_height), 1)
        fill_width = int(bar_width * self.decode_progress)
        if fill_width > 0:
            pygame.draw.rect(self.screen, TEXT_COLOR, (bar_x, bar_y, fill_width, bar_height))

    def draw_state_revealed(self):
        """복호화된 메시지만 표시 - 화면 중앙에 한 줄 + 시간 정보"""
        text = self.get_current_message_text()
        if not text:
            return

        msg_surf = self.font_large.render(text, True, ACCENT_COLOR)
        msg_rect = msg_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
        self.screen.blit(msg_surf, msg_rect)

        # 시간 정보가 있으면 아래에 작게 표시
        time_info = self.get_current_time_info()
        if time_info:
            time_surf = self.font_small.render(time_info, True, DIM_TEXT_COLOR)
            time_rect = time_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 65))
            self.screen.blit(time_surf, time_rect)

    def draw_state_clear(self):
        """_CLEAR._ 만 화면 중앙에 크게 표시"""
        clear_text = "_CLEAR._"
        clear_surf = self.font_xlarge.render(clear_text, True, ACCENT_COLOR)
        clear_rect = clear_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
        self.screen.blit(clear_surf, clear_rect)

    def draw_state_complete(self):
        """모든 단계 완료 화면"""
        text1 = "━━ 모든 메시지 수신 완료 ━━"
        surf1 = self.font_medium.render(text1, True, ACCENT_COLOR)
        rect1 = surf1.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 - 40))
        self.screen.blit(surf1, rect1)

        text2 = f"총 {len(self.messages)}단계 해금 완료"
        surf2 = self.font_small.render(text2, True, TEXT_COLOR)
        rect2 = surf2.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2 + 40))
        self.screen.blit(surf2, rect2)

    # ───────────────── 설정 화면 (ICS URL 방식) ─────────────────

    def is_calendar_configured(self) -> bool:
        """캘린더 ICS URL이 설정되어 있는지 확인"""
        try:
            from calendar_sync import is_configured
            return is_configured()
        except Exception:
            return False

    def open_settings(self):
        """설정 화면 열기"""
        self.prev_state = self.state
        self.state = self.STATE_SETTINGS
        self.settings_selection = 0
        self.settings_status = ""
        self.url_input_mode = False   # URL 입력 모드 여부
        self.url_input_text = ""      # URL 입력 버퍼

    def close_settings(self):
        """설정 화면 닫고 이전 상태로 복귀"""
        self.url_input_mode = False
        self.state = self.prev_state

    def start_url_input(self):
        """URL 입력 모드 진입 - 클립보드에서 자동 붙여넣기 시도"""
        self.url_input_mode = True
        self.url_input_text = ""
        # 클립보드에서 URL 자동 가져오기
        try:
            import subprocess
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=3
            )
            clip = result.stdout.strip()
            if clip and ("calendar.google.com" in clip or ".ics" in clip.lower()):
                self.url_input_text = clip
                self.settings_status = "📋 클립보드에서 URL을 가져왔습니다"
            else:
                self.settings_status = "URL을 붙여넣으세요 (Ctrl+V)"
        except Exception:
            self.settings_status = "URL을 붙여넣으세요 (Ctrl+V)"

    def confirm_url_input(self):
        """입력된 URL을 저장"""
        url = self.url_input_text.strip()
        if not url:
            self.settings_status = "❌ URL이 비어있습니다"
            return
        if len(url) < 10:
            self.settings_status = "❌ 유효한 URL을 입력하세요"
            return

        try:
            from calendar_sync import set_ics_url
            set_ics_url(url)
            self.settings_status = "✅ 캘린더 URL 저장 완료!"
            self.url_input_mode = False
        except Exception as e:
            self.settings_status = f"❌ 저장 실패: {str(e)[:40]}"

    def do_calendar_sync(self):
        """캘린더 동기화를 백그라운드 스레드에서 실행"""
        if self.settings_busy:
            return
        if not self.is_calendar_configured():
            self.settings_status = "❌ 먼저 캘린더 URL을 설정하세요"
            return

        self.settings_busy = True
        self.settings_status = "📅 일정 동기화 중..."

        def _sync():
            try:
                from calendar_sync import sync_calendar
                result = sync_calendar()
                if result:
                    self.messages = load_messages(MESSAGES_FILE)
                    self.current_stage_idx = 0
                    self.current_msg_idx = 0
                    self.settings_status = f"✅ 동기화 완료! ({len(self.messages)}단계)"
                else:
                    self.settings_status = "❌ 동기화 실패"
            except Exception as e:
                self.settings_status = f"❌ 오류: {str(e)[:40]}"
            finally:
                self.settings_busy = False

        t = threading.Thread(target=_sync, daemon=True)
        t.start()

    def do_clear_url(self):
        """저장된 캘린더 URL 삭제"""
        try:
            from calendar_sync import clear_ics_url
            clear_ics_url()
            self.settings_status = "✅ URL 삭제 완료"
        except Exception as e:
            self.settings_status = f"❌ 오류: {str(e)[:40]}"

    def handle_settings_input(self, key):
        """설정 화면 키 입력 처리"""
        if self.settings_busy:
            return

        # URL 입력 모드
        if self.url_input_mode:
            if key == pygame.K_ESCAPE:
                self.url_input_mode = False
                self.settings_status = ""
            elif key == pygame.K_RETURN:
                self.confirm_url_input()
            elif key == pygame.K_BACKSPACE:
                self.url_input_text = self.url_input_text[:-1]
            elif key == pygame.K_v and pygame.key.get_mods() & pygame.KMOD_CTRL:
                # Ctrl+V 붙여넣기
                try:
                    import subprocess
                    result = subprocess.run(
                        ["powershell", "-command", "Get-Clipboard"],
                        capture_output=True, text=True, timeout=3
                    )
                    clip = result.stdout.strip()
                    if clip:
                        self.url_input_text = clip
                        self.settings_status = "📋 붙여넣기 완료"
                except Exception:
                    pass
            return

        # 일반 메뉴 모드
        menu_count = 3

        if key == pygame.K_UP:
            self.settings_selection = (self.settings_selection - 1) % menu_count
        elif key == pygame.K_DOWN:
            self.settings_selection = (self.settings_selection + 1) % menu_count
        elif key in (pygame.K_SPACE, pygame.K_RETURN):
            if self.settings_selection == 0:
                # 캘린더 URL 설정 / 변경
                self.start_url_input()
            elif self.settings_selection == 1:
                # 일정 동기화
                self.do_calendar_sync()
            elif self.settings_selection == 2:
                # 돌아가기
                self.close_settings()
        elif key == pygame.K_DELETE or key == pygame.K_BACKSPACE:
            # 선택된 항목이 URL이면 삭제
            if self.settings_selection == 0 and self.is_calendar_configured():
                self.do_clear_url()
        elif key in (pygame.K_ESCAPE, pygame.K_s):
            self.close_settings()

    def draw_state_settings(self):
        """설정 화면 그리기"""
        # 제목
        title = "설정"
        title_surf = self.font_medium.render(title, True, ACCENT_COLOR)
        title_rect = title_surf.get_rect(centerx=WINDOW_WIDTH // 2, y=120)
        self.screen.blit(title_surf, title_rect)

        pygame.draw.line(self.screen, DIM_TEXT_COLOR, (200, 165), (WINDOW_WIDTH - 200, 165), 1)

        # 캘린더 연동 상태
        configured = self.is_calendar_configured()
        status_text = "● URL 설정됨" if configured else "○ 미설정"
        status_color = ACCENT_COLOR if configured else DIM_TEXT_COLOR
        status_surf = self.font_tiny.render(f"Google Calendar: {status_text}", True, status_color)
        status_rect = status_surf.get_rect(centerx=WINDOW_WIDTH // 2, y=185)
        self.screen.blit(status_surf, status_rect)

        # URL 입력 모드
        if self.url_input_mode:
            self._draw_url_input()
            return

        # 메뉴 항목
        menu_items = [
            "캘린더 URL 변경" if configured else "캘린더 URL 설정",
            "일정 동기화",
            "돌아가기",
        ]

        menu_y_start = 250
        for i, item in enumerate(menu_items):
            is_selected = (i == self.settings_selection)
            color = ACCENT_COLOR if is_selected else TEXT_COLOR
            prefix = "▶ " if is_selected else "   "

            item_surf = self.font_small.render(f"{prefix}{item}", True, color)
            item_rect = item_surf.get_rect(centerx=WINDOW_WIDTH // 2, y=menu_y_start + i * 50)
            self.screen.blit(item_surf, item_rect)

            if is_selected:
                underline_y = item_rect.bottom + 2
                pygame.draw.line(self.screen, color,
                                 (item_rect.left, underline_y),
                                 (item_rect.right, underline_y), 1)

        # 상태 메시지
        if self.settings_status:
            show = True
            if self.settings_busy:
                show = self.cursor_visible
            if show:
                st_surf = self.font_tiny.render(self.settings_status, True, TEXT_COLOR)
                st_rect = st_surf.get_rect(centerx=WINDOW_WIDTH // 2, y=450)
                self.screen.blit(st_surf, st_rect)

        # 하단 안내
        hint = "[↑↓] 이동  [SPACE] 선택  [S/ESC] 닫기"
        hint_surf = self.font_tiny.render(hint, True, DIM_TEXT_COLOR)
        hint_rect = hint_surf.get_rect(centerx=WINDOW_WIDTH // 2, y=550)
        self.screen.blit(hint_surf, hint_rect)

    def _draw_url_input(self):
        """URL 입력 화면 그리기"""
        # 안내 텍스트
        guide = "Google Calendar 비공개 iCal URL을 입력하세요"
        guide_surf = self.font_small.render(guide, True, TEXT_COLOR)
        guide_rect = guide_surf.get_rect(centerx=WINDOW_WIDTH // 2, y=230)
        self.screen.blit(guide_surf, guide_rect)

        # 입력 박스
        box_x = 100
        box_y = 290
        box_w = WINDOW_WIDTH - 200
        box_h = 40
        pygame.draw.rect(self.screen, DIM_TEXT_COLOR, (box_x, box_y, box_w, box_h), 1)

        # URL 텍스트 (길면 끝부분만 표시)
        display_url = self.url_input_text
        max_chars = 60
        if len(display_url) > max_chars:
            display_url = "..." + display_url[-(max_chars - 3):]

        # 커서 깜빡임
        if self.cursor_visible:
            display_url += "│"

        url_surf = self.font_tiny.render(display_url, True, ACCENT_COLOR)
        url_rect = url_surf.get_rect(midleft=(box_x + 10, box_y + box_h // 2))
        self.screen.blit(url_surf, url_rect)

        # 상태 메시지
        if self.settings_status:
            st_surf = self.font_tiny.render(self.settings_status, True, TEXT_COLOR)
            st_rect = st_surf.get_rect(centerx=WINDOW_WIDTH // 2, y=360)
            self.screen.blit(st_surf, st_rect)

        # 하단 안내
        hint = "[Ctrl+V] 붙여넣기  [ENTER] 확인  [ESC] 취소"
        hint_surf = self.font_tiny.render(hint, True, DIM_TEXT_COLOR)
        hint_rect = hint_surf.get_rect(centerx=WINDOW_WIDTH // 2, y=420)
        self.screen.blit(hint_surf, hint_rect)

    def draw(self):
        """화면 그리기"""
        self.screen.fill(BG_COLOR)

        self.draw_border()

        # 설정 화면은 자체 헤더/푸터 사용
        if self.state == self.STATE_SETTINGS:
            self.draw_state_settings()
        else:
            self.draw_header()
            self.draw_footer()

            # 상태별 화면
            if self.state == self.STATE_IDLE:
                self.draw_state_idle()
            elif self.state == self.STATE_BEEPING:
                self.draw_state_beeping()
            elif self.state == self.STATE_DECODING:
                self.draw_state_decoding()
            elif self.state == self.STATE_REVEALED:
                self.draw_state_revealed()
            elif self.state == self.STATE_CLEAR:
                self.draw_state_clear()
            elif self.state == self.STATE_COMPLETE:
                self.draw_state_complete()

        # CRT 스캔라인 효과
        self.draw_scanlines()

        pygame.display.flip()

    def replay_current_stage(self):
        """현재 단계 다시 재생"""
        if self.get_current_stage():
            self.current_msg_idx = 0
            self.state = self.STATE_IDLE

    def run(self):
        """메인 루프"""
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if self.state == self.STATE_SETTINGS:
                        # 설정 화면 전용 입력
                        self.handle_settings_input(event.key)
                    else:
                        if event.key in (pygame.K_ESCAPE, pygame.K_q):
                            running = False
                        elif event.key == pygame.K_s:
                            # S키로 설정 화면 열기
                            self.open_settings()
                        elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                            self.advance()
                        elif event.key == pygame.K_r:
                            if self.state in (self.STATE_REVEALED, self.STATE_CLEAR):
                                self.replay_current_stage()

            self.update(dt)
            self.draw()

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    # --sync 인자가 있으면 Google Calendar 동기화 후 실행
    if "--sync" in sys.argv:
        try:
            from calendar_sync import sync_calendar
            sync_calendar()
        except Exception as e:
            print(f"⚠️ 캘린더 동기화 실패: {e}")
            print("   기존 messages.json으로 실행합니다.")

    sim = PagerSimulator()
    sim.run()
