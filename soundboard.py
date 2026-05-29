import sys
import random
from pathlib import Path
from collections import defaultdict, deque

from PIL import Image

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QImage, QFont, QPainter, QPainterPath, QFontMetrics
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QGridLayout, QHBoxLayout, QVBoxLayout, QMessageBox, QSizePolicy
)

import pygame


# -----------------------------
# Config
# -----------------------------
BASE_DIR = Path(__file__).parent
IGNORE_DIRS = {"_backup_before_normalize", "__pycache__"}
SPECIAL_RACE = "murloc"

HISTORY_SIZE = 2

PLATE_W, PLATE_H = 320, 190
TITLE_H = 32
LOGO_SIZE = (42, 42)
PLATE_RADIUS = 20

FIXED_LAYOUT = [
    ["pandaren", "human",    "forsaken", "orc"],
    ["naga",     "nightelf", "goblin",   "troll"],
    ["ethereal", "draenei",  "gnome",    "tauren"],
    ["kobold",   "worgen",   "dwarf",    "bloodelf"],
]

HORDE_RACES = {"orc", "troll", "tauren", "bloodelf", "forsaken", "goblin"}
ALLIANCE_RACES = {"human", "nightelf", "draenei", "worgen", "gnome", "dwarf"}
NEUTRAL_RACES = {"pandaren", "naga", "ethereal", "kobold"}

HORDE_LOGO = BASE_DIR / "horde_logo.webp"
ALLIANCE_LOGO = BASE_DIR / "alliance_logo.webp"

APP_QSS = """
QMainWindow {
    background: #111111;
}

QLabel#StatusLabel {
    color: #d0d0d0;
    padding: 6px 2px;
    font-size: 13px;
}

QPushButton {
    border: 1px solid rgba(255, 255, 255, 45);
    border-radius: 19px;
    padding: 8px 12px;
    color: white;
    font-weight: 700;
    background: rgba(40, 40, 40, 140);
}
QPushButton:hover {
    border: 1px solid rgba(255, 255, 255, 90);
    background: rgba(80, 80, 80, 180);
}
QPushButton:pressed {
    background: rgba(255, 255, 255, 40);
}

QPushButton#TurnBtn {
    background: rgba(70, 200, 110, 95);
    border: 1px solid rgba(120, 255, 170, 140);
    border-radius: 19px;
    color: white;
}
QPushButton#TurnBtn:hover {
    background: rgba(80, 220, 120, 140);
    border: 1px solid rgba(170, 255, 200, 220);
}
QPushButton#TurnBtn:pressed {
    background: rgba(60, 180, 100, 180);
}

QPushButton#AttackBtn {
    background: rgba(70, 130, 255, 95);
    border: 1px solid rgba(130, 180, 255, 150);
    border-radius: 19px;
    color: white;
}
QPushButton#AttackBtn:hover {
    background: rgba(90, 150, 255, 145);
    border: 1px solid rgba(180, 210, 255, 220);
}
QPushButton#AttackBtn:pressed {
    background: rgba(60, 110, 220, 180);
}

QPushButton#DeathBtn {
    background: rgba(230, 70, 70, 95);
    border: 1px solid rgba(255, 130, 130, 150);
    border-radius: 19px;
    color: white;
}
QPushButton#DeathBtn:hover {
    background: rgba(255, 90, 90, 145);
    border: 1px solid rgba(255, 180, 180, 220);
}
QPushButton#DeathBtn:pressed {
    background: rgba(200, 60, 60, 180);
}

QPushButton#DeclinedBtn {
    background: rgba(150, 150, 150, 85);
    border: 1px solid rgba(220, 220, 220, 120);
    border-radius: 19px;
    color: white;
}
QPushButton#DeclinedBtn:hover {
    background: rgba(180, 180, 180, 125);
    border: 1px solid rgba(245, 245, 245, 180);
}
QPushButton#DeclinedBtn:pressed {
    background: rgba(140, 140, 140, 170);
}

QPushButton#MurlocBtn {
    background: rgba(0, 151, 167, 225);
    border: 1px solid rgba(150, 240, 255, 140);
    border-radius: 16px;
    padding: 10px 16px;
}
QPushButton#MurlocBtn:hover {
    background: rgba(0, 171, 187, 245);
}

QPushButton#StopBtn {
    background: rgba(85, 85, 85, 225);
    border: 1px solid rgba(200, 200, 200, 80);
    border-radius: 16px;
    padding: 10px 16px;
}
QPushButton#StopBtn:hover {
    background: rgba(105, 105, 105, 245);
}

QPushButton#ShuffleBtn {
    background: rgba(160, 90, 210, 200);
    border: 1px solid rgba(210, 150, 255, 160);
    border-radius: 16px;
    padding: 10px 16px;
    color: white;
    font-weight: 700;
}
QPushButton#ShuffleBtn:hover {
    background: rgba(180, 110, 230, 230);
    border: 1px solid rgba(230, 180, 255, 220);
}
QPushButton#ShuffleBtn:pressed {
    background: rgba(130, 70, 180, 200);
}
"""

