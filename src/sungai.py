# -*- coding: utf-8 -*-
"""
sungai.py — SUNGAI DINAMIS + integrasi multi-modul AI (tanpa pygame).

    §1  Matriks biaya tile  (Modul 03 & 09)   : ROCK / TIDE / DEEP / WOOD + carve_river()
    §2  Knowledge Base FOL/CNF (Modul 07)      : RiverKB — klausa Horn (bentuk CNF), TELL & ASK
    §3  Perencanaan otomatis PDDL (Modul 08)   : PDDL_DOMAIN + planner STRIPS (A* atas state PDDL)
    §4  Keputusan di bawah ketidakpastian (Modul 09): RiverMDP — MDP + MEU (value iteration)

CATATAN ASUMSI (spesifikasi sumber terpotong di bagian 4 "MDP_Tuple:"):
    tuple MDP (S, A, T, R, gamma) di §4 DIDEFINISIKAN di sini oleh implementasi:
    S=(sel, pasang) dgn pasang in {rendah, tinggi}; A=gerak ke tetangga; T=gerak deterministik &
    pasang berantai Markov (TIDE_P_UP / TIDE_P_DOWN); R=-biaya sel tujuan (pada pasang tujuan)
    + hadiah tujuan; gamma=0.97. Ubah konstanta di bawah kalau definisi aslinya berbeda.
"""
import heapq
import math
import random
from dataclasses import dataclass

# ===========================================================================
# §1. TILE & MATRIKS BIAYA
# ===========================================================================
GRASS, TREE, PROP, BUSH = 0, 1, 2, 3          # sama dgn game.py
ROCK, TIDE, DEEP, WOOD = 4, 5, 6, 7           # tile sungai (Wood_Sunk = fluent KB, bukan tipe grid)
RIVER_TILES = (ROCK, TIDE, DEEP, WOOD)
TILE_NAMES = {ROCK: "Rock_Fixed", TIDE: "HighTide_Area", DEEP: "DeepRiver_Fixed",
                WOOD: "Wood_Floating"}

COST_GROUND = 1
COST_ROCK = 1                 # jembatan permanen, stabil
COST_TIDE_HIGH, COST_TIDE_LOW = 3, 1
COST_DEEP = 5                 # penalti tinggi
COST_WOOD_FLOATING = 1        # langkah pertama
COST_WOOD_SUNK = 5            # kayu yang sudah diinjak = air dalam
WOOD_RESPAWN_TURNS = COST_WOOD_SUNK   # kayu tenggelam SELAMA sebanyak biayanya (turn), lalu mengapung lagi
UNSAFE_COST = 5               # langkah dengan biaya >= ini dianggap TIDAK AMAN


def turns_for_cost(cost):
    """SISTEM TURN: masuk ke tile berbiaya `cost` memakan sebanyak `cost` turn (minimal 1)."""
    return max(1, int(round(cost)))

# Pasang: rantai Markov 2-keadaan, bergerak 1 langkah tiap tick waktu permainan.
TIDE_P_UP = 0.20              # P(rendah -> tinggi)
TIDE_P_DOWN = 0.30            # P(tinggi -> rendah)   => P(tinggi) jangka panjang = 0.4

# --- bentuk sungai organik (lihat carve_river) ---
RIVER_AMPLITUDE = (1.6, 2.6)
RIVER_CORE_HALF = (0.95, 1.9)
RIVER_SHORE = (0.7, 1.5)
RIVER_JITTER = 0.30


def _smooth_noise(y, phases, periods):
    """Derau halus 1-D (jumlah sinus berfrekuensi beda) dalam rentang kira-kira [-1, 1]."""
    return sum(math.sin(2 * math.pi * y / p + ph) for ph, p in zip(phases, periods)) / len(periods)


