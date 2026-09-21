"""
Kejar-Kejaran di Desa — NPC Pathfinding (UCS vs A*)
Pygame. Grafik memakai sprite sheet asli (TX_Plant, TX_Shadow_Plant, TX_Props,
TX_Shadow, TX_Player, TX_Tileset_Grass) — taruh ke-6 file PNG tsb di folder
yang sama dengan game.py ini supaya bisa jalan.

Kontrol:
    - Panah / WASD  : gerakkan pemain (tahan utk jalan terus, melambat di semak)
    - Klik kiri     : pindah ke petak yang bisa dilewati
    - 1             : algoritma A*
    - 2             : algoritma UCS
    - H             : ganti heuristik A* (manhattan/euclidean/chebyshev/octile)
    - G             : nyala/mati gerak diagonal (8 arah)
    - E             : mode DEBUG — tampilkan node yang dieksplorasi + jalur
    - M             : ganti mode kejar NPC (otomatis / manual) — real-time saja
    - T             : ganti mode REAL-TIME <-> TURN-BASED (giliran)
    - F             : layar penuh / jendela
    - SPACE         : langkah manual NPC (mode manual) ATAU lewati giliran (turn-based)
    - N             : peta baru
    - R             : reset posisi (respawn)
    - ESC           : keluar
"""

import heapq
import math
import os
import random
import sys
import time

import pygame

# ---------------------------------------------------------------------------
# Konfigurasi dasar
# ---------------------------------------------------------------------------
ROWS, COLS, CELL = int(16*1.2), int(22*1.2), int(32*1.2)

# Tipe medan
GRASS, TREE, PROP, BUSH = 0, 1, 2, 3
BUSH_COST = 3  # biaya melintasi semak dalam pathfinding (dulunya sungai)

CHAR_W = CELL           # lebar karakter = 1 petak
CHAR_H = CELL * 2        # tinggi karakter = 2 petak  -> dimensi 1x2

SCREEN_W, SCREEN_H = COLS * CELL, ROWS * CELL + 112  # ruang HUD bawah
FPS = 60

HEURISTIC_NAMES = ["octile", "manhattan", "euclidean", "chebyshev"]

MOVE_ANIM_MS = 260     # lama animasi "jalan" ditampilkan setelah 1 langkah
WALK_FRAME_MS = 90     # lama tiap frame animasi jalan

SS = 2  # faktor supersampling untuk gambar karakter (dirender besar lalu diperkecil agar halus)

# --- Kecepatan gerak (ms per petak) ---
PLAYER_STEP_MS = 130         # kecepatan jalan normal pemain (tahan tombol)
NPC_STEP_MS_DEFAULT = 220    # kecepatan jalan normal NPC (real-time)
BUSH_SLOW_MULT = 2.1         # pengali cooldown langkah saat berada di petak semak


# ---------------------------------------------------------------------------
# Aset sprite — dipotong dari sprite sheet TX_*.png yang disertakan
# (TX_Plant, TX_Shadow_Plant, TX_Props, TX_Shadow, TX_Player, TX_Tileset_Grass)
# ---------------------------------------------------------------------------
ASSET_DIR = os.path.dirname(os.path.abspath(__file__))

# Kotak potong (x0, y0, x1, y1) hasil deteksi otomatis pada tiap sheet 512x512
# (128x128 utk TX_Player, 256x256 utk TX_Tileset_Grass).
PLANT_BOXES = {
    "tree0": (24, 14, 137, 153), "tree1": (161, 17, 256, 153), "tree2": (295, 31, 374, 151),
    "bush0": (38, 198, 60, 217), "bush1": (98, 195, 125, 220), "bush2": (156, 190, 194, 222),
    "bush3": (216, 185, 263, 227), "bush4": (282, 186, 321, 231), "bush5": (346, 190, 386, 225),
}
SHADOW_PLANT_BOXES = {
    "tree0": (48, 100, 134, 152), "tree1": (173, 105, 255, 151), "tree2": (304, 111, 378, 151),
    "bush0": (39, 207, 61, 219), "bush1": (99, 205, 127, 222), "bush2": (160, 206, 197, 223),
    "bush3": (220, 205, 266, 229), "bush4": (285, 209, 323, 233), "bush5": (348, 198, 389, 227),
}
PROPS_BOXES = {
    "chest": (387, 2, 414, 63), "crate": (160, 18, 192, 64), "barrel": (163, 86, 189, 125),
    "urn_small": (162, 153, 190, 189), "urn_tall": (165, 217, 186, 251),
    "rock1": (353, 269, 447, 341), "rock2": (164, 288, 189, 315), "rock3": (227, 303, 253, 343),
}
SHADOW_PROPS_BOXES = {
    "chest": (387, 15, 419, 63), "crate": (160, 30, 199, 64), "barrel": (163, 98, 194, 125),
    "urn_small": (163, 165, 193, 191), "urn_tall": (165, 232, 188, 251),
    "rock1": (353, 269, 450, 341), "rock2": (164, 299, 192, 315), "rock3": (231, 319, 261, 343),
}
PLAYER_BOXES = {
    "front": (6, 14, 27, 58), "back": (38, 10, 59, 58), "side": (69, 13, 90, 58),
    "shadow": (99, 32, 126, 60),
}