# -----------------------------
# Audio
# -----------------------------
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
pygame.mixer.set_num_channels(48)
active_sounds = []


def cleanup_finished_sounds():
    global active_sounds
    active_sounds = [(s, ch) for (s, ch) in active_sounds if ch and ch.get_busy()]


# -----------------------------
# Helpers
# -----------------------------
def discover_races():
    races = []
    for folder in BASE_DIR.iterdir():
        if not folder.is_dir():
            continue
        if folder.name in IGNORE_DIRS:
            continue
        if (folder / f"{folder.name}_turn").is_dir():
            races.append(folder.name)
    return sorted(races)


def find_category_folder(race_name: str, category: str):
    race_dir = BASE_DIR / race_name
    if not race_dir.is_dir():
        return None

    if category == "turn":
        cands = [race_dir / f"{race_name}_turn"]
    elif category == "attack":
        cands = [race_dir / f"{race_name}_attack"]
    elif category == "death":
        cands = [race_dir / f"{race_name}_death", race_dir / f"{race_name}_deeath"]
    elif category == "declined":
        cands = [race_dir / f"{race_name}_decline", race_dir / f"{race_name}_declined"]
    else:
        return None

    for p in cands:
        if p.is_dir():
            return p
    return None


def get_sounds(race_name: str, category: str):
    folder = find_category_folder(race_name, category)
    if not folder:
        return []
    return sorted(folder.glob("*.ogg"))


def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


def rounded_pixmap_from_path(image_path: Path, size=(PLATE_W, PLATE_H), radius=PLATE_RADIUS):
    try:
        img = Image.open(image_path).convert("RGB").resize(size, Image.Resampling.LANCZOS)
        pixmap = pil_to_qpixmap(img)

        rounded = QPixmap(size[0], size[1])
        rounded.fill(Qt.transparent)

        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, size[0], size[1], radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()

        return rounded
    except Exception as e:
        print(f"[IMG ERROR] {image_path}: {e}")
        return None


def get_race_images(race_name: str) -> dict:
    """
    Returns a dict with:
      'default'  -> Path to o.jpg (or None)
      'extras'   -> list of Paths for numbered images (1.jpg, 2.jpg, etc.)
                    sorted, excluding o.jpg
    """
    race_dir = BASE_DIR / race_name
    if not race_dir.is_dir():
        return {"default": None, "extras": []}

    extensions = ("*.jpg", "*.jpeg", "*.png", "*.webp")
    all_imgs = []
    for ext in extensions:
        all_imgs.extend(race_dir.glob(ext))

    # Only direct children (not in subfolders)
    all_imgs = [p for p in all_imgs if p.parent == race_dir]

    default_img = None
    extras = []

    for img in all_imgs:
        if img.stem.lower() == "o":
            default_img = img
        else:
            extras.append(img)

    extras = sorted(extras)
    return {"default": default_img, "extras": extras}


def get_faction_logo_path(race_name: str):
    race = race_name.lower()
    if race in HORDE_RACES and HORDE_LOGO.exists():
        return HORDE_LOGO
    if race in ALLIANCE_RACES and ALLIANCE_LOGO.exists():
        return ALLIANCE_LOGO
    return None


def get_logo_pixmap(race_name: str):
    logo_path = get_faction_logo_path(race_name)
    if not logo_path:
        return None
    return rounded_pixmap_from_path(logo_path, size=LOGO_SIZE, radius=8)


def pretty_race_name(name: str):
    mapping = {
        "bloodelf": "Blood Elf",
        "nightelf": "Night Elf",
    }
    return mapping.get(name.lower(), name.capitalize())


# -----------------------------
# Anti-repeat history
# -----------------------------
play_history = defaultdict(lambda: deque(maxlen=HISTORY_SIZE))