def carve_river(g, rng=random):
    """Gambar sungai vertikal ORGANIK di tengah peta (menimpa pohon/properti/semak di jalurnya).
        - garis tengah BERKELOK (sinus + derau halus), lebar inti & tepi berubah sepanjang aliran
        - tepi kasar: jarak ke garis tengah diberi derau -> tidak ada tepi lurus berbentuk kotak
        - inti = DEEP, cincin luar = TIDE (pantai pasang), sisanya daratan
        - JEMBATAN BATU = jalur batu loncatan berliku dari tepi ke tepi di dekat ujung atas/bawah peta
        - KAYU APUNG = seluruh inti air dalam pada 2 baris dekat jalur lurus pemain-musuh
    Tile sungai TETAP bisa dilewati (hanya mahal), jadi peta tidak pernah terputus.
    Return dict info layout."""
    rows, cols = len(g), len(g[0])
    two_pi = 2 * math.pi
    period = rng.uniform(rows * 0.85, rows * 1.5)
    amp = rng.uniform(*RIVER_AMPLITUDE)
    ph1, ph2, ph3, ph4, ph5 = (rng.uniform(0, two_pi) for _ in range(5))
    base = cols / 2.0 + rng.uniform(-0.7, 0.7)
    samples = []
    for i in range((rows - 1) * 4 + 1):
        y = i / 4
        x = base + amp * math.sin(two_pi * y / period + ph1) + 0.4 * math.sin(two_pi * y / (period * 0.43) + ph2)
        core = RIVER_CORE_HALF[0] + (RIVER_CORE_HALF[1] - RIVER_CORE_HALF[0]) * (0.5 + 0.5 * math.sin(two_pi * y / (rows * 0.6) + ph3))
        shore = RIVER_SHORE[0] + (RIVER_SHORE[1] - RIVER_SHORE[0]) * (0.5 + 0.5 * math.sin(two_pi * y / (rows * 0.45) + ph4))
        samples.append((y, min(max(x, 9.0), cols - 10.0), core, shore))

    kind = [[GRASS] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            best = min(samples, key=lambda p: (p[0] - r) ** 2 + (p[1] - c) ** 2)
            d = math.hypot(best[0] - r, best[1] - c) + RIVER_JITTER * math.sin(1.9 * r + 2.3 * c + ph5) * math.cos(0.7 * r - 1.3 * c)
            if d <= best[2]:
                kind[r][c] = DEEP
            elif d <= best[2] + best[3]:
                kind[r][c] = TIDE

    wood_rows = [rows // 2, rows // 2 - 4]
    for r in wood_rows:
        deep = [c for c in range(cols) if kind[r][c] == DEEP]
        if deep:
            for c in range(min(deep), max(deep) + 1):
                kind[r][c] = WOOD

    rock_row = rng.choice([r for r in (1, 2, rows - 3, rows - 2) if r not in wood_rows])
    river_cells = [(r, c) for r in range(rows) for c in range(cols)
                    if kind[r][c] in (DEEP, TIDE)]
    row_cells = [c for r, c in river_cells if r == rock_row]
    rock_path = []
    if row_cells:
        left_c, right_c = min(row_cells), max(row_cells)
        cur = (rock_row, left_c)
        rock_path.append(cur)
        while cur[1] < right_c:
            next_c = cur[1] + 1
            options = [(rr, next_c) for rr in (rock_row - 1, rock_row, rock_row + 1)
                        if 0 <= rr < rows and kind[rr][next_c] in (DEEP, TIDE)]
            if not options:
                options = [(rr, next_c) for rr in range(rows)
                            if kind[rr][next_c] in (DEEP, TIDE)]
            if not options:
                break
            cur = rng.choice(options) if rng.random() < 0.3 else min(options, key=lambda p: abs(p[0] - rock_row))
            rock_path.append(cur)
    for r, c in rock_path:
        kind[r][c] = ROCK
    if rock_path:
        left_c = rock_path[0][1]
        right_c = rock_path[-1][1]
        left_r = rock_path[0][0]
        right_r = rock_path[-1][0]
        for rr in range(max(0, left_r - 1), min(rows, left_r + 2)):
            if left_c > 0:
                kind[rr][left_c - 1] = GRASS
        for rr in range(max(0, right_r - 1), min(rows, right_r + 2)):
            if right_c + 1 < cols:
                kind[rr][right_c + 1] = GRASS

    for r in range(rows):
        for c in range(cols):
            if kind[r][c] != GRASS:
                g[r][c] = kind[r][c]
    return {"rock_row": rock_row, "wood_rows": wood_rows, "rock_path": rock_path,
            "centers": [(p[0], p[1]) for p in samples]}


def build_style(grid):
    """Info gambar per tile sungai: kedalaman dan sisi yang berbatasan dengan daratan."""
    rows, cols = len(grid), len(grid[0])
    is_river = lambda r, c: 0 <= r < rows and 0 <= c < cols and grid[r][c] in RIVER_TILES
    style, dist, queue = {}, {}, []
    for r in range(rows):
        for c in range(cols):
            if is_river(r, c) and any(not is_river(r + dr, c + dc)
                                        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))):
                dist[(r, c)] = 0
                queue.append((r, c))
    queue_index = 0
    while queue_index < len(queue):
        r, c = queue[queue_index]
        queue_index += 1
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            n = (r + dr, c + dc)
            if is_river(*n) and n not in dist:
                dist[n] = dist[(r, c)] + 1
                queue.append(n)
    for (r, c), d in dist.items():
        style[(r, c)] = {"depth": min(d, 3),
                        "land": (not is_river(r - 1, c), not is_river(r + 1, c),
                                    not is_river(r, c - 1), not is_river(r, c + 1))}
    return style


