"""
Kejar-Kejaran di Desa — NPC Pathfinding (UCS vs A*)
Port dari game.html (canvas/JS) ke Python + Pygame, memakai aset sprite
(TX_Tileset_Grass, TX_Plant, TX_Tileset_Wall, TX_Player, TX_Shadow, dst).

Kontrol:
    - Panah / WASD  : gerakkan pemain
    - Klik kiri     : pindah ke petak yang bisa dilewati
    - 1             : algoritma A*
    - 2             : algoritma UCS
    - H             : ganti heuristik A* (manhattan/euclidean/chebyshev/octile)
    - G             : nyala/mati gerak diagonal (8 arah)
    - E             : tampilkan/sembunyikan node yang dieksplorasi
    - M             : ganti mode kejar NPC (otomatis / manual)
    - SPACE         : langkah manual NPC (saat mode manual)
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
ROWS, COLS, CELL = 16, 22, 32
RIVER_COST = 4
GRASS, TREE, HOUSE, RIVER = 0, 1, 2, 3

SCREEN_W, SCREEN_H = COLS * CELL, ROWS * CELL + 90  # ruang HUD bawah
FPS = 60

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

HEURISTIC_NAMES = ["octile", "manhattan", "euclidean", "chebyshev"]


def load(name, size=None):
    path = os.path.join(ASSET_DIR, name)
    img = pygame.image.load(path).convert_alpha()
    if size:
        img = pygame.transform.smoothscale(img, size)
    return img


class Assets:
    def __init__(self):
        self.grass = [load(f"grass_{c}.png") for c in ("a", "b", "c")]
        self.stone = load("stone_a.png")
        self.wall = load("wall.png")
        self.wall2 = load("wall2.png")
        self.trees = [load(f"tree_{i}.png") for i in range(3)]
        self.tree_shadows = [load(f"tree_shadow_{i}.png") for i in range(3)]
        self.bushes = [load(f"bush_{i}.png") for i in range(6)]
        self.bush_shadows = [load(f"bush_shadow_{i}.png") for i in range(3)]
        self.player_front = load("player_front.png")
        self.player_back = load("player_back.png")
        self.player_side = load("player_side.png")
        self.char_shadow = load("char_shadow.png")

        # versi NPC: sprite pemain yang di-tint merah
        self.npc_front = self._tint(self.player_front, (224, 83, 61))
        self.npc_back = self._tint(self.player_back, (224, 83, 61))
        self.npc_side = self._tint(self.player_side, (224, 83, 61))

    @staticmethod
    def _tint(surface, color):
        img = surface.copy()
        tint = pygame.Surface(img.get_size(), pygame.SRCALPHA)
        tint.fill(color + (0,))
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
    return in_bounds(r, c) and grid[r][c] not in (TREE, HOUSE)


def terrain_cost(grid, r, c):
    return RIVER_COST if grid[r][c] == RIVER else 1


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


def place_houses(g):
    houses = 4
    placed = tries = 0
    while placed < houses and tries < 200:
        tries += 1
        w = 2 + random.choice([0, 1])
        h = 2
        r0 = 2 + random.randint(0, ROWS - h - 4 - 1)
        c0 = 2 + random.randint(0, COLS - w - 4 - 1)
        clear = True
        for r in range(r0 - 1, r0 + h + 1):
            for c in range(c0 - 1, c0 + w + 1):
                if not in_bounds(r, c) or g[r][c] != GRASS:
                    clear = False
                    break
            if not clear:
                break
        if not clear:
            continue
        for r in range(r0, r0 + h):
            for c in range(c0, c0 + w):
                g[r][c] = HOUSE
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


def place_river(g):
    c = 5 + random.randint(0, COLS - 10 - 1)
    drift = 0
    for r in range(ROWS):
        drift += random.choice([-1, 1])
        drift = max(-1, min(1, drift))
        c = max(2, min(COLS - 3, c + drift))
        width = 2 if random.random() < 0.3 else 1
        for w in range(width):
            cc = c + w
            if in_bounds(r, cc) and g[r][cc] != HOUSE:
                g[r][cc] = RIVER


def count_passable(g):
    return sum(1 for r in range(ROWS) for c in range(COLS) if g[r][c] not in (TREE, HOUSE))


def largest_component_size(g):
    seen = [[False] * COLS for _ in range(ROWS)]
    best = 0
    for r0 in range(ROWS):
        for c0 in range(COLS):
            if g[r0][c0] in (TREE, HOUSE) or seen[r0][c0]:
                continue
            size = 0
            stack = [(r0, c0)]
            seen[r0][c0] = True
            while stack:
                cr, cc = stack.pop()
                size += 1
                for dr, dc in ORTH:
                    nr, nc = cr + dr, cc + dc
                    if not in_bounds(nr, nc) or g[nr][nc] in (TREE, HOUSE) or seen[nr][nc]:
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
        place_river(g)
        place_houses(g)
        place_trees(g)
        attempts += 1
        if largest_component_size(g) >= count_passable(g) * 0.85 or attempts >= 20:
            break
    passable = [(r, c) for r in range(ROWS) for c in range(COLS) if g[r][c] not in (TREE, HOUSE)]
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
        self.assets = Assets()

        self.algo = "astar"          # "astar" | "ucs"
        self.heuristic = "octile"
        self.diagonal = True
        self.show_explored = False
        self.chase_mode = "auto"     # "auto" | "manual"
        self.speed_ms = 220
        self.npc_timer = 0.0

        self.toast_text = ""
        self.toast_until = 0.0

        # pra-render tekstur tetap acak per-tile agar rumput bervariasi konsisten
        self.grass_variant = [[random.randint(0, 2) for _ in range(COLS)] for _ in range(ROWS)]
        self.tree_variant = [[random.randint(0, 2) for _ in range(COLS)] for _ in range(ROWS)]
        self.bush_variant = [[random.randint(0, 5) for _ in range(COLS)] for _ in range(ROWS)]

        self.new_map()

    # ---------------- Map lifecycle ----------------
    def new_map(self):
        self.grid, self.passable = generate_map()
        spawn = nearest_passable_cell(self.passable, *FIXED_PLAYER_SPAWN)
        self.player = spawn
        self.npc = farthest_passable_cell(self.passable, self.player)
        self.last_result = None
        self.npc_path = None
        self.recompute_npc_path()

    def respawn(self):
        spawn = nearest_passable_cell(self.passable, *FIXED_PLAYER_SPAWN)
        self.player = spawn
        self.npc = farthest_passable_cell(self.passable, self.player)
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
        if self.npc == self.player:
            self.on_capture()

    def try_move_player(self, r, c):
        if not is_passable(self.grid, r, c):
            return
        self.player = (r, c)
        self.recompute_npc_path()

    # ---------------- Drawing ----------------
    def draw_tile(self, r, c):
        x, y = c * CELL, r * CELL
        t = self.grid[r][c]
        if t == GRASS:
            img = self.assets.grass[self.grass_variant[r][c]]
            self.screen.blit(img, (x, y))
        elif t == RIVER:
            pygame.draw.rect(self.screen, (47, 111, 143), (x, y, CELL, CELL))
            wave = ((r * 7 + c * 3) % 4) - 1
            pygame.draw.line(
                self.screen, (127, 199, 221),
                (x + 3, y + CELL // 2 + wave), (x + CELL - 3, y + CELL // 2 + wave), 2
            )
        elif t == HOUSE:
            img = self.assets.wall if (r + c) % 2 == 0 else self.assets.wall2
            self.screen.blit(img, (x, y))
            top_is_house = in_bounds(r - 1, c) and self.grid[r - 1][c] == HOUSE
            if not top_is_house:
                pygame.draw.polygon(
                    self.screen, (138, 59, 44),
                    [(x, y + 2), (x + CELL // 2, y - 10), (x + CELL, y + 2)]
                )
        elif t == TREE:
            # rumput dasar dulu
            img = self.assets.grass[self.grass_variant[r][c]]
            self.screen.blit(img, (x, y))

    def draw_tree_or_bush(self, r, c):
        """Digambar sesudah tile agar bisa 'menjulang' ke atas petak (pseudo-isometrik)."""
        t = self.grid[r][c]
        x, y = c * CELL, r * CELL
        if t != TREE:
            return
        is_big_tree = (r * 31 + c * 17) % 3 != 0  # sebagian besar jadi pohon besar, sisanya semak
        if is_big_tree:
            idx = self.tree_variant[r][c]
            shadow = self.assets.tree_shadows[idx]
            tree = self.assets.trees[idx]
            sh_rect = shadow.get_rect(midbottom=(x + CELL // 2, y + CELL - 2))
            self.screen.blit(shadow, sh_rect)
            th = int(CELL * 2.6)
            tw = int(th * tree.get_width() / tree.get_height())
            timg = pygame.transform.smoothscale(tree, (tw, th))
            trect = timg.get_rect(midbottom=(x + CELL // 2, y + CELL - 4))
            self.screen.blit(timg, trect)
        else:
            idx = self.bush_variant[r][c]
            shadow = self.assets.bush_shadows[idx % 3]
            bush = self.assets.bushes[idx]
            sh_rect = shadow.get_rect(midbottom=(x + CELL // 2, y + CELL - 2))
            self.screen.blit(shadow, sh_rect)
            bh = int(CELL * 1.3)
            bw = int(bh * bush.get_width() / bush.get_height())
            bimg = pygame.transform.smoothscale(bush, (bw, bh))
            brect = bimg.get_rect(midbottom=(x + CELL // 2, y + CELL - 2))
            self.screen.blit(bimg, brect)

    def draw_explored_overlay(self):
        if not self.show_explored or not self.last_result or not self.last_result["visited"]:
            return
        visited = self.last_result["visited"]
        total = max(1, len(visited))
        overlay = pygame.Surface((CELL - 4, CELL - 4), pygame.SRCALPHA)
        for i, (r, c) in enumerate(visited):
            alpha = int(255 * (0.08 + 0.30 * (i / total)))
            overlay.fill((95, 160, 220, alpha))
            self.screen.blit(overlay, (c * CELL + 2, r * CELL + 2))

    def draw_path_overlay(self):
        if not self.npc_path or len(self.npc_path) < 2:
            return
        total = len(self.npc_path)
        overlay = pygame.Surface((CELL - 14, CELL - 14), pygame.SRCALPHA)
        for i, (r, c) in enumerate(self.npc_path):
            alpha = int(255 * (0.14 + 0.22 * (i / total)))
            overlay.fill((227, 173, 76, alpha))
            self.screen.blit(overlay, (c * CELL + 7, r * CELL + 7))

    def draw_character(self, cell, facing_delta, front_img, back_img, side_img, shadow_img):
        r, c = cell
        x, y = c * CELL + CELL // 2, r * CELL + CELL // 2
        srect = shadow_img.get_rect(center=(x, y + CELL * 0.30))
        self.screen.blit(shadow_img, srect)

        dr, dc = facing_delta
        if dr > 0:
            img = front_img
        elif dr < 0:
            img = back_img
        else:
            img = side_img
        flip = dc < 0
        if flip:
            img = pygame.transform.flip(img, True, False)
        h = int(CELL * 1.35)
        w = int(h * img.get_width() / img.get_height())
        img2 = pygame.transform.smoothscale(img, (w, h))
        rect = img2.get_rect(midbottom=(x, y + CELL * 0.38))
        self.screen.blit(img2, rect)

    def draw_entities(self):
        pr, pc = self.player
        # arah hadap pemain: menuju NPC (agar tetap ada gestur), default menghadap bawah
        facing = (1, 0)
        self.draw_character(
            self.player, facing,
            self.assets.player_front, self.assets.player_back, self.assets.player_side,
            self.assets.char_shadow,
        )

        facing_n = (1, 0)
        if self.npc_path and len(self.npc_path) > 1:
            nr2, nc2 = self.npc_path[1]
            facing_n = (nr2 - self.npc[0], nc2 - self.npc[1])
        self.draw_character(
            self.npc, facing_n,
            self.assets.npc_front, self.assets.npc_back, self.assets.npc_side,
            self.assets.char_shadow,
        )

    def draw_hud(self):
        y0 = ROWS * CELL
        pygame.draw.rect(self.screen, (22, 34, 26), (0, y0, SCREEN_W, SCREEN_H - y0))
        pygame.draw.line(self.screen, (44, 61, 47), (0, y0), (SCREEN_W, y0), 2)

        res = self.last_result
        algo_label = "UCS" if self.algo == "ucs" else f"A* ({self.heuristic})"
        lines_left = [
            f"Algoritma: {algo_label}   |   Diagonal: {'ya' if self.diagonal else 'tidak'}   |   Mode: {self.chase_mode}",
            f"Node dieksplorasi: {res['nodes'] if res else '-'}   "
            f"Panjang jalur: {len(res['path']) if res and res['path'] else '-'}   "
            f"Biaya: {res['cost']:.2f}" if res and res["path"] else "Biaya: -",
            f"Waktu komputasi: {res['time_ms']:.2f} ms" if res else "",
        ]
        for i, txt in enumerate(lines_left):
            surf = self.font_small.render(txt, True, (230, 240, 225))
            self.screen.blit(surf, (10, y0 + 6 + i * 18))

        help_txt = "1/2 algo  H heuristik  G diagonal  E explored  M mode  SPACE step  N peta baru  R reset  ESC keluar"
        surf = self.font_small.render(help_txt, True, (150, 168, 145))
        self.screen.blit(surf, (10, y0 + 64))

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
        self.draw_explored_overlay()
        self.draw_path_overlay()
        for r in range(ROWS):
            for c in range(COLS):
                self.draw_tree_or_bush(r, c)
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