TREE_KEYS = ["tree0", "tree1", "tree2"]
BUSH_KEYS = ["bush0", "bush1", "bush2", "bush3", "bush4", "bush5"]
PROP_KEYS = ["chest", "crate", "barrel", "urn_small", "urn_tall", "rock1", "rock2", "rock3"]

# Target tinggi render tiap prop (px, sebelum dikali skala CELL) -> lebar
# ikut menyesuaikan proporsi aslinya.
PROP_TARGET_H = {
    "chest": 1.15, "crate": 1.15, "barrel": 1.05,
    "urn_small": 0.95, "urn_tall": 1.15,
    "rock1": 0.85, "rock2": 0.55, "rock3": 0.6,
}

TREE_TARGET_H = 2.7   # x CELL — pohon menjulang di atas petaknya
BUSH_TARGET_H = 1.35  # x CELL — semak dibuat cukup besar agar terkesan rimbun/lebar
CHAR_ANIM_PAD = 5      # px ruang ekstra di atas sprite karakter utk animasi "hop"


def _load_sheet(name):
    path = os.path.join(ASSET_DIR, name)
    return pygame.image.load(path).convert_alpha()


def _crop(sheet, box):
    x0, y0, x1, y1 = box
    surf = pygame.Surface((x1 - x0, y1 - y0), pygame.SRCALPHA)
    surf.blit(sheet, (0, 0), area=pygame.Rect(x0, y0, x1 - x0, y1 - y0))
    return surf


def _scaled_pair(img, shadow, target_h, smooth=True):
    """Skalakan sprite objek & bayangannya dengan faktor yang SAMA (diturunkan
    dari tinggi target objek) supaya proporsi bayangan tetap pas."""
    w, h = img.get_size()
    scale = target_h / max(1, h)
    fn = pygame.transform.smoothscale if smooth else pygame.transform.scale
    img2 = fn(img, (max(1, round(w * scale)), max(1, round(h * scale))))
    sw, sh = shadow.get_size()
    shadow2 = fn(shadow, (max(1, round(sw * scale)), max(1, round(sh * scale))))
    return img2, shadow2


def tint_surface(surf, color):
    """Beri warna pada sprite (mis. musuh vs pemain) tanpa merusak alpha."""
    out = surf.copy()
    tint = pygame.Surface(out.get_size(), pygame.SRCALPHA)
    tint.fill(color)
    out.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def make_shadow_blob(w, h):
    surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
    pygame.draw.ellipse(surf, (10, 12, 8, 100), (0, 0, max(1, w), max(1, h)))
    return surf


def make_character_frames(base_imgs):
    """base_imgs: dict facing -> Surface dasar (sudah diskalakan ke CHAR_H).
    TX_Player.png cuma menyediakan 1 gambar statis per arah hadap, jadi
    animasi "jalan" disimulasikan lewat sedikit gerakan naik-turun (hop) per
    frame — bayangannya sendiri digambar terpisah & tetap diam di tanah,
    sehingga gerakannya tetap terlihat jelas per arah (depan/belakang/samping)."""
    lifts = (0, 3, 0, 5)  # px terangkat, per frame animasi jalan
    out = {}
    for facing, img in base_imgs.items():
        w, h = img.get_size()
        frames = []
        for lift in lifts:
            canvas = pygame.Surface((w, h + CHAR_ANIM_PAD), pygame.SRCALPHA)
            canvas.blit(img, (0, CHAR_ANIM_PAD - lift))
            frames.append(canvas)
        out[facing] = frames
    return out