def static_cost(tile, high_tide=False):
    """Biaya dasar tile (tanpa KB) — fallback & dasar tes."""
    if tile == ROCK:
        return COST_ROCK
    if tile == TIDE:
        return COST_TIDE_HIGH if high_tide else COST_TIDE_LOW
    if tile == DEEP:
        return COST_DEEP
    if tile == WOOD:
        return COST_WOOD_FLOATING
    return COST_GROUND


# ===========================================================================
# §2. KNOWLEDGE BASE — FOL / CNF (klausa Horn)  +  TELL / ASK
# ===========================================================================
# Atom = tuple ("Pred", arg, ...). Variabel = string berawalan "?". Waktu t = int.
# Term aritmetika waktu: ("+", "?t", 1). Literal negatif (NAF): ("not", atom).
#
#   Predikat statis : IsRock(x,y)  IsDeepRiver(x,y)  TidalArea(x,y)  Walkable(x,y)
#   Fluent          : HighTide(t)  IsWoodFloating(x,y,t)  IsWoodSunk(x,y,t)  SteppedOn(x,y,t)
#   Turunan         : TileCost(x,y,t,c)  Unsafe(x,y,t)
@dataclass(frozen=True)
class Clause:
    name: str
    head: tuple
    body: tuple                      # literal positif atau ("not", atom)
    note: str = ""

    def to_cnf(self):
        """Klausa Horn = CNF: body positif jadi literal NEGATIF, head positif."""
        def fmt(a):
            return "%s(%s)" % (a[0], ",".join(_fmt_term(x) for x in a[1:]))
        lits = []
        for b in self.body:
            lits.append(fmt(b[1]) if b[0] == "not" else "¬" + fmt(b))   # not A  =>  A di CNF
        lits.append(fmt(self.head))
        return " ∨ ".join(lits)

    def to_fol(self):
        def fmt(a):
            return "%s(%s)" % (a[0], ",".join(_fmt_term(x) for x in a[1:]))
        body = " ∧ ".join(("¬" + fmt(b[1])) if b[0] == "not" else fmt(b) for b in self.body)
        return "%s ⇒ %s" % (body, fmt(self.head))


def _fmt_term(x):
    if isinstance(x, tuple):
        return "%s%s%d" % (x[1].lstrip("?"), "+" if x[2] >= 0 else "−", abs(x[2]))
    return str(x).lstrip("?")


KB_RULES = (
    # ---- aturan spesifikasi ----
    Clause("R1", ("TileCost", "?x", "?y", "?t", 3),
            (("HighTide", "?t"), ("TidalArea", "?x", "?y")),
            "HighTide(t) ∧ TidalArea(x,y) ⇒ TileCost(x,y,t)=3"),
    Clause("R2", ("IsWoodSunk", "?x", "?y", ("+", "?t", 1)),
            (("SteppedOn", "?x", "?y", "?t"), ("IsWoodFloating", "?x", "?y", "?t")),
            "SteppedOn ∧ IsWoodFloating ⇒ IsWoodSunk(t+1)"),
    Clause("R3", ("TileCost", "?x", "?y", "?t", 5),
            (("IsWoodSunk", "?x", "?y", "?t"),),
            "IsWoodSunk(t) ⇒ TileCost=5  (berlaku utk t+1 dari injakan)"),
    # ---- aksioma bingkai (frame axioms) agar fluent bertahan antar waktu ----
    Clause("R4", ("IsWoodSunk", "?x", "?y", ("+", "?t", 1)),
            (("IsWoodSunk", "?x", "?y", "?t"), ("not", ("Emerge", "?x", "?y", "?t"))),
            "kayu tenggelam tetap tenggelam sampai muncul lagi"),
    Clause("R5", ("IsWoodFloating", "?x", "?y", ("+", "?t", 1)),
            (("IsWoodFloating", "?x", "?y", "?t"), ("not", ("SteppedOn", "?x", "?y", "?t"))),
            "kayu mengapung tetap mengapung bila tidak diinjak"),
    # ---- biaya dasar & tile statis ----
    Clause("R6", ("TileCost", "?x", "?y", "?t", 5),
            (("IsDeepRiver", "?x", "?y"),), "sungai dalam selalu 5"),
    Clause("R7", ("TileCost", "?x", "?y", "?t", 1),
            (("Walkable", "?x", "?y"),), "biaya dasar 1 (batu, tanah, kayu apung, pasang rendah)"),
    Clause("R8", ("Unsafe", "?x", "?y", "?t"),
            (("TileCost", "?x", "?y", "?t", 5),), "biaya 5 = langkah TIDAK aman"),
    # ---- kayu MUNCUL LAGI setelah tenggelam selama WOOD_RESPAWN_TURNS (= biaya kayu tenggelam) ----
    Clause("R9", ("SunkSince", "?x", "?y", ("+", "?t", 1)),
            (("SteppedOn", "?x", "?y", "?t"), ("IsWoodFloating", "?x", "?y", "?t")),
            "catat kapan kayu mulai tenggelam"),
    Clause("R10", ("Emerge", "?x", "?y", "?t"),
            (("IsWoodSunk", "?x", "?y", "?t"), ("SunkSince", "?x", "?y", ("+", "?t", -(WOOD_RESPAWN_TURNS - 1)))),
            "tenggelam sebanyak biayanya (turn) => muncul"),
    Clause("R11", ("IsWoodFloating", "?x", "?y", ("+", "?t", 1)),
            (("Emerge", "?x", "?y", "?t"),), "kayu mengapung lagi di turn berikutnya"),
)
_TEMPORAL = ("HighTide", "IsWoodFloating", "IsWoodSunk", "SteppedOn", "SunkSince", "Emerge")
_FORWARD_FIRST = ("R10",)            # fakta waktu-t (Emerge) harus ada dulu sebelum aturan t -> t+1
_FORWARD = ("R2", "R9", "R4", "R5", "R11")        # aturan temporal dijalankan forward-chaining saat TELL
_BACKWARD = ("R1", "R3", "R6", "R7", "R8")


