"""
Kejar-Kejaran di Desa — NPC Pathfinding (UCS vs A*)
Port dari game.html (canvas/JS) ke Python + Pygame, memakai aset sprite-sheet
(TX_Player, TX_Props, TX_Plant, TX_Tileset_Grass, dst).

Kontrol:
    - Panah / WASD  : gerakkan pemain
    - Klik kiri     : pindah ke petak yang bisa dilewati
    - 1             : algoritma A*
    - 2             : algoritma UCS
    - H             : ganti heuristik A* (manhattan/euclidean/chebyshev/octile)
    - G             : nyala/mati gerak diagonal (8 arah)
    - E             : mode DEBUG — tampilkan node yang sudah di-expand NPC
    - M             : ganti mode kejar NPC (otomatis / manual)
    - SPACE         : langkah manual NPC (saat mode manual)
    - N             : peta baru
    - R             : reset posisi (respawn)
    - ESC           : keluar

Catatan aset:
    Karakter (pemain & NPC) memakai sprite arah depan/belakang/samping dari
    TX_Player.png. Sheet ini hanya berisi satu pose per arah (tanpa siklus
    jalan multi-frame), jadi "animasi" dibuat secara prosedural: posisi
    ditween-kan antar petak + lompatan kecil (hop) saat melangkah, dan efek
    napas halus saat diam. Ini murni visual, tidak mengubah logika/gameplay.
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
ROWS, COLS, CELL = 16, 22, 32
BUSH_COST = 4  # biaya melintasi semak (dulu: sungai)
GRASS, TREE, PROP, BUSH = 0, 1, 2, 3

SCREEN_W, SCREEN_H = COLS * CELL, ROWS * CELL + 108  # ruang HUD bawah
FPS = 60

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

HEURISTIC_NAMES = ["octile", "manhattan", "euclidean", "chebyshev"]

# --- Animasi karakter -------------------------------------------------------
MOVE_ANIM_MS = 130      # lama tween perpindahan satu petak
HOP_HEIGHT = 6          # tinggi lompatan kecil (px) saat melangkah
IDLE_BREATHE_AMPL = 1.4 # amplitudo goyangan halus saat diam (px)
IDLE_BREATHE_SPEED = 2.4

# ---------------------------------------------------------------------------
# Rect potongan sprite-sheet (x, y, w, h) dalam koordinat native gambar
# ---------------------------------------------------------------------------
PLAYER_SHEET_RECTS = {
    "front": (0, 0, 32, 64),
    "back": (32, 0, 32, 64),
    "side": (64, 0, 32, 64),
    "shadow": (96, 0, 32, 64),
}

TREE_RECTS = [
    (20, 10, 121, 147),
    (157, 13, 103, 144),
    (291, 27, 87, 128),
]

BUSH_RECTS = [
    (34, 194, 30, 27),
    (94, 191, 35, 33),
    (152, 186, 46, 40),
    (212, 181, 55, 50),
    (278, 182, 47, 53),
    (342, 186, 48, 43),
]

GRASS_RECTS = [
    (0, 0, 32, 32),
    (200, 20, 32, 32),
    (100, 60, 32, 32),
    (224, 70, 32, 32),
]

# props pengganti "rumah": box/peti, kotak/krat, tong, dan guci
PROP_RECTS = [
    (160, 16, 32, 52),   # krat kayu (crate)
    (96, 28, 32, 36),    # peti kecil (chest)
    (160, 150, 32, 42),  # tong (barrel)
    (162, 215, 30, 40),  # guci kecil
    (160, 282, 32, 38),  # guci/pot besar
]


def load_sheet(name):
    path = os.path.join(ASSET_DIR, name)
    return pygame.image.load(path).convert_alpha()


def cut(sheet, rect):
    return sheet.subsurface(pygame.Rect(*rect)).copy()


class Assets:
    def __init__(self):
        player_sheet = load_sheet("TX_Player.png")
        plant_sheet = load_sheet("TX_Plant.png")
        grass_sheet = load_sheet("TX_Tileset_Grass.png")
        props_sheet = load_sheet("TX_Props.png")

        self.player_front = cut(player_sheet, PLAYER_SHEET_RECTS["front"])
        self.player_back = cut(player_sheet, PLAYER_SHEET_RECTS["back"])
        self.player_side = cut(player_sheet, PLAYER_SHEET_RECTS["side"])
        self.char_shadow = cut(player_sheet, PLAYER_SHEET_RECTS["shadow"])

        self.grass = [cut(grass_sheet, r) for r in GRASS_RECTS]
        self.trees = [cut(plant_sheet, r) for r in TREE_RECTS]
        self.bushes = [cut(plant_sheet, r) for r in BUSH_RECTS]
        self.props = [cut(props_sheet, r) for r in PROP_RECTS]

        # versi NPC: sprite pemain yang di-tint merah
        self.npc_front = self._tint(self.player_front, (224, 83, 61))
        self.npc_back = self._tint(self.player_back, (224, 83, 61))
        self.npc_side = self._tint(self.player_side, (224, 83, 61))

    @staticmethod
    def _tint(surface, color):
        img = surface.copy()
        colored = pygame.Surface(img.get_size(), pygame.SRCALPHA)
        colored.fill(color)
        img.blit(colored, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return img


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
    """A* generik; UCS = A* dengan heuristik nol. Mengembalikan dict hasil."""
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
    """Sebar obstacle berupa props satu-petak (krat/peti/tong/guci),
    menggantikan bentuk rumah/bangunan."""
    count = 16
    placed = tries = 0
    while placed < count and tries < 400:
        tries += 1
        r, c = random.randint(0, ROWS - 1), random.randint(0, COLS - 1)
        if g[r][c] != GRASS:
            continue
        g[r][c] = PROP
        placed += 1


def place_trees(g):
    count = 40
    placed = tries = 0
    while placed < count and tries < 400:
        tries += 1
        r, c = random.randint(0, ROWS - 1), random.randint(0, COLS - 1)
        if g[r][c] != GRASS:
            continue
        g[r][c] = TREE
        placed += 1


def place_bush_belt(g):
    """Sabuk semak lebar menggantikan sungai (dulu RIVER, kini BUSH)."""
    c = 5 + random.randint(0, COLS - 10 - 1)
    drift = 0
    for r in range(ROWS):
        drift += random.choice([-1, 1])
        drift = max(-1, min(1, drift))
        c = max(2, min(COLS - 5, c + drift))
        width = 3 + random.choice([-1, 0, 0, 1, 2])  # lebar 2..5, mayoritas 3-4
        width = max(2, min(5, width))
        for w in range(width):
            cc = c + w
            if in_bounds(r, cc) and g[r][cc] != PROP:
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
        place_bush_belt(g)
        place_props(g)
        place_trees(g)
        attempts += 1
        if largest_component_size(g) >= count_passable(g) * 0.85 or attempts >= 20:
            break
    passable = [(r, c) for r in range(ROWS) for c in range(COLS) if g[r][c] not in (TREE, PROP)]
    return g, passable


# ---------------------------------------------------------------------------
# Animasi entitas (tween antar petak + hop + napas idle) — murni visual
# ---------------------------------------------------------------------------
class CharAnim:
    def __init__(self, cell):
        self.from_cell = cell
        self.to_cell = cell
        self.start = -9999.0
        self.facing = (1, 0)  # default menghadap depan/bawah

    def move_to(self, new_cell):
        if new_cell == self.to_cell:
            return
        dr = new_cell[0] - self.to_cell[0]
        dc = new_cell[1] - self.to_cell[1]
        if dr != 0 or dc != 0:
            self.facing = (dr, dc)
        self.from_cell = self.to_cell
        self.to_cell = new_cell
        self.start = time.perf_counter()

    def snap_to(self, cell):
        self.from_cell = cell
        self.to_cell = cell
        self.start = -9999.0

    def pixel_center(self, now):
        t = (now - self.start) / (MOVE_ANIM_MS / 1000.0)
        t = max(0.0, min(1.0, t))
        # smoothstep untuk gerak yang lebih halus
        smooth = t * t * (3 - 2 * t)
        r0, c0 = self.from_cell
        r1, c1 = self.to_cell
        r = r0 + (r1 - r0) * smooth
        c = c0 + (c1 - c0) * smooth
        x = c * CELL + CELL / 2
        y = r * CELL + CELL / 2
        moving = t < 1.0
        if moving:
            hop = -math.sin(math.pi * t) * HOP_HEIGHT
        else:
            hop = -abs(math.sin(now * IDLE_BREATHE_SPEED)) * IDLE_BREATHE_AMPL
        return x, y + hop, moving


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
        self.font_tiny = pygame.font.SysFont("consolas", 10)
        self.assets = Assets()

        self.algo = "astar"          # "astar" | "ucs"
        self.heuristic = "octile"
        self.diagonal = True
        self.show_explored = False   # mode DEBUG
        self.chase_mode = "auto"     # "auto" | "manual"
        self.speed_ms = 220
        self.npc_timer = 0.0

        self.toast_text = ""
        self.toast_until = 0.0

        # pra-render varian tekstur tetap acak per-tile agar tampilan konsisten
        self.grass_variant = [[random.randint(0, len(self.assets.grass) - 1) for _ in range(COLS)] for _ in range(ROWS)]
        self.tree_variant = [[random.randint(0, len(self.assets.trees) - 1) for _ in range(COLS)] for _ in range(ROWS)]
        self.bush_variant = [[random.randint(0, len(self.assets.bushes) - 1) for _ in range(COLS)] for _ in range(ROWS)]
        self.prop_variant = [[random.randint(0, len(self.assets.props) - 1) for _ in range(COLS)] for _ in range(ROWS)]

        self.new_map()

    # ---------------- Map lifecycle ----------------
    def new_map(self):
        self.grid, self.passable = generate_map()
        spawn = nearest_passable_cell(self.passable, *FIXED_PLAYER_SPAWN)
        self.player = spawn
        self.npc = farthest_passable_cell(self.passable, self.player)
        self.player_anim = CharAnim(self.player)
        self.player_anim.facing = (1, 0)
        self.npc_anim = CharAnim(self.npc)
        self.npc_anim.facing = (1, 0)
        self.last_result = None
        self.npc_path = None
        self.recompute_npc_path()

    def respawn(self):
        spawn = nearest_passable_cell(self.passable, *FIXED_PLAYER_SPAWN)
        self.player = spawn
        self.npc = farthest_passable_cell(self.passable, self.player)
        self.player_anim.snap_to(self.player)
        self.npc_anim.snap_to(self.npc)
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

    def npc_step(self):
        self.recompute_npc_path()
        if len(self.npc_path) > 1:
            self.npc = self.npc_path[1]
            self.npc_anim.move_to(self.npc)
        if self.npc == self.player:
            self.on_capture()

    def try_move_player(self, r, c):
        if not is_passable(self.grid, r, c):
            return
        self.player = (r, c)
        self.player_anim.move_to(self.player)
        self.recompute_npc_path()

    # ---------------- Drawing ----------------
    def draw_tile(self, r, c):
        """Lapisan dasar tanah. TREE/PROP/BUSH tetap berdiri di atas rumput."""
        x, y = c * CELL, r * CELL
        img = self.assets.grass[self.grass_variant[r][c]]
        self.screen.blit(img, (x, y))

    @staticmethod
    def _draw_soft_shadow(screen, cx, bottom_y, width, height):
        shadow = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (20, 15, 10, 95), shadow.get_rect())
        rect = shadow.get_rect(center=(cx, bottom_y - height * 0.3))
        screen.blit(shadow, rect)

    def draw_decor(self, r, c):
        """Digambar sesudah tile dasar agar bisa 'menjulang' di atas petak."""
        t = self.grid[r][c]
        x, y = c * CELL, r * CELL
        cx = x + CELL // 2
        base_y = y + CELL - 2

        if t == TREE:
            idx = self.tree_variant[r][c]
            tree = self.assets.trees[idx]
            self._draw_soft_shadow(self.screen, cx, base_y, int(CELL * 0.9), int(CELL * 0.4))
            th = int(CELL * 2.6)
            tw = int(th * tree.get_width() / tree.get_height())
            timg = pygame.transform.smoothscale(tree, (tw, th))
            trect = timg.get_rect(midbottom=(cx, y + CELL - 4))
            self.screen.blit(timg, trect)

        elif t == PROP:
            idx = self.prop_variant[r][c]
            prop = self.assets.props[idx]
            self._draw_soft_shadow(self.screen, cx, base_y, int(CELL * 0.8), int(CELL * 0.32))
            ph = int(CELL * 1.25)
            pw = int(ph * prop.get_width() / prop.get_height())
            pimg = pygame.transform.smoothscale(prop, (pw, ph))
            prect = pimg.get_rect(midbottom=(cx, base_y))
            self.screen.blit(pimg, prect)

        elif t == BUSH:
            idx = self.bush_variant[r][c]
            bush = self.assets.bushes[idx]
            # sedikit lebih besar dari petak agar sabuk semak terlihat menyatu/rimbun
            bh = int(CELL * 1.35)
            bw = int(bh * bush.get_width() / bush.get_height())
            bimg = pygame.transform.smoothscale(bush, (bw, bh))
            brect = bimg.get_rect(midbottom=(cx, y + CELL - 1))
            self.screen.blit(bimg, brect)

    def draw_debug_overlay(self):
        """Mode DEBUG: highlight semua node yang sudah di-expand NPC untuk
        mencapai pemain, plus urutan ekspansinya bila jumlahnya tidak terlalu
        banyak, ditambah penanda titik awal (NPC) dan titik tujuan (pemain)."""
        if not self.show_explored or not self.last_result or not self.last_result["visited"]:
            return
        visited = self.last_result["visited"]
        total = max(1, len(visited))
        overlay = pygame.Surface((CELL - 4, CELL - 4), pygame.SRCALPHA)
        show_numbers = total <= 90
        for i, (r, c) in enumerate(visited):
            alpha = int(255 * (0.10 + 0.42 * (i / total)))
            overlay.fill((95, 160, 220, alpha))
            self.screen.blit(overlay, (c * CELL + 2, r * CELL + 2))
            pygame.draw.rect(
                self.screen, (60, 120, 190, 160),
                (c * CELL + 2, r * CELL + 2, CELL - 4, CELL - 4), 1
            )
            if show_numbers:
                txt = self.font_tiny.render(str(i), True, (15, 30, 50))
                self.screen.blit(txt, (c * CELL + 3, r * CELL + 3))

        # tandai titik mulai pencarian (posisi NPC) dan tujuan (posisi pemain)
        nr, nc = self.npc
        pr, pc = self.player
        pygame.draw.rect(self.screen, (224, 83, 61), (nc * CELL, nr * CELL, CELL, CELL), 2)
        pygame.draw.rect(self.screen, (90, 200, 110), (pc * CELL, pr * CELL, CELL, CELL), 2)

    def draw_path_overlay(self):
        if not self.npc_path or len(self.npc_path) < 2:
            return
        total = len(self.npc_path)
        overlay = pygame.Surface((CELL - 14, CELL - 14), pygame.SRCALPHA)
        for i, (r, c) in enumerate(self.npc_path):
            alpha = int(255 * (0.14 + 0.22 * (i / total)))
            overlay.fill((227, 173, 76, alpha))
            self.screen.blit(overlay, (c * CELL + 7, r * CELL + 7))

    def draw_character(self, anim, front_img, back_img, side_img, shadow_img, now):
        x, y, _moving = anim.pixel_center(now)
        srect = shadow_img.get_rect(center=(x, y + CELL * 0.30))
        self.screen.blit(shadow_img, srect)

        dr, dc = anim.facing
        if dr > 0:
            img = front_img
        elif dr < 0:
            img = back_img
        else:
            img = side_img
        flip = dc < 0
        if flip:
            img = pygame.transform.flip(img, True, False)

        # dimensi karakter: 1 petak lebar x 2 petak tinggi (mengikuti rasio 32x64 sprite)
        h = CELL * 2
        w = int(h * img.get_width() / img.get_height())
        img2 = pygame.transform.smoothscale(img, (w, h))
        rect = img2.get_rect(midbottom=(x, y + CELL * 0.38))
        self.screen.blit(img2, rect)

    def draw_entities(self):
        now = time.perf_counter()
        self.draw_character(
            self.player_anim,
            self.assets.player_front, self.assets.player_back, self.assets.player_side,
            self.assets.char_shadow, now,
        )
        self.draw_character(
            self.npc_anim,
            self.assets.npc_front, self.assets.npc_back, self.assets.npc_side,
            self.assets.char_shadow, now,
        )

    def draw_hud(self):
        y0 = ROWS * CELL
        pygame.draw.rect(self.screen, (22, 34, 26), (0, y0, SCREEN_W, SCREEN_H - y0))
        pygame.draw.line(self.screen, (44, 61, 47), (0, y0), (SCREEN_W, y0), 2)

        res = self.last_result
        algo_label = "UCS" if self.algo == "ucs" else f"A* ({self.heuristic})"
        debug_label = "ON" if self.show_explored else "off"
        lines_left = [
            f"Algoritma: {algo_label}   |   Diagonal: {'ya' if self.diagonal else 'tidak'}   |   Mode: {self.chase_mode}   |   Debug: {debug_label}",
            (f"Node dieksplorasi: {res['nodes'] if res else '-'}   "
             f"Panjang jalur: {len(res['path']) if res and res['path'] else '-'}   "
             f"Biaya: {res['cost']:.2f}") if res and res["path"] else "Biaya: -",
            f"Waktu komputasi: {res['time_ms']:.2f} ms" if res else "",
        ]
        for i, txt in enumerate(lines_left):
            surf = self.font_small.render(txt, True, (230, 240, 225))
            self.screen.blit(surf, (10, y0 + 6 + i * 18))

        if self.show_explored:
            legend = "DEBUG: kotak biru = sudah di-expand NPC (angka = urutan)  |  merah = mulai (NPC)  |  hijau = tujuan (pemain)"
            surf = self.font_small.render(legend, True, (150, 200, 235))
            self.screen.blit(surf, (10, y0 + 60))

        help_txt = "1/2 algo  H heuristik  G diagonal  E debug  M mode  SPACE step  N peta baru  R reset  ESC keluar"
        surf2 = self.font_small.render(help_txt, True, (150, 168, 145))
        self.screen.blit(surf2, (10, y0 + 82))

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
        for r in range(ROWS):
            for c in range(COLS):
                self.draw_decor(r, c)
        self.draw_entities()
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
            self.try_move_player(self.player[0] + dr, self.player[1] + dc)
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
            self.show_explored = not self.show_explored
        elif key == pygame.K_m:
            self.chase_mode = "manual" if self.chase_mode == "auto" else "auto"
            self.npc_timer = 0.0
        elif key == pygame.K_SPACE and self.chase_mode == "manual":
            self.npc_step()
        elif key == pygame.K_n:
            self.new_map()
        elif key == pygame.K_r:
            self.respawn()
        elif key == pygame.K_ESCAPE:
            pygame.quit()
            sys.exit(0)

    def handle_click(self, pos):
        x, y = pos
        if y >= ROWS * CELL:
            return
        c, r = x // CELL, y // CELL
        if in_bounds(r, c):
            self.try_move_player(r, c)

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

            if self.chase_mode == "auto":
                self.npc_timer += dt * 1000
                if self.npc_timer >= self.speed_ms:
                    self.npc_timer = 0.0
                    self.npc_step()

            self.draw()


if __name__ == "__main__":
    Game().run()