# ---------------------------------------------------------------------------
# Assets: dimuat & dipotong dari sprite sheet asli saat startup
# ---------------------------------------------------------------------------
class Assets:
    def __init__(self):
        plant_sheet = _load_sheet("assets\\TX_Plant.png")
        shadow_plant_sheet = _load_sheet("assets\\TX_Shadow_Plant.png")
        props_sheet = _load_sheet("assets\\TX_Props.png")
        shadow_sheet = _load_sheet("assets\\TX_Shadow.png")
        player_sheet = _load_sheet("assets\\TX_Player.png")
        grass_sheet = _load_sheet("assets\\TX_Tileset_Grass.png")

        # --- tanah rumput (dipotong dari area rumput bersih di tileset) ---
        grass_swatches = [(152, 4, 184, 36), (188, 8, 220, 40), (216, 38, 248, 70)]
        self.grass = [
            pygame.transform.scale(_crop(grass_sheet, box), (CELL, CELL))
            for box in grass_swatches
        ]

        # --- pohon (dipakai utk petak TREE, penghalang) ---
        self.trees, self.tree_shadows = [], []
        for k in TREE_KEYS:
            img = _crop(plant_sheet, PLANT_BOXES[k])
            sh = _crop(shadow_plant_sheet, SHADOW_PLANT_BOXES[k])
            img2, sh2 = _scaled_pair(img, sh, CELL * TREE_TARGET_H)
            self.trees.append(img2)
            self.tree_shadows.append(sh2)

        # --- semak (dipakai utk petak BUSH, bisa dilewati tapi melambat) ---
        self.bushes, self.bush_shadows = [], []
        for k in BUSH_KEYS:
            img = _crop(plant_sheet, PLANT_BOXES[k])
            sh = _crop(shadow_plant_sheet, SHADOW_PLANT_BOXES[k])
            img2, sh2 = _scaled_pair(img, sh, CELL * BUSH_TARGET_H)
            self.bushes.append(img2)
            self.bush_shadows.append(sh2)

        # --- properti kecil (peti/kotak/guci/batu) — pengganti "rumah" ---
        self.props, self.prop_shadows = {}, {}
        for k in PROP_KEYS:
            img = _crop(props_sheet, PROPS_BOXES[k])
            sh = _crop(shadow_sheet, SHADOW_PROPS_BOXES[k])
            img2, sh2 = _scaled_pair(img, sh, CELL * PROP_TARGET_H[k])
            self.props[k] = img2
            self.prop_shadows[k] = sh2
        self.prop_kinds = PROP_KEYS

        # --- karakter (pemain & musuh, dari TX_Player.png) ---
        player_base = {
            facing: _scaled_pair(
                _crop(player_sheet, PLAYER_BOXES[facing]),
                _crop(player_sheet, PLAYER_BOXES["shadow"]),
                CHAR_H, smooth=False,
            )[0]
            for facing in ("front", "back", "side")
        }
        enemy_base = {f: tint_surface(img, (255, 150, 140, 255)) for f, img in player_base.items()}

        self.player_frames = make_character_frames(player_base)
        self.enemy_frames = make_character_frames(enemy_base)

        shadow_crop = _crop(player_sheet, PLAYER_BOXES["shadow"])
        front_crop = _crop(player_sheet, PLAYER_BOXES["front"])
        _, self.char_shadow = _scaled_pair(front_crop, shadow_crop, CHAR_H, smooth=False)


# ---------------------------------------------------------------------------
# Util grid
# ---------------------------------------------------------------------------
def in_bounds(r, c):
    return 0 <= r < ROWS and 0 <= c < COLS


def is_passable(grid, r, c):
    return in_bounds(r, c) and grid[r][c] not in (TREE, PROP)


def terrain_cost(grid, r, c):
    return BUSH_COST if grid[r][c] == BUSH else 1


ORTH = [(1, 0), (-1, 0), (0, 1), (0, -1)]
DIAG = [(1, 1), (1, -1), (-1, 1), (-1, -1)]


def neighbors_of(grid, r, c, diagonal):
    dirs = ORTH + DIAG if diagonal else ORTH
    out = []
    for dr, dc in dirs:
        nr, nc = r + dr, c + dc
        if not is_passable(grid, nr, nc):
            continue
        if dr != 0 and dc != 0:
            if not is_passable(grid, r + dr, c) or not is_passable(grid, r, c + dc):
                continue
        out.append((nr, nc))
    return out


def move_cost(grid, r, c, nr, nc):
    base = terrain_cost(grid, nr, nc)
    diagonal = (r != nr and c != nc)
    return base * math.sqrt(2) if diagonal else base


HEURISTICS = {
    "manhattan": lambda a, b: abs(a[0] - b[0]) + abs(a[1] - b[1]),
    "euclidean": lambda a, b: math.hypot(a[0] - b[0], a[1] - b[1]),
    "chebyshev": lambda a, b: max(abs(a[0] - b[0]), abs(a[1] - b[1])),
    "octile": lambda a, b: (
        (lambda dx, dy: (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy))(
            abs(a[0] - b[0]), abs(a[1] - b[1])
        )
    ),
    "zero": lambda a, b: 0,
}