def _is_var(x):
    return isinstance(x, str) and x.startswith("?")


def _eval(term, b):
    if isinstance(term, tuple):                       # ("+", "?t", 1)
        base = _eval(term[1], b)
        return base + term[2] if isinstance(base, int) else term
    return b.get(term, term) if _is_var(term) else term


def _unify(pattern, fact, b):
    if len(pattern) != len(fact) or pattern[0] != fact[0]:
        return None
    b = dict(b)
    for p, f in zip(pattern[1:], fact[1:]):
        if isinstance(p, tuple):
            if _eval(p, b) != f:
                return None
        elif _is_var(p):
            if p in b:
                if b[p] != f:
                    return None
            else:
                b[p] = f
        elif p != f:
            return None
    return b


class RiverKB:
    """KB ground + mesin inferensi. TELL meng-update fluent (forward chaining); ASK menjawab
    kueri biaya/keamanan (backward chaining / resolusi SLD atas klausa Horn)."""

    def __init__(self):
        self.facts = {}                 # predikat -> set(tuple)
        self.t = 0
        self.version = 0                # naik tiap ada perubahan yg MEMENGARUHI biaya
        self.wood = set()               # sel kayu yang dikenal KB
        self._hyp_tide = None           # pasang hipotetis utk kueri MDP (None = pakai fakta)
        self.rules = {c.name: c for c in KB_RULES}
        self.tell_log = []
        self._tindex = {}               # (predikat temporal, t) -> fakta; agar forward chaining tidak O(t^2)

    # ---------------- fakta ----------------
    def _add(self, atom):
        s = self.facts.setdefault(atom[0], set())
        if atom in s:
            return False
        s.add(atom)
        if atom[0] in _TEMPORAL:
            self._tindex.setdefault((atom[0], atom[-1]), set()).add(atom)
        return True

    def has(self, atom):
        return atom in self.facts.get(atom[0], ())

    def load_static(self, grid):
        """Fakta statis dari layout peta (dipanggil sekali per peta)."""
        for r, row in enumerate(grid):
            for c, tile in enumerate(row):
                if tile in (TREE, PROP):
                    continue
                self._add(("Walkable", r, c))
                if tile == ROCK:
                    self._add(("IsRock", r, c))
                elif tile == DEEP:
                    self._add(("IsDeepRiver", r, c))
                elif tile == TIDE:
                    self._add(("TidalArea", r, c))
                elif tile == WOOD:
                    self.wood.add((r, c))
                    self._add(("IsWoodFloating", r, c, 0))

    # ---------------- TELL ----------------
    def tell(self, event):
        """TELL(KB, Event) — event: ("tide", t, high:bool) | ("step", x, y, t).
        Update fluent pada langkah t dan forward-chain ke t+1. Return True kalau biaya berubah."""
        changed = False
        kind = event[0]
        if kind == "tide":
            _, t, high = event
            prev = self.has(("HighTide", t - 1)) if t > 0 else False
            if high:
                self._add(("HighTide", t))
            changed = (high != prev)
        elif kind == "step":
            _, x, y, t = event
            if (x, y) in self.wood:
                self._add(("SteppedOn", x, y, t))
                changed = self.has(("IsWoodFloating", x, y, t))     # akan tenggelam di t+1
        else:
            raise ValueError("event tidak dikenal: %r" % (event,))
        self.tell_log.append(event)
        if changed:
            self.version += 1
        return changed

    def advance(self, t):
        """Forward chaining aturan temporal R2/R4/R5 dari waktu t ke t+1 (untuk semua kayu)."""
        for name in _FORWARD_FIRST:                       # fase 1: Emerge(x,y,t) dari fluent waktu t
            rule = self.rules[name]
            for b in list(self._match_body(rule.body, {"?t": t})):
                self._add(tuple(rule.head[:1]) + tuple(_eval(a, b) for a in rule.head[1:]))
        derived = []                                      # fase 2: fluent waktu t+1
        for name in _FORWARD:
            rule = self.rules[name]
            for b in self._match_body(rule.body, {"?t": t}):
                derived.append(tuple(rule.head[:1]) + tuple(_eval(a, b) for a in rule.head[1:]))
        for atom in derived:
            self._add(atom)
        self.t = t + 1

    def _match_body(self, body, b, idx=0):
        """Semua binding yang memenuhi `body` terhadap fakta (positif dulu, lalu NAF)."""
        pos = [l for l in body if l[0] != "not"]
        neg = [l for l in body if l[0] == "not"]

        def rec(i, bb):
            if i == len(pos):
                for n in neg:
                    atom = tuple(_eval(a, bb) for a in n[1][1:])
                    if self.has((n[1][0],) + atom):
                        return
                yield bb
                return
            lit = pos[i]
            pool = self.facts.get(lit[0], ())
            if lit[0] in _TEMPORAL:                       # waktu sudah terikat -> ambil dari indeks waktu
                tv = _eval(lit[-1], bb)
                if isinstance(tv, int):
                    pool = self._tindex.get((lit[0], tv), ())
            for fact in list(pool):
                nb = _unify(lit, fact, bb)
                if nb is not None:
                    yield from rec(i + 1, nb)
        yield from rec(0, b)

    # ---------------- ASK (backward chaining) ----------------
    def _holds(self, atom):
        """Apakah atom ground terbukti? (fakta, atau klausa backward yg kepalanya cocok)."""
        if atom[0] == "HighTide" and self._hyp_tide is not None:
            return bool(self._hyp_tide)
        if self.has(atom):
            return True
        for name in _BACKWARD:
            rule = self.rules[name]
            if rule.head[0] != atom[0] or len(rule.head) != len(atom):
                continue
            b = _unify(rule.head, atom, {})
            if b is None:
                continue
            if self._prove_body(rule.body, b):
                return True
        return False

    def _prove_body(self, body, b):
        for lit in body:
            if lit[0] == "not":
                ground = (lit[1][0],) + tuple(_eval(a, b) for a in lit[1][1:])
                if self._holds(ground):
                    return False
            else:
                ground = (lit[0],) + tuple(_eval(a, b) for a in lit[1:])
                if not self._holds(ground):
                    return False
        return True

    def ask_cost(self, x, y, t=None, assume_high=None):
        """ASK(KB, TileCost(x,y,t,?c)) -> biaya terbesar yang terbukti (1, 3, atau 5)."""
        t = self.t if t is None else t
        old = self._hyp_tide
        self._hyp_tide = assume_high
        try:
            best = None
            for c in (5, 3, 1):
                if self._holds(("TileCost", x, y, t, c)):
                    best = c
                    break
            return best if best is not None else COST_GROUND
        finally:
            self._hyp_tide = old

    def ask_safe(self, x, y, t=None):
        """ASK(KB, ¬Unsafe(x,y,t)) — evaluasi keamanan langkah sebelum A* meng-expand."""
        t = self.t if t is None else t
        return not self._holds(("Unsafe", x, y, t))

    def ask(self, x, y, t=None):
        """(aman?, biaya) — antarmuka Agent_Interface.ASK untuk A*."""
        return self.ask_safe(x, y, t), self.ask_cost(x, y, t)

    def high_tide(self, t=None):
        t = self.t if t is None else t
        return self.has(("HighTide", t))

    def wood_state(self, x, y, t=None):
        t = self.t if t is None else t
        if self.has(("IsWoodSunk", x, y, t)):
            return "sunk"
        if self.has(("IsWoodFloating", x, y, t)):
            return "floating"
        return None

    def sunk_remaining(self, x, y, t=None):
        """Sisa turn sebelum kayu (x,y) yang tenggelam mengapung lagi; None kalau tidak tenggelam."""
        t = self.t if t is None else t
        if not self.has(("IsWoodSunk", x, y, t)):
            return None
        for (_, sx, sy, s) in self.facts.get("SunkSince", ()):
            if (sx, sy) == (x, y) and s <= t <= s + WOOD_RESPAWN_TURNS - 1:
                return s + WOOD_RESPAWN_TURNS - t
        return None

    def rules_text(self, mode="cnf"):
        return [("%s  %s" % (c.name, c.to_cnf() if mode == "cnf" else c.to_fol())) for c in KB_RULES]