def choose_non_repeating(race: str, category: str, sounds):
    if not sounds:
        return None
    key = (race, category)
    recent = set(play_history[key])
    available = [s for s in sounds if s not in recent]
    chosen = random.choice(available if available else sounds)
    play_history[key].append(chosen)
    return chosen


# -----------------------------
# UI
# -----------------------------
class RacePlate(QWidget):
    def __init__(self, race_name: str, play_cb, parent=None):
        super().__init__(parent)
        self.race = race_name
        self.play_cb = play_cb
        self.setFixedSize(QSize(PLATE_W, PLATE_H))
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

        # Discover images for this race
        img_data = get_race_images(race_name)
        self._default_img = img_data["default"]
        self._extra_imgs  = img_data["extras"]

        # Build full cycle list: [default, extra1, extra2, ...]
        # default is always index 0 if it exists
        self._all_imgs = []
        if self._default_img:
            self._all_imgs.append(self._default_img)
        self._all_imgs.extend(self._extra_imgs)

        self._img_index = 0  # always starts at default (index 0)

        # Background label
        self.bg = QLabel(self)
        self.bg.setGeometry(0, 0, PLATE_W, PLATE_H)
        self.bg.setScaledContents(True)

        # Load initial (default) image
        self._apply_bg(self._img_index)

        # Dark overlay
        self.overlay = QLabel(self)
        self.overlay.setGeometry(0, 0, PLATE_W, PLATE_H)
        self.overlay.setStyleSheet(
            f"background: rgba(0, 0, 0, 70); border-radius: {PLATE_RADIUS}px;"
        )

        # Faction logo top-left
        self.logo = QLabel(self)
        self.logo.setGeometry(12, 10, LOGO_SIZE[0], LOGO_SIZE[1])
        self.logo.setScaledContents(True)
        logo_pm = get_logo_pixmap(race_name)
        if logo_pm:
            self.logo.setPixmap(logo_pm)

        # Title top-right
        race_text = pretty_race_name(race_name)
        title_font = QFont("Arial", 11, QFont.Bold)
        metrics = QFontMetrics(title_font)
        text_width = metrics.horizontalAdvance(race_text)
        title_width = min(text_width + 24, 170)

        self.title = QLabel(race_text, self)
        self.title.setFont(title_font)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setGeometry(PLATE_W - title_width - 12, 12, title_width, TITLE_H)
        self.title.setStyleSheet("""
            color: white;
            background: rgba(0, 0, 0, 115);
            border-radius: 12px;
            padding: 4px 10px;
            font-weight: 800;
            font-size: 14px;
        """)

        # Bottom buttons
        btn_wrap = QWidget(self)
        btn_wrap.setGeometry(10, PLATE_H - 58, PLATE_W - 20, 40)
        row = QHBoxLayout(btn_wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)

        btn_turn     = QPushButton("Turn")
        btn_attack   = QPushButton("Attack")
        btn_death    = QPushButton("Death")
        btn_declined = QPushButton("Declined")

        btn_turn.setObjectName("TurnBtn")
        btn_attack.setObjectName("AttackBtn")
        btn_death.setObjectName("DeathBtn")
        btn_declined.setObjectName("DeclinedBtn")

        btn_turn.clicked.connect(lambda: self.play_cb(self.race, "turn"))
        btn_attack.clicked.connect(lambda: self.play_cb(self.race, "attack"))
        btn_death.clicked.connect(lambda: self.play_cb(self.race, "death"))
        btn_declined.clicked.connect(lambda: self.play_cb(self.race, "declined"))

        for btn in (btn_turn, btn_attack, btn_death, btn_declined):
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(38)
            row.addWidget(btn)

    # ------------------------------------------------------------------
    # Image cycling
    # ------------------------------------------------------------------
    def _apply_bg(self, index: int):
        """Load and display the image at self._all_imgs[index]."""
        if not self._all_imgs:
            self._draw_fallback()
            return

        pm = rounded_pixmap_from_path(
            self._all_imgs[index], size=(PLATE_W, PLATE_H), radius=PLATE_RADIUS
        )
        if pm:
            self.bg.setPixmap(pm)
        else:
            self._draw_fallback()

    def _draw_fallback(self):
        fallback = QPixmap(PLATE_W, PLATE_H)
        fallback.fill(Qt.transparent)
        painter = QPainter(fallback)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(Qt.darkGray)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, PLATE_W, PLATE_H, PLATE_RADIUS, PLATE_RADIUS)
        painter.end()
        self.bg.setPixmap(fallback)

    def advance_image(self):
        """Step to the next image in the cycle (wraps around)."""
        if len(self._all_imgs) <= 1:
            return  # nothing to cycle
        self._img_index = (self._img_index + 1) % len(self._all_imgs)
        self._apply_bg(self._img_index)

    def reset_to_default(self):
        """Jump back to the default (o.jpg) image."""
        self._img_index = 0
        self._apply_bg(self._img_index)

    def has_extra_images(self) -> bool:
        return len(self._all_imgs) > 1


