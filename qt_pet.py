"""Offline Kitty overlay, using the same Qt event loop as the application."""
import math
import random
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import QLabel


class Kitty(QLabel):
    def __init__(self, sprite, cfg):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                         Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.cfg = cfg
        self.sheet = QPixmap(str(sprite))
        if self.sheet.isNull():
            raise RuntimeError("The bundled Kitty sprite is missing.")
        self.frames = {}
        self.size = int(cfg.get("cat_size", 32))
        self.speed = int(cfg.get("speed", 10))
        self.active = self.frozen = False
        self.px, self.py = 500., 500.
        self.idle_time = self.idle_frame = self.frame_count = 0
        self.idle_animation = None
        self.timer = QTimer(self)
        self.timer.setInterval(90)
        self.timer.timeout.connect(self.tick)
        self.set_size(self.size)

    def set_size(self, size):
        self.size = int(size)
        positions = {"idle": [(3, 3)], "alert": [(7, 3)], "tired": [(3, 2)],
                     "sleeping": [(2, 0), (2, 1)], "scratch": [(5, 0), (6, 0), (7, 0)],
                     "N": [(1, 2), (1, 3)], "NE": [(0, 2), (0, 3)], "E": [(3, 0), (3, 1)],
                     "SE": [(5, 1), (5, 2)], "S": [(6, 3), (7, 2)], "SW": [(5, 3), (6, 1)],
                     "W": [(4, 2), (4, 3)], "NW": [(1, 0), (1, 1)]}
        self.frames = {name: [self.sheet.copy(x*32, y*32, 32, 32).scaled(self.size, self.size,
                       Qt.KeepAspectRatio, Qt.FastTransformation) for x, y in cells]
                       for name, cells in positions.items()}
        self.setFixedSize(self.size, self.size)
        self.sprite("idle")

    def sprite(self, name, frame=0):
        frames = self.frames.get(name, self.frames["idle"])
        self.setPixmap(frames[frame % len(frames)])

    def toggle(self, enabled):
        self.active = bool(enabled)
        if self.active:
            cursor = QCursor.pos()
            self.px, self.py = cursor.x()+70., cursor.y()+70.
            self.move(round(self.px-self.size/2), round(self.py-self.size/2))
            self.show()
            self.timer.start()
        else:
            self.timer.stop()
            self.hide()

    def freeze(self):
        self.frozen = not self.frozen
        self.sprite("idle")
        return self.frozen

    def tick(self):
        if self.frozen:
            return
        cursor = QCursor.pos()
        dx, dy = self.px-cursor.x(), self.py-cursor.y()
        distance = math.hypot(dx, dy)
        if distance >= max(self.speed, self.size*1.5):
            self.idle_time = self.idle_frame = 0
            self.idle_animation = None
            self.frame_count += 1
            direction = ("N" if dy/distance > .5 else "S" if dy/distance < -.5 else "") + ("W" if dx/distance > .5 else "E" if dx/distance < -.5 else "")
            self.sprite(direction or "idle", self.frame_count)
            self.px -= dx/distance*self.speed
            self.py -= dy/distance*self.speed
        else:
            self.idle_time = min(self.idle_time+1, 100)
            if self.idle_time > 10 and self.idle_animation is None and random.randrange(100) == 0:
                self.idle_animation = random.choice(["sleeping", "scratch"])
            if self.idle_animation:
                self.sprite(self.idle_animation, self.idle_frame//4)
                self.idle_frame += 1
                if self.idle_frame > 100:
                    self.idle_animation, self.idle_frame = None, 0
            else:
                self.sprite("idle")
        self.move(round(self.px-self.size/2), round(self.py-self.size/2))