# ===========================================================================
# WORLD — pembungkus KB + waktu + pasang stokastik (dipakai game.py)
# ===========================================================================
class RiverWorld:
    def __init__(self, grid, seed=None, p_up=TIDE_P_UP, p_down=TIDE_P_DOWN):
        self.grid = grid
        self.rng = random.Random(seed)
        self.p_up, self.p_down = p_up, p_down
        self.kb = RiverKB()
        self.kb.load_static(grid)
        self.t = 0
        self.kb.tell(("tide", 0, False))     # mulai dari pasang rendah
        self._cache = {}
        self._cache_ver = -1
        self._actions = {}
        self.has_river = any(t in RIVER_TILES for row in grid for t in row)
        self.style = build_style(grid)

    @property
    def version(self):
        return self.kb.version

    @property
    def high(self):
        return self.kb.high_tide(self.t)

    # --- biaya (dipakai A* lewat terminal_cost di game.py) ---
    def cost(self, r, c):
        if self._cache_ver != self.kb.version:
            self._cache.clear()
            self._cache_ver = self.kb.version
        key = (r, c)
        v = self._cache.get(key)
        if v is None:
            v = self._cache[key] = self.kb.ask_cost(r, c, self.t)
        return v

    def cost_hyp(self, r, c, high):
        """Biaya sel jika pasang = high (untuk MDP); fluent kayu tetap sesuai KB sekarang."""
        return self.kb.ask_cost(r, c, self.t, assume_high=bool(high))

    def safe(self, r, c):
        return self.kb.ask_safe(r, c, self.t)

    # --- dinamika ---
    def step_on(self, r, c):
        """Seorang agen menginjak (r,c) pada waktu t. Return True kalau kayu akan tenggelam."""
        return self.kb.tell(("step", r, c, self.t))

    def advance(self):
        """Maju 1 tick waktu: sampel pasang, TELL, forward-chain fluent. Return True bila ada
        perubahan biaya (pasang berganti / kayu tenggelam) -> pemicu REPLANNING."""
        v0 = self.kb.version
        t0 = self.t
        self.kb.advance(t0)                       # R2/R4/R5: t0 -> t0+1
        self.t = t0 + 1
        was_high = self.kb.has(("HighTide", t0))
        p = self.p_down if was_high else self.p_up
        high_now = (not was_high) if self.rng.random() < p else was_high
        self.kb.tell(("tide", self.t, high_now))
        # kayu yang baru tenggelam ATAU baru muncul lagi di t+1 mengubah biaya
        if any(self.kb.has(("IsWoodSunk", x, y, self.t)) != self.kb.has(("IsWoodSunk", x, y, t0))
                for (x, y) in self.kb.wood):
            self.kb.version += 1
        return self.kb.version != v0

    def wood_counts(self):
        fl = sum(1 for (x, y) in self.kb.wood if self.kb.wood_state(x, y, self.t) == "floating")
        sk = sum(1 for (x, y) in self.kb.wood if self.kb.wood_state(x, y, self.t) == "sunk")
        return fl, sk

    def sunk_signature(self):
        return tuple(sorted((x, y) for (x, y) in self.kb.wood if self.kb.wood_state(x, y, self.t) == "sunk"))