# -----------------------------
# Main Window
# -----------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Small WoW Race Soundboard")
        self.resize(1450, 900)

        self.all_races = discover_races()
        self.has_murloc = any(r.lower() == SPECIAL_RACE for r in self.all_races)

        self.sound_data = {}
        for race in self.all_races:
            self.sound_data[race] = {
                "turn":     get_sounds(race, "turn"),
                "attack":   get_sounds(race, "attack"),
                "death":    get_sounds(race, "death"),
                "declined": get_sounds(race, "declined"),
            }

        # Track all RacePlate widgets so we can call advance_image() on them
        self._plates: list[RacePlate] = []

        central = QWidget()
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(10)

        # ---- Top bar ----
        top = QHBoxLayout()
        top.setSpacing(10)

        if self.has_murloc:
            murloc_name = self._get_race_key("murloc")
            mbtn = QPushButton(f"Murloc ({len(self.sound_data[murloc_name]['turn'])})")
            mbtn.setObjectName("MurlocBtn")
            mbtn.clicked.connect(lambda: self.play_random(murloc_name, "turn"))
            top.addWidget(mbtn, alignment=Qt.AlignLeft)

        # Shuffle Art button
        self.shuffle_btn = QPushButton("🎨  Shuffle Art")
        self.shuffle_btn.setObjectName("ShuffleBtn")
        self.shuffle_btn.setToolTip(
            "Cycle every race plate to its next available image.\n"
            "Races with only o.jpg are unaffected."
        )
        self.shuffle_btn.clicked.connect(self._shuffle_all_art)
        top.addWidget(self.shuffle_btn, alignment=Qt.AlignLeft)

        top.addStretch(1)

        stop_btn = QPushButton("Stop All")
        stop_btn.setObjectName("StopBtn")
        stop_btn.clicked.connect(self.stop_all)
        top.addWidget(stop_btn)

        outer.addLayout(top)

        # ---- Status bar ----
        self.status = QLabel("Ready")
        self.status.setObjectName("StatusLabel")
        outer.addWidget(self.status)

        # ---- Race grid ----
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)

        for row_index, row_data in enumerate(FIXED_LAYOUT):
            for col_index, race_name in enumerate(row_data):
                real_race = self._get_race_key(race_name)
                if real_race and real_race.lower() != SPECIAL_RACE:
                    plate = RacePlate(real_race, self.play_random)
                    grid.addWidget(plate, row_index, col_index)
                    self._plates.append(plate)

        outer.addWidget(grid_host, stretch=1)

    # ------------------------------------------------------------------
    def _get_race_key(self, name_lower: str):
        for race in self.all_races:
            if race.lower() == name_lower.lower():
                return race
        return None

    def _shuffle_all_art(self):
        """Advance every plate's image by one step."""
        advanced = 0
        for plate in self._plates:
            if plate.has_extra_images():
                plate.advance_image()
                advanced += 1
        self.status.setText(
            f"Art shuffled — {advanced} plate(s) updated."
            if advanced else "No plates have alternate art."
        )

    def play_random(self, race: str, category: str):
        sounds = self.sound_data.get(race, {}).get(category, [])
        if not sounds:
            QMessageBox.warning(
                self, "Missing sounds", f"No {category} sounds found for {race}"
            )
            return

        chosen = choose_non_repeating(race, category, sounds)
        if not chosen:
            return

        try:
            snd = pygame.mixer.Sound(str(chosen))
            ch = snd.play()
            if ch is None:
                QMessageBox.warning(self, "Playback busy", "No available audio channels.")
                return

            cleanup_finished_sounds()
            active_sounds.append((snd, ch))
            self.status.setText(
                f"{pretty_race_name(race)} / {category}: {chosen.name}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Playback error", f"Could not play:\n{chosen}\n\n{e}"
            )

    def stop_all(self):
        pygame.mixer.stop()
        self.status.setText("Stopped all sounds")


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()