def search(grid, start, goal, diagonal, heuristic_fn):
    """A* generik; UCS = A* dengan heuristik nol. Mengembalikan dict hasil,
    termasuk 'visited' berisi SEMUA node yang sudah di-expand (dipakai mode debug)."""
    t0 = time.perf_counter()
    g_score = {start: 0.0}
    came_from = {}
    counter = 0
    open_heap = [(heuristic_fn(start, goal), counter, start)]
    closed = set()
    visited = []
    nodes_expanded = 0

    while open_heap:
        f, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        closed.add(current)
        nodes_expanded += 1
        visited.append(current)

        if current == goal:
            path = [current]
            k = current
            while k in came_from:
                k = came_from[k]
                path.append(k)
            path.reverse()
            return {
                "path": path,
                "cost": g_score[current],
                "nodes": nodes_expanded,
                "time_ms": (time.perf_counter() - t0) * 1000,
                "visited": visited,
            }

        for nr, nc in neighbors_of(grid, *current, diagonal):
            nb = (nr, nc)
            if nb in closed:
                continue
            g2 = g_score[current] + move_cost(grid, current[0], current[1], nr, nc)
            if nb not in g_score or g2 < g_score[nb] - 1e-9:
                g_score[nb] = g2
                came_from[nb] = current
                counter += 1
                heapq.heappush(open_heap, (g2 + heuristic_fn(nb, goal), counter, nb))

    return {
        "path": None,
        "cost": math.inf,
        "nodes": nodes_expanded,
        "time_ms": (time.perf_counter() - t0) * 1000,
        "visited": visited,
    }


# ---------------------------------------------------------------------------
# Pembuatan peta
# ---------------------------------------------------------------------------
def blank_grid():
    return [[GRASS] * COLS for _ in range(ROWS)]


def place_props(g):
    """Sebar properti kecil (peti/kotak/guci) satu-petak sebagai penghalang —
    tidak ada lagi bentuk bangunan/rumah."""
    count = 14
    placed = tries = 0
    while placed < count and tries < 300:
        tries += 1
        r = random.randint(1, ROWS - 2)
        c = random.randint(1, COLS - 2)
        if g[r][c] != GRASS:
            continue
        g[r][c] = PROP
        placed += 1


def place_trees(g):
    count = 34
    placed = tries = 0
    while placed < count and tries < 400:
        tries += 1
        r, c = random.randint(0, ROWS - 1), random.randint(0, COLS - 1)
        if g[r][c] != GRASS:
            continue
        g[r][c] = TREE
        placed += 1


def place_bush_band(g):
    """Pengganti sungai: jalur semak yang lebar & rimbun, tetap bisa dilewati
    (dengan biaya lebih mahal), meliuk dari atas ke bawah peta."""
    c = 4 + random.randint(0, COLS - 14 - 1)
    drift = 0
    for r in range(ROWS):
        drift += random.choice([-1, 0, 1])
        drift = max(-1, min(1, drift))
        c = max(1, min(COLS - 8, c + drift))
        width = random.choice([5, 6, 6, 7])  # dilebarkan lagi dari revisi sebelumnya
        for w in range(width):
            cc = c + w
            if in_bounds(r, cc):
                g[r][cc] = BUSH


def count_passable(g):
    return sum(1 for r in range(ROWS) for c in range(COLS) if g[r][c] not in (TREE, PROP))


def largest_component_size(g):
    seen = [[False] * COLS for _ in range(ROWS)]
    best = 0
    for r0 in range(ROWS):
        for c0 in range(COLS):
            if g[r0][c0] in (TREE, PROP) or seen[r0][c0]:
                continue
            size = 0
            stack = [(r0, c0)]
            seen[r0][c0] = True
            while stack:
                cr, cc = stack.pop()
                size += 1
                for dr, dc in ORTH:
                    nr, nc = cr + dr, cc + dc
                    if not in_bounds(nr, nc) or g[nr][nc] in (TREE, PROP) or seen[nr][nc]:
                        continue
                    seen[nr][nc] = True
                    stack.append((nr, nc))
            best = max(best, size)
    return best


FIXED_PLAYER_SPAWN = (1, 1)


def nearest_passable_cell(passable, tr, tc):
    return min(passable, key=lambda p: math.hypot(p[0] - tr, p[1] - tc))


def farthest_passable_cell(passable, frm):
    return max(passable, key=lambda p: max(abs(p[0] - frm[0]), abs(p[1] - frm[1])))