# ===========================================================================
# §3. PERENCANAAN OTOMATIS — PDDL (STRIPS)
# ===========================================================================
PDDL_DOMAIN = """(define (domain sungai)
    (:requirements :strips :typing)
    (:types agent loc)
    (:predicates (at ?ag - agent ?loc - loc) (adj ?a - loc ?b - loc)
                (wood-at ?loc - loc) (wood-floating ?loc - loc) (wood-sunk ?loc - loc))
    (:action STEP_ON_WOOD
    :parameters (?ag - agent ?from - loc ?to - loc)
    :precondition (and (at ?ag ?from) (wood-at ?to) (wood-floating ?to) (adj ?from ?to))
    :effect (and (at ?ag ?to) (not (at ?ag ?from)) (not (wood-floating ?to)) (wood-sunk ?to)))
    ;; tambahan agar rencana lengkap (spesifikasi hanya mendefinisikan STEP_ON_WOOD):
    (:action MOVE
    :parameters (?ag - agent ?from - loc ?to - loc)
    :precondition (and (at ?ag ?from) (adj ?from ?to))
    :effect (and (at ?ag ?to) (not (at ?ag ?from))))
)"""


@dataclass(frozen=True)
class Action:
    name: str
    params: tuple
    pre: frozenset
    add: frozenset
    delete: frozenset
    cost: float
    frm: tuple = None
    to: tuple = None


def _loc(rc):
    return "c%d_%d" % rc


def ground_actions(world, neighbors, diagonal_cost=math.sqrt(2)):
    """Ground semua aksi: STEP_ON_WOOD (kayu mengapung) & MOVE (selain itu, termasuk kayu
    yang sudah tenggelam = air dalam, biaya 5). `neighbors(r,c)` -> daftar sel tetangga."""
    grid = world.grid
    by_from = {}
    wood_cells = world.kb.wood
    for r in range(len(grid)):
        for c in range(len(grid[0])):
            for (nr, nc) in neighbors(r, c):
                df = diagonal_cost if (nr != r and nc != c) else 1.0
                frm, to = (r, c), (nr, nc)
                if to in wood_cells:
                    # kayu: bisa diinjak (STEP_ON_WOOD, mengapung) atau dilalui sbg air dalam (MOVE)
                    a = Action("STEP_ON_WOOD", ("ag", _loc(frm), _loc(to)),
                                frozenset({("at", "ag", frm), ("wood-floating", to)}),
                                frozenset({("at", "ag", to), ("wood-sunk", to)}),
                                frozenset({("at", "ag", frm), ("wood-floating", to)}),
                                COST_WOOD_FLOATING * df, frm, to)
                    by_from.setdefault(frm, []).append(a)
                    a2 = Action("MOVE", ("ag", _loc(frm), _loc(to)),
                                frozenset({("at", "ag", frm), ("wood-sunk", to)}),
                                frozenset({("at", "ag", to)}), frozenset({("at", "ag", frm)}),
                                COST_WOOD_SUNK * df, frm, to)
                    by_from.setdefault(frm, []).append(a2)
                else:
                    a = Action("MOVE", ("ag", _loc(frm), _loc(to)),
                                frozenset({("at", "ag", frm)}), frozenset({("at", "ag", to)}),
                                frozenset({("at", "ag", frm)}), None, frm, to)
                    by_from.setdefault(frm, []).append((a, to, df))
    return by_from


def plan_pddl(world, neighbors, start, goal, base_cost, heuristic=None, max_nodes=30000, cache_key=None):
    """A* atas ruang state STRIPS. State = frozenset atom {(at ag loc), (wood-floating w),
    (wood-sunk w)}; aksi diterapkan lewat pre/add/delete. `base_cost(r,c)` = biaya sel NON-kayu
    (dari KB/ASK pada waktu sekarang). Return dict: plan (daftar aksi), path, cost, nodes."""
    h = heuristic or (lambda a, b: max(abs(a[0] - b[0]), abs(a[1] - b[1])))
    wood = world.kb.wood
    t = world.t
    init = {("at", "ag", start)}
    for w in wood:
        st = world.kb.wood_state(w[0], w[1], t)
        init.add(("wood-sunk" if st == "sunk" else "wood-floating", w))
    init = frozenset(init)
    if cache_key is not None and cache_key in world._actions:
        actions = world._actions[cache_key]
    else:
        actions = ground_actions(world, neighbors)
        if cache_key is not None:
            world._actions[cache_key] = actions
    goal_atom = ("at", "ag", goal)
    open_, tie = [(h(start, goal), 0.0, 0, init, None, None)], 0
    best = {init: 0.0}
    parents = {}
    nodes = 0
    while open_:
        f, g, _, state, _p, _a = heapq.heappop(open_)
        if g > best.get(state, math.inf) + 1e-9:
            continue
        nodes += 1
        if goal_atom in state:
            seq, cur = [], state
            while cur in parents:
                cur, act = parents[cur]
                seq.append(act)
            seq.reverse()
            path = [start] + [a.to for a in seq]
            return {"plan": seq, "path": path, "cost": g, "nodes": nodes, "ok": True}
        if nodes > max_nodes:
            break
        loc = next(a[2] for a in state if a[0] == "at")
        for item in actions.get(loc, ()):
            if isinstance(item, tuple):                           # MOVE non-kayu
                act, to, df = item
                cost = base_cost(to[0], to[1]) * df
            else:
                act, cost = item, item.cost
            if not act.pre <= state:
                continue
            ns = frozenset((state - act.delete) | act.add)
            ng = g + cost
            if ng + 1e-9 < best.get(ns, math.inf):
                best[ns] = ng
                parents[ns] = (state, act)
                tie += 1
                heapq.heappush(open_, (ng + h(act.to, goal), ng, tie, ns, None, None))
    return {"plan": [], "path": [start], "cost": math.inf, "nodes": nodes, "ok": False}


def _parse(loc_name):
    r, c = loc_name[1:].split("_")
    return int(r), int(c)


def to_pddl_problem(world, start, goal):
    objs = " ".join(sorted({_loc(w) for w in world.kb.wood} | {_loc(start), _loc(goal)}))
    init = ["(at ag %s)" % _loc(start)]
    for w in sorted(world.kb.wood):
        init.append("(wood-at %s)" % _loc(w))
        init.append("(wood-%s %s)" % ("sunk" if world.kb.wood_state(w[0], w[1], world.t) == "sunk" else "floating", _loc(w)))
    return "(define (problem p) (:domain sungai)\n  (:objects ag - agent %s - loc)\n  (:init %s)\n  (:goal (at ag %s)))" % (
        objs, " ".join(init), _loc(goal))


# ===========================================================================
# §4. MDP + MEU  (asumsi tuple — lihat catatan di atas modul)
# ===========================================================================
class RiverMDP:
    """MDP: S=(sel, pasang), A=gerak ke tetangga, T=gerak deterministik & pasang Markov,
    R=-biaya(sel tujuan | pasang tujuan) (×√2 diagonal), hadiah tujuan G, diskon gamma.
    Kebijakan MEU: pilih aksi dgn utilitas-harapan tertinggi.  Solusi: value iteration."""

    def __init__(self, cells, neighbors, cost_fn, goal, p_up=TIDE_P_UP, p_down=TIDE_P_DOWN,
                gamma=0.97, goal_reward=60.0):
        self.cells = list(cells)
        self.idx = {c: i for i, c in enumerate(self.cells)}
        self.goal = goal
        self.gamma = gamma
        self.G = goal_reward
        self.p = {False: {False: 1 - p_up, True: p_up}, True: {False: p_down, True: 1 - p_down}}
        n = len(self.cells)
        self.nbr = []
        for (r, c) in self.cells:
            lst = []
            for (nr, nc) in neighbors(r, c):
                if (nr, nc) in self.idx:
                    lst.append((self.idx[(nr, nc)], math.sqrt(2) if (nr != r and nc != c) else 1.0))
            self.nbr.append(lst)
        # biaya-harapan langkah ke sel j dari pasang saat ini tau: E_tau[j] = sum_tau' P(tau'|tau) cost(j|tau')
        cl = [cost_fn(r, c, False) for (r, c) in self.cells]
        ch = [cost_fn(r, c, True) for (r, c) in self.cells]
        self.cost = {False: cl, True: ch}
        self.E = {tau: [self.p[tau][False] * cl[j] + self.p[tau][True] * ch[j] for j in range(n)]
                    for tau in (False, True)}
        self.V = {False: [0.0] * n, True: [0.0] * n}
        self.iterations = 0

    def solve(self, tol=0.02, max_iter=300):
        gi = self.idx[self.goal]
        V = self.V
        n = len(self.cells)
        for tau in (False, True):
            V[tau][gi] = self.G
        gamma, p, E, nbr = self.gamma, self.p, self.E, self.nbr
        for it in range(1, max_iter + 1):
            delta = 0.0
            # U_tau[j] = gamma * sum_tau' P(tau'|tau) V_tau'[j]
            U = {tau: [gamma * (p[tau][False] * V[False][j] + p[tau][True] * V[True][j]) for j in range(n)]
                for tau in (False, True)}
            for tau in (False, True):
                Vt, Et, Ut = V[tau], E[tau], U[tau]
                for i in range(n):
                    if i == gi:
                        continue
                    best = -1e18
                    for (j, f) in nbr[i]:
                        q = -f * Et[j] + Ut[j]
                        if q > best:
                            best = q
                    if best == -1e18:
                        continue
                    d = abs(best - Vt[i])
                    if d > delta:
                        delta = d
                    Vt[i] = best
            self.iterations = it
            if delta < tol:
                break
        return self

    def q_values(self, cell, high):
        i = self.idx[cell]
        p, gamma = self.p[bool(high)], self.gamma
        out = []
        for (j, f) in self.nbr[i]:
            q = -f * self.E[bool(high)][j] + gamma * (p[False] * self.V[False][j] + p[True] * self.V[True][j])
            out.append((q, self.cells[j]))
        return out

    def best_action(self, cell, high):
        """MEU: sel tujuan dgn utilitas-harapan terbesar dari (cell, pasang)."""
        qs = self.q_values(cell, high)
        return max(qs)[1] if qs else cell

    def rollout(self, start, high, max_len=300):
        """Jalur MEU dari `start`: ikuti kebijakan, asumsi pasang saat ini bertahan (kemungkinan
        terbesar). Return (path, biaya_harapan)."""
        path, seen, cur, total = [start], {start}, start, 0.0
        while cur != self.goal and len(path) < max_len:
            nxt = self.best_action(cur, high)
            if nxt == cur or nxt in seen:
                break
            f = math.sqrt(2) if (nxt[0] != cur[0] and nxt[1] != cur[1]) else 1.0
            total += f * self.E[bool(high)][self.idx[nxt]]
            path.append(nxt)
            seen.add(nxt)
            cur = nxt
        return path, total