def generate_map():
    attempts = 0
    g = blank_grid()
    while True:
        g = blank_grid()
        place_bush_band(g)
        place_props(g)
        place_trees(g)
        attempts += 1
        if largest_component_size(g) >= count_passable(g) * 0.85 or attempts >= 20:
            break
    passable = [(r, c) for r in range(ROWS) for c in range(COLS) if g[r][c] not in (TREE, PROP)]
    return g, passable


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Kejar-Kejaran di Desa — A* vs UCS (Pygame)")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 16)
        self.font_small = pygame.font.SysFont("consolas", 13)
        self.font_tiny = pygame.font.SysFont("consolas", 11)
        self.assets = Assets()

        self.algo = "astar"          # "astar" | "ucs"
        self.heuristic = "octile"
        self.diagonal = True
        self.debug_mode = False      # tampilkan node yang di-expand + jalur
        self.chase_mode = "auto"     # "auto" | "manual" (dipakai saat real-time)
        self.turn_based = False      # False = real-time, True = giliran
        self.player_turn_done = False
        self.speed_ms = NPC_STEP_MS_DEFAULT  # base kecepatan NPC (ditampilkan di HUD)
        self.npc_step_delay = NPC_STEP_MS_DEFAULT  # delay efektif langkah berikutnya (melambat di semak)
        self.npc_timer = 0.0

        # cooldown langkah pemain (utk tahan tombol) — melambat di semak
        self.player_timer = PLAYER_STEP_MS
        self.player_step_ms = PLAYER_STEP_MS

        self.fullscreen = False

        self.toast_text = ""
        self.toast_until = 0.0

        # arah hadap & animasi
        self.player_facing = "front"
        self.npc_facing = "front"
        self.player_last_move = -9999.0
        self.npc_last_move = -9999.0

        # pra-render variasi tekstur tetap acak per-tile agar konsisten
        self.grass_variant = [[random.randint(0, 2) for _ in range(COLS)] for _ in range(ROWS)]
        self.bush_variant = [[random.randint(0, len(self.assets.bushes) - 1) for _ in range(COLS)] for _ in range(ROWS)]
        self.tree_variant = [[random.randint(0, len(self.assets.trees) - 1) for _ in range(COLS)] for _ in range(ROWS)]
        self.prop_variant = [[random.choice(self.assets.prop_kinds) for _ in range(COLS)] for _ in range(ROWS)]

        self.new_map()

    # ---------------- Map lifecycle ----------------
    def new_map(self):
        self.grid, self.passable = generate_map()
        spawn = nearest_passable_cell(self.passable, *FIXED_PLAYER_SPAWN)
        self.player = spawn
        self.npc = farthest_passable_cell(self.passable, self.player)
        self.last_result = None
        self.npc_path = None
        self.player_step_ms = PLAYER_STEP_MS
        self.npc_step_delay = self.speed_ms
        self.player_timer = self.player_step_ms
        self.npc_timer = 0.0
        self.recompute_npc_path()

    def respawn(self):
        spawn = nearest_passable_cell(self.passable, *FIXED_PLAYER_SPAWN)
        self.player = spawn
        self.npc = farthest_passable_cell(self.passable, self.player)
        self.player_step_ms = PLAYER_STEP_MS
        self.npc_step_delay = self.speed_ms
        self.player_timer = self.player_step_ms
        self.recompute_npc_path()

    # ---------------- Search / stats ----------------
    def current_heuristic_fn(self):
        return HEURISTICS["zero"] if self.algo == "ucs" else HEURISTICS[self.heuristic]

    def recompute_npc_path(self):
        res = search(self.grid, self.npc, self.player, self.diagonal, self.current_heuristic_fn())
        self.last_result = res
        self.npc_path = res["path"] or [self.npc]

    def show_toast(self, msg, duration=0.9):
        self.toast_text = msg
        self.toast_until = time.perf_counter() + duration

    def on_capture(self):
        self.show_toast("NPC menangkap pemain! Posisi direset.")
        self.respawn()

    @staticmethod
    def _facing_from_delta(dr, dc):
        """Sprite 'side' sumbernya (TX_Player.png) secara alami menghadap
        KIRI, jadi flip=True dipakai saat bergerak ke KANAN (dc > 0)."""
        if dc != 0:
            return "side", dc > 0
        if dr > 0:
            return "front", False
        if dr < 0:
            return "back", False
        return "front", False

    def npc_step(self):
        self.recompute_npc_path()
        if len(self.npc_path) > 1:
            nr, nc = self.npc_path[1]
            dr, dc = nr - self.npc[0], nc - self.npc[1]
            facing, flip = self._facing_from_delta(dr, dc)
            self.npc_facing = facing
            if dc != 0:
                self._npc_flip_state = flip
            self.npc = (nr, nc)
            self.npc_last_move = time.perf_counter()
            # melambat kalau berjalan MELEWATI/masuk ke petak semak
            self.npc_step_delay = (
                self.speed_ms * BUSH_SLOW_MULT if self.grid[nr][nc] == BUSH else self.speed_ms
            )
        if self.npc == self.player:
            self.on_capture()

    def try_move_player(self, r, c):
        if not is_passable(self.grid, r, c):
            return False
        dr, dc = r - self.player[0], c - self.player[1]
        facing, flip = self._facing_from_delta(dr, dc)
        self.player_facing = facing
        if dc != 0:
            self._player_flip_state = flip
        self.player = (r, c)
        self.player_last_move = time.perf_counter()
        # melambat kalau melangkah masuk ke petak semak
        self.player_step_ms = PLAYER_STEP_MS * BUSH_SLOW_MULT if self.grid[r][c] == BUSH else PLAYER_STEP_MS
        self.player_timer = 0.0
        self.recompute_npc_path()

        if self.turn_based:
            # giliran pemain selesai -> musuh langsung membalas 1 langkah
            if self.npc != self.player:
                self.npc_step()
        return True

    # ---------------- Drawing ----------------
    def draw_tile(self, r, c):
        """Lapisan tanah: selalu rumput. Semak (BUSH) kini digambar sebagai
        objek dekor di atas rumput (lihat _draw_bush_unit) supaya ikut
        di-y-sort dengan pohon/properti/karakter."""
        x, y = c * CELL, r * CELL
        img = self.assets.grass[self.grass_variant[r][c]]
        self.screen.blit(img, (x, y))

    def _draw_tree_unit(self, r, c):
        x, y = c * CELL, r * CELL
        idx = self.tree_variant[r][c]
        img = self.assets.trees[idx]
        sh = self.assets.tree_shadows[idx]
        base = (x + CELL // 2, y + CELL)
        # bayangan selalu digambar dulu (di bawah), lalu objeknya di atas -> pohon
        # tidak pernah tertutup bayangannya sendiri.
        self.screen.blit(sh, sh.get_rect(midbottom=base))
        self.screen.blit(img, img.get_rect(midbottom=base))

    def _draw_prop_unit(self, r, c):
        x, y = c * CELL, r * CELL
        kind = self.prop_variant[r][c]
        img = self.assets.props[kind]
        sh = self.assets.prop_shadows[kind]
        base = (x + CELL // 2, y + CELL)
        self.screen.blit(sh, sh.get_rect(midbottom=base))
        self.screen.blit(img, img.get_rect(midbottom=base))

    def _draw_bush_unit(self, r, c):
        x, y = c * CELL, r * CELL
        idx = self.bush_variant[r][c]
        img = self.assets.bushes[idx]
        sh = self.assets.bush_shadows[idx]
        base = (x + CELL // 2, y + CELL)
        self.screen.blit(sh, sh.get_rect(midbottom=base))
        self.screen.blit(img, img.get_rect(midbottom=base))

    def _draw_character_unit(self, cell, facing, last_move_time, frames_dict, flip):
        """Gambar bayangan lalu sprite karakter, presisi menempel di kaki
        (tanpa offset satu blok) — bayangan tidak pernah menutupi sprite
        pemiliknya karena selalu digambar duluan (lapisan lebih bawah)."""
        r, c = cell
        base = (c * CELL + CELL // 2, r * CELL + CELL)
        shadow = self.assets.char_shadow
        self.screen.blit(shadow, shadow.get_rect(midbottom=base))

        img = self._anim_frame(facing, last_move_time, frames_dict)
        if flip:
            img = pygame.transform.flip(img, True, False)
        self.screen.blit(img, img.get_rect(midbottom=base))

    def draw_decor_and_entities(self):
        """Y-sort: semua objek (pohon, properti, pemain, musuh) digambar
        terurut berdasarkan baris petaknya, sehingga objek yang lebih 'dekat'
        (baris lebih besar/bawah layar) digambar belakangan -> tampak di
        depan objek yang lebih 'jauh' (baris lebih kecil/atas layar).
        Saat baris sama, karakter diprioritaskan tampil di depan dekor."""
        units = []
        for r in range(ROWS):
            for c in range(COLS):
                t = self.grid[r][c]
                if t == TREE:
                    units.append(((r, 0), self._draw_tree_unit, (r, c)))
                elif t == PROP:
                    units.append(((r, 0), self._draw_prop_unit, (r, c)))
                elif t == BUSH:
                    units.append(((r, 0), self._draw_bush_unit, (r, c)))

        units.append((
            (self.player[0], 1), self._draw_character_unit,
            (self.player, self.player_facing, self.player_last_move,
             self.assets.player_frames, self._player_flip()),
        ))
        units.append((
            (self.npc[0], 1), self._draw_character_unit,
            (self.npc, self.npc_facing, self.npc_last_move,
             self.assets.enemy_frames, self._npc_flip()),
        ))

        units.sort(key=lambda u: u[0])
        for _, fn, args in units:
            fn(*args)

    def draw_debug_overlay(self):
        """Mode debug: tampilkan seluruh node yang sudah di-expand algoritma
        pencarian (bukan cuma jalur akhir), supaya proses pencarian terlihat."""
        if not self.debug_mode or not self.last_result:
            return
        visited = self.last_result["visited"]
        if not visited:
            return
        total = max(1, len(visited))
        overlay = pygame.Surface((CELL - 4, CELL - 4), pygame.SRCALPHA)
        show_numbers = total <= 140
        for i, (r, c) in enumerate(visited):
            alpha = int(255 * (0.10 + 0.35 * (i / total)))
            overlay.fill((95, 160, 220, alpha))
            self.screen.blit(overlay, (c * CELL + 2, r * CELL + 2))
            if show_numbers:
                txt = self.font_small.render(str(i), True, (20, 30, 60))
                self.screen.blit(txt, (c * CELL + 3, r * CELL + 2))
        # jalur akhir di atas overlay biru
        if self.npc_path and len(self.npc_path) > 1:
            path_ov = pygame.Surface((CELL - 14, CELL - 14), pygame.SRCALPHA)
            plen = len(self.npc_path)
            for i, (r, c) in enumerate(self.npc_path):
                alpha = int(255 * (0.35 + 0.45 * (i / plen)))
                path_ov.fill((227, 173, 76, alpha))
                self.screen.blit(path_ov, (c * CELL + 7, r * CELL + 7))
        # tandai start (npc) & goal (player) node pencarian
        nr, nc = self.npc
        pr, pc = self.player
        pygame.draw.rect(self.screen, (255, 90, 60), (nc * CELL, nr * CELL, CELL, CELL), 2)
        pygame.draw.rect(self.screen, (80, 220, 120), (pc * CELL, pr * CELL, CELL, CELL), 2)

    def draw_path_overlay(self):
        """Jalur NPC selalu ditampilkan tipis (di luar mode debug) agar mudah dibaca."""
        if self.debug_mode:
            return  # sudah ditangani draw_debug_overlay
        if not self.npc_path or len(self.npc_path) < 2:
            return
        total = len(self.npc_path)
        overlay = pygame.Surface((CELL - 14, CELL - 14), pygame.SRCALPHA)
        for i, (r, c) in enumerate(self.npc_path):
            alpha = int(255 * (0.14 + 0.22 * (i / total)))
            overlay.fill((227, 173, 76, alpha))
            self.screen.blit(overlay, (c * CELL + 7, r * CELL + 7))

    def _anim_frame(self, facing, last_move_time, frames_dict):
        now = time.perf_counter()
        elapsed_ms = (now - last_move_time) * 1000
        if elapsed_ms < MOVE_ANIM_MS:
            frame_idx = int(elapsed_ms // WALK_FRAME_MS) % 4
        else:
            frame_idx = 0  # pose diam
        return frames_dict[facing][frame_idx]

    def _player_flip(self):
        return getattr(self, "_player_flip_state", False)

    def _npc_flip(self):
        return getattr(self, "_npc_flip_state", False)

    def draw_hud(self):
        y0 = ROWS * CELL
        pygame.draw.rect(self.screen, (22, 34, 26), (0, y0, SCREEN_W, SCREEN_H - y0))
        pygame.draw.line(self.screen, (44, 61, 47), (0, y0), (SCREEN_W, y0), 2)

        res = self.last_result
        algo_label = "UCS" if self.algo == "ucs" else f"A* ({self.heuristic})"
        debug_label = "AKTIF" if self.debug_mode else "mati"
        mode_label = "GILIRAN" if self.turn_based else f"real-time ({self.chase_mode})"
        lines_left = [
            f"Algoritma: {algo_label}   |   Diagonal: {'ya' if self.diagonal else 'tidak'}   |   "
            f"Mode: {mode_label}   |   Debug: {debug_label}   |   Layar: "
            + ("penuh" if self.fullscreen else "jendela"),
            f"Node dieksplorasi: {res['nodes'] if res else '-'}   "
            f"Panjang jalur: {len(res['path']) if res and res['path'] else '-'}   "
            + (f"Biaya: {res['cost']:.2f}" if res and res["path"] else "Biaya: -"),
            f"Waktu komputasi: {res['time_ms']:.2f} ms" if res else "",
        ]
        for i, txt in enumerate(lines_left):
            surf = self.font_small.render(txt, True, (230, 240, 225))
            self.screen.blit(surf, (10, y0 + 6 + i * 18))

        help_txt = "1/2 algo  H heuristik  G diagonal  E debug  M mode  T giliran  F fullscreen  N peta  R reset  ESC keluar"
        surf = self.font_tiny.render(help_txt, True, (150, 168, 145))
        self.screen.blit(surf, (10, y0 + 64))

        if self.debug_mode:
            legend1 = "Debug: biru = node yang sudah di-expand (angka = urutan, makin terang makin baru)"
            legend2 = "kuning = jalur akhir NPC   merah = posisi NPC   hijau = posisi target (player)"
            surf2 = self.font_tiny.render(legend1, True, (120, 190, 235))
            surf3 = self.font_tiny.render(legend2, True, (120, 190, 235))
            self.screen.blit(surf2, (10, y0 + 80))
            self.screen.blit(surf3, (10, y0 + 94))

        if self.toast_text and time.perf_counter() < self.toast_until:
            msg = self.font.render(self.toast_text, True, (255, 255, 255))
            box = pygame.Surface((msg.get_width() + 24, msg.get_height() + 14), pygame.SRCALPHA)
            box.fill((224, 83, 61, 235))
            box.blit(msg, (12, 7))
            self.screen.blit(box, (SCREEN_W // 2 - box.get_width() // 2, 12))

    def draw(self):
        self.screen.fill((20, 30, 20))
        for r in range(ROWS):
            for c in range(COLS):
                self.draw_tile(r, c)
        self.draw_debug_overlay()
        self.draw_path_overlay()
        self.draw_decor_and_entities()
        self.draw_hud()
        pygame.display.flip()

    # ---------------- Input / loop ----------------
    def handle_key(self, key):
        move_map = {
            pygame.K_UP: (-1, 0), pygame.K_w: (-1, 0),
            pygame.K_DOWN: (1, 0), pygame.K_s: (1, 0),
            pygame.K_LEFT: (0, -1), pygame.K_a: (0, -1),
            pygame.K_RIGHT: (0, 1), pygame.K_d: (0, 1),
        }
        if key in move_map:
            dr, dc = move_map[key]
            nr, nc = self.player[0] + dr, self.player[1] + dc
            self.try_move_player(nr, nc)
            self.player_timer = 0.0
            return
        if key == pygame.K_1:
            self.algo = "astar"
            self.recompute_npc_path()
        elif key == pygame.K_2:
            self.algo = "ucs"
            self.recompute_npc_path()
        elif key == pygame.K_h:
            i = HEURISTIC_NAMES.index(self.heuristic)
            self.heuristic = HEURISTIC_NAMES[(i + 1) % len(HEURISTIC_NAMES)]
            self.recompute_npc_path()
        elif key == pygame.K_g:
            self.diagonal = not self.diagonal
            self.recompute_npc_path()
        elif key == pygame.K_e:
            self.debug_mode = not self.debug_mode
        elif key == pygame.K_m:
            self.chase_mode = "manual" if self.chase_mode == "auto" else "auto"
            self.npc_timer = 0.0
        elif key == pygame.K_t:
            self.turn_based = not self.turn_based
            self.npc_timer = 0.0
            self.player_timer = self.player_step_ms
            self.show_toast("Mode GILIRAN aktif" if self.turn_based else "Mode REAL-TIME aktif")
        elif key == pygame.K_f:
            self.toggle_fullscreen()
        elif key == pygame.K_SPACE:
            if self.turn_based:
                # lewati giliran pemain -> musuh tetap membalas 1 langkah
                if self.npc != self.player:
                    self.npc_step()
            elif self.chase_mode == "manual":
                self.npc_step()
        elif key == pygame.K_n:
            self.new_map()
        elif key == pygame.K_r:
            self.respawn()
        elif key == pygame.K_ESCAPE:
            pygame.quit()
            sys.exit(0)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if not self.fullscreen:
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
            return
        # coba mode fullscreen yang otomatis diskalakan; kalau driver/GPU tidak
        # mendukung SCALED (mis. tanpa akselerasi renderer), turun ke FULLSCREEN
        # biasa, lalu ke mode jendela kalau tetap gagal.
        for flags in (pygame.FULLSCREEN | pygame.SCALED, pygame.FULLSCREEN, 0):
            try:
                self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
                return
            except pygame.error:
                continue
        self.fullscreen = False

    def handle_click(self, pos):
        x, y = pos
        if y >= ROWS * CELL:
            return
        c, r = x // CELL, y // CELL
        if in_bounds(r, c):
            self.try_move_player(r, c)

    MOVE_KEYS = {
        pygame.K_UP: (-1, 0), pygame.K_w: (-1, 0),
        pygame.K_DOWN: (1, 0), pygame.K_s: (1, 0),
        pygame.K_LEFT: (0, -1), pygame.K_a: (0, -1),
        pygame.K_RIGHT: (0, 1), pygame.K_d: (0, 1),
    }

    def _poll_continuous_movement(self, dt):
        """Gerak halus saat tombol arah DITAHAN (real-time saja). Kecepatan
        melambat otomatis ketika pemain sedang berada di petak semak."""
        if self.turn_based:
            return
        self.player_timer += dt * 1000
        if self.player_timer < self.player_step_ms:
            return
        keys = pygame.key.get_pressed()
        dr = dc = 0
        for k, (kdr, kdc) in self.MOVE_KEYS.items():
            if keys[k]:
                dr, dc = kdr, kdc
                break
        if dr == 0 and dc == 0:
            self.player_timer = self.player_step_ms  # siap gerak instan begitu ditekan lagi
            return
        moved = self.try_move_player(self.player[0] + dr, self.player[1] + dc)
        if not moved:
            self.player_timer = self.player_step_ms

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)
                elif event.type == pygame.KEYDOWN:
                    self.handle_key(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)

            self._poll_continuous_movement(dt)

            if not self.turn_based and self.chase_mode == "auto":
                self.npc_timer += dt * 1000
                if self.npc_timer >= self.npc_step_delay:
                    self.npc_timer = 0.0
                    self.npc_step()

            self.draw()


if __name__ == "__main__":
    Game().run()