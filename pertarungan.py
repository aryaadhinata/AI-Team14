# -*- coding: utf-8 -*-
"""
pertarungan.py — modul pertarungan giliran (turn-based) antara NPC dan pemain.

Dipicu dari game.py saat NPC berhasil menangkap pemain (lihat Game.on_capture()
di game.py). NPC memilih aksinya lewat pencarian pohon permainan 2-pemain
(minimax / alpha-beta / alpha-beta dengan batas node "early stop" / expectimax
opsional), BUKAN aturan tetap (if/else) — supaya bisa dibandingkan.

======================================================================
DEFINISI FORMAL (ringkas — versi lengkap + hasil eksperimen ada di LAPORAN.md)
======================================================================
STATE     s = (player_hp, npc_hp, turn, to_move, player_last, npc_last)
            player_hp, npc_hp  : nyawa kedua pihak, 0..100
            turn               : ronde ke berapa (1 ronde = 1 giliran NPC + 1 giliran pemain)
            to_move            : True -> giliran NPC memilih aksi, False -> giliran pemain
            player_last/npc_last : aksi terakhir masing-masing pihak (efek defend/parry
                                baru berlaku saat LAWAN menyerang pada giliran berikutnya)

ACTION    A = {ATTACK, DEFEND, HEAL, PARRY}         (branching factor = 4)
            ATTACK : serang lawan (damage dikurangi/dibatalkan kalau lawan DEFEND/PARRY)
            DEFEND : kurangi 50% damage serangan lawan pada giliran berikutnya
            HEAL   : pulihkan HP sendiri
            PARRY  : batalkan penuh + balas damage kalau lawan menyerang giliran berikutnya;
                    tidak berefek apa pun kalau lawan tidak menyerang (aksi berisiko)

TRANSITION  s' = RESULT(s, a)  -> lihat apply_action()

TERMINAL TEST  T(s) := player_hp <= 0  OR  npc_hp <= 0  OR  turn >= MAX_TURNS
                    (batas MAX_TURNS mencegah pertarungan tak berkesudahan / tree tak terbatas)

UTILITY  U(s), s terminal, dari sudut pandang NPC (MAX):
            npc menang   : +10000 - turn   (menang lebih cepat = lebih baik)
            pemain menang: -10000 + turn
            seri/limit giliran habis : 0

EVALUATION FUNCTION  Eval(s) — dipakai saat depth cutoff TERCAPAI sebelum s
            terminal (pengganti U(s) yang belum bisa dihitung). Beberapa versi
            disediakan untuk eksperimen #2 (lihat bagian "EVALUATION FUNCTIONS").
======================================================================
"""

import math
import random
import time
from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# 1. KONSTANTA
# ---------------------------------------------------------------------------

PLAYER_MAX_HP = 100
NPC_MAX_HP = 100
ATTACK_DMG_MIN, ATTACK_DMG_MAX = 10, 25      # poin damage saat serangan BERHASIL
ATTACK_DMG_WEIGHTS = [13, 8, 5, 3, 2, 1]     # bobot utk nilai 10,13,16,19,22,25 berurutan (10 paling jarang)
ATTACK_HIT_BASE, ATTACK_HIT_CAP = 0.70, 0.85  # peluang serangan berhasil: 70% -> naik fibonacci -> maks 85%

DEFEND_BASE_PENETRATION = 0.2   # bertahan pertama kali: cuma 20% damage yang masuk
DEFEND_CAP_PENETRATION = 1.0    # makin sering bertahan BERUNTUN, makin tembus (fibonacci), maks 100%

HEAL_BASE = 15
HEAL_CHANCE_BASE, HEAL_CHANCE_CAP = 0.10, 0.95  # peluang heal berhasil: 10% -> naik fibonacci -> maks 95%
HEAL_BONUS_CHANCE = 0.25         # peluang dapat heal "kritikal" di atas nilai dasar
HEAL_MULT_MIN, HEAL_MULT_MAX = 1.10, 1.67
HEAL_MULT_WEIGHTS = [13, 8, 5, 3, 2, 1]      # sama polanya: 1.10 paling umum, 1.67 paling jarang

PARRY_REFLECT_MIN, PARRY_REFLECT_MAX = 0.5, 2.0   # tangkisan: pantulkan 0.5x - 2x damage yg masuk, uniform

FIB_TERMS = 8            # panjang deret fibonacci yang dipakai sbg "kurva" kenaikan peluang
HP_LEVEL_BUCKET = 12      # tiap 12 HP hilang = naik 1 "level" di kurva fibonacci

MAX_TURNS = 20               # batas ronde -> batas kedalaman tree (lihat TERMINAL TEST)


def _fibonacci(n_terms):
    fibs = [1, 1]
    while len(fibs) < n_terms:
        fibs.append(fibs[-1] + fibs[-2])
    return fibs


_FIB = _fibonacci(FIB_TERMS)   # [1, 1, 2, 3, 5, 8, 13, 21]
_FIB_MAX = _FIB[-1]


def _fib_ramp(level, base, cap):
    """level=0 -> TEPAT base, level maksimum -> TEPAT cap, naik mengikuti fibonacci."""
    idx = max(0, min(int(level), len(_FIB) - 1))
    span = _FIB[-1] - _FIB[0]
    ratio = (_FIB[idx] - _FIB[0]) / span
    return base + (cap - base) * ratio


def _hp_level(current_hp, max_hp=100, bucket=HP_LEVEL_BUCKET):
    missing = max_hp - max(0, current_hp)
    return missing // bucket


def attack_hit_chance(attacker_hp):
    return _fib_ramp(_hp_level(attacker_hp), ATTACK_HIT_BASE, ATTACK_HIT_CAP)


def heal_chance(healer_hp):
    return _fib_ramp(_hp_level(healer_hp), HEAL_CHANCE_BASE, HEAL_CHANCE_CAP)


def defend_penetration(streak):
    return _fib_ramp(streak, DEFEND_BASE_PENETRATION, DEFEND_CAP_PENETRATION)


_ATTACK_DMG_VALUES = [round(ATTACK_DMG_MIN + i * (ATTACK_DMG_MAX - ATTACK_DMG_MIN) / 5) for i in range(6)]
_HEAL_MULT_VALUES = [round(HEAL_MULT_MIN + i * (HEAL_MULT_MAX - HEAL_MULT_MIN) / 5, 2) for i in range(6)]


def roll_attack_damage():
    return random.choices(_ATTACK_DMG_VALUES, weights=ATTACK_DMG_WEIGHTS, k=1)[0]


def roll_heal_multiplier():
    return random.choices(_HEAL_MULT_VALUES, weights=HEAL_MULT_WEIGHTS, k=1)[0]


EXPECTED_ATTACK_DMG = sum(v * w for v, w in zip(_ATTACK_DMG_VALUES, ATTACK_DMG_WEIGHTS)) / sum(ATTACK_DMG_WEIGHTS)
EXPECTED_HEAL_MULT = sum(v * w for v, w in zip(_HEAL_MULT_VALUES, HEAL_MULT_WEIGHTS)) / sum(HEAL_MULT_WEIGHTS)
EXPECTED_PARRY_MULT = (PARRY_REFLECT_MIN + PARRY_REFLECT_MAX) / 2

class Action(Enum):
    ATTACK = "attack"
    DEFEND = "defend"
    HEAL = "heal"
    PARRY = "parry"

ACTIONS = [Action.ATTACK, Action.DEFEND, Action.HEAL, Action.PARRY]  # urutan default

ACTION_LABEL = {
    Action.ATTACK: "Serang", Action.DEFEND: "Bertahan",
    Action.HEAL: "Pulihkan", Action.PARRY: "Tangkis",
}

def describe_event(event) -> str:
    actor = "NPC" if event["actor"] == "npc" else "Pemain"
    a = event["action"]
    if a == Action.ATTACK:
        if event["hit"] is False:
            return f"{actor} menyerang -> MELESET!"
        if event.get("reflect"):
            return f"{actor} menyerang tapi DITANGKIS! kena balik {event['reflect']} dmg"
        return f"{actor} menyerang -> kena {event['damage']} damage"
    if a == Action.HEAL:
        if event["heal"] == 0:
            return f"{actor} mencoba memulihkan diri -> GAGAL"
        tag = " (KRITIKAL!)" if event["bonus_heal"] else ""
        return f"{actor} memulihkan diri +{event['heal']} HP{tag}"
    if a == Action.DEFEND:
        return f"{actor} bersiap bertahan"
    if a == Action.PARRY:
        return f"{actor} bersiap menangkis"
    return f"{actor} -> {a.value}"

# ---------------------------------------------------------------------------
# 2. STATE
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CombatState:
    player_hp: int
    npc_hp: int
    turn: int
    to_move: bool                  # True = giliran NPC (MAX), False = giliran pemain (MIN)
    player_last: "Action | None" = None
    npc_last: "Action | None" = None
    player_defend_streak: int = 0
    npc_defend_streak: int = 0
    player_last_dmg_taken: int = 0
    npc_last_dmg_taken: int = 0

    def is_terminal(self):
        return self.player_hp <= 0 or self.npc_hp <= 0 or self.turn >= MAX_TURNS

    def winner(self):
        """True = NPC menang, False = pemain menang, None = belum/seri."""
        if self.player_hp <= 0 and self.npc_hp <= 0:
            return None
        if self.player_hp <= 0:
            return True
        if self.npc_hp <= 0:
            return False
        return None


def new_combat(player_hp=PLAYER_MAX_HP, npc_hp=NPC_MAX_HP, npc_starts=True):
    return CombatState(player_hp, npc_hp, turn=0, to_move=npc_starts)


# ---------------------------------------------------------------------------
# 3. TRANSITION FUNCTION — RESULT(s, a)
# ---------------------------------------------------------------------------

def apply_action(state: CombatState, action: Action):
    """Terapkan aksi pihak yang bergiliran DENGAN RNG ASLI — dipakai pertarungan
    sungguhan (game.py) & simulate_combat(). Return (state_baru, event) dengan
    event = dict info buat log ('kena 8 damage', 'meleset', dst).
    !! Pencarian NPC (minimax/alpha-beta/dst) TIDAK memakai fungsi ini — mereka
    memakai apply_action_expected() di bawah supaya pohon tetap deterministik."""
    player_hp, npc_hp = state.player_hp, state.npc_hp
    player_last, npc_last = state.player_last, state.npc_last
    p_streak, n_streak = state.player_defend_streak, state.npc_defend_streak
    p_last_dmg, n_last_dmg = state.player_last_dmg_taken, state.npc_last_dmg_taken
    event = {"action": action, "hit": None, "damage": 0, "reflect": 0, "heal": 0, "bonus_heal": False}

    if state.to_move:  # ---- giliran NPC ----
        event["actor"] = "npc"
        if action == Action.ATTACK:
            hit = random.random() < attack_hit_chance(npc_hp)
            event["hit"] = hit
            if hit:
                dmg = roll_attack_damage()
                if player_last == Action.PARRY:
                    reflect = round(dmg * random.uniform(PARRY_REFLECT_MIN, PARRY_REFLECT_MAX))
                    npc_hp -= reflect
                    n_last_dmg = reflect
                    event["reflect"] = reflect
                else:
                    if player_last == Action.DEFEND:
                        dmg = round(dmg * defend_penetration(p_streak))
                    player_hp -= dmg
                    p_last_dmg = dmg
                    event["damage"] = dmg
        elif action == Action.HEAL:
            if random.random() < heal_chance(npc_hp):
                if random.random() < HEAL_BONUS_CHANCE:
                    healed = round((HEAL_BASE + (n_last_dmg or 5)) * roll_heal_multiplier())
                    event["bonus_heal"] = True
                else:
                    healed = HEAL_BASE
                npc_hp = min(NPC_MAX_HP, npc_hp + healed)
                event["heal"] = healed
        n_streak = n_streak + 1 if action == Action.DEFEND else 0
        npc_last = action
    else:  # ---- giliran pemain ----
        event["actor"] = "player"
        if action == Action.ATTACK:
            hit = random.random() < attack_hit_chance(player_hp)
            event["hit"] = hit
            if hit:
                dmg = roll_attack_damage()
                if npc_last == Action.PARRY:
                    reflect = round(dmg * random.uniform(PARRY_REFLECT_MIN, PARRY_REFLECT_MAX))
                    player_hp -= reflect
                    p_last_dmg = reflect
                    event["reflect"] = reflect
                else:
                    if npc_last == Action.DEFEND:
                        dmg = round(dmg * defend_penetration(n_streak))
                    npc_hp -= dmg
                    n_last_dmg = dmg
                    event["damage"] = dmg
        elif action == Action.HEAL:
            if random.random() < heal_chance(player_hp):
                if random.random() < HEAL_BONUS_CHANCE:
                    healed = round((HEAL_BASE + (p_last_dmg or 5)) * roll_heal_multiplier())
                    event["bonus_heal"] = True
                else:
                    healed = HEAL_BASE
                player_hp = min(PLAYER_MAX_HP, player_hp + healed)
                event["heal"] = healed
        p_streak = p_streak + 1 if action == Action.DEFEND else 0
        player_last = action

    new_turn = state.turn + (1 if not state.to_move else 0)
    new_state = CombatState(max(player_hp, 0), max(npc_hp, 0), new_turn, not state.to_move,
                            player_last, npc_last, p_streak, n_streak, p_last_dmg, n_last_dmg)
    return new_state, event


def apply_action_expected(state: CombatState, action: Action) -> CombatState:
    """Versi DETERMINISTIK (nilai harapan / expected value, TANPA RNG) dari
    apply_action — dipakai HANYA oleh minimax/alpha-beta/early-stop/expectimax
    supaya NPC tetap bisa mikir beberapa langkah ke depan tanpa pohonnya
    meledak/berubah-ubah karena RNG. Tidak menghasilkan event (bukan buat log)."""
    player_hp, npc_hp = state.player_hp, state.npc_hp
    player_last, npc_last = state.player_last, state.npc_last
    p_streak, n_streak = state.player_defend_streak, state.npc_defend_streak

    def expected_heal(hp):
        p_heal = heal_chance(hp)
        e_amount = ((1 - HEAL_BONUS_CHANCE) * HEAL_BASE
                    + HEAL_BONUS_CHANCE * (HEAL_BASE + 5) * EXPECTED_HEAL_MULT)
        return p_heal * e_amount

    if state.to_move:
        if action == Action.ATTACK:
            p_hit = attack_hit_chance(npc_hp)
            if player_last == Action.PARRY:
                npc_hp -= p_hit * EXPECTED_ATTACK_DMG * EXPECTED_PARRY_MULT
            else:
                dmg = p_hit * EXPECTED_ATTACK_DMG
                if player_last == Action.DEFEND:
                    dmg *= defend_penetration(p_streak)
                player_hp -= dmg
        elif action == Action.HEAL:
            npc_hp = min(NPC_MAX_HP, npc_hp + expected_heal(npc_hp))
        n_streak = n_streak + 1 if action == Action.DEFEND else 0
        npc_last = action
    else:
        if action == Action.ATTACK:
            p_hit = attack_hit_chance(player_hp)
            if npc_last == Action.PARRY:
                player_hp -= p_hit * EXPECTED_ATTACK_DMG * EXPECTED_PARRY_MULT
            else:
                dmg = p_hit * EXPECTED_ATTACK_DMG
                if npc_last == Action.DEFEND:
                    dmg *= defend_penetration(n_streak)
                npc_hp -= dmg
        elif action == Action.HEAL:
            player_hp = min(PLAYER_MAX_HP, player_hp + expected_heal(player_hp))
        p_streak = p_streak + 1 if action == Action.DEFEND else 0
        player_last = action

    new_turn = state.turn + (1 if not state.to_move else 0)
    return CombatState(max(player_hp, 0), max(npc_hp, 0), new_turn, not state.to_move,
                        player_last, npc_last, p_streak, n_streak,
                        state.player_last_dmg_taken, state.npc_last_dmg_taken)

# ---------------------------------------------------------------------------
# 4. UTILITY (state terminal)
# ---------------------------------------------------------------------------

def utility(state: CombatState) -> float:
    w = state.winner()
    if w is True:
        return 10_000 - state.turn
    if w is False:
        return -10_000 + state.turn
    return 0.0  # seri / limit giliran habis tanpa pemenang


# ---------------------------------------------------------------------------
# 5. EVALUATION FUNCTIONS (dipakai saat depth cutoff, state belum terminal)
#    Beberapa varian sengaja disediakan untuk eksperimen #2.
# ---------------------------------------------------------------------------

def eval_hp_diff(state: CombatState) -> float:
    """Netral: selisih HP apa adanya."""
    return state.npc_hp - state.player_hp


def eval_defensive(state: CombatState) -> float:
    """NPC menghargai HP-nya sendiri jauh lebih tinggi -> cenderung heal/defend
    lebih dulu, baru menyerang saat aman."""
    return 1.8 * state.npc_hp - state.player_hp


def eval_aggressive(state: CombatState) -> float:
    """NPC menghargai menghabisi HP lawan jauh lebih tinggi -> cenderung
    menyerang terus meski HP sendiri terkuras."""
    return state.npc_hp - 2.2 * state.player_hp


def eval_stance_aware(state: CombatState) -> float:
    """Selisih HP + sedikit bonus posisi (in-progress defend/parry dihargai
    karena berpotensi mengurangi damage giliran berikut)."""
    score = state.npc_hp - state.player_hp
    if state.npc_last == Action.DEFEND:
        score += 3
    if state.npc_last == Action.PARRY:
        score += 2
    return score


EVAL_FUNCTIONS = {
    "hp_diff": eval_hp_diff,
    "defensive": eval_defensive,
    "aggressive": eval_aggressive,
    "stance_aware": eval_stance_aware,
}


# ---------------------------------------------------------------------------
# 6. ALGORITMA PENCARIAN — semua mengembalikan (nilai, aksi_terbaik) dan
#    menghitung node yang dieksplorasi lewat dict `counters` (buat overlay #2
#    & eksperimen node count).
# ---------------------------------------------------------------------------

def minimax(state, depth, eval_fn, action_order, counters):
    counters["nodes"] += 1
    if state.is_terminal():
        return utility(state), None
    if depth == 0:
        return eval_fn(state), None
    best_action = None
    if state.to_move:  # NPC = MAX
        best_val = -math.inf
        for a in action_order:
            val, _ = minimax(apply_action_expected(state, a), depth - 1, eval_fn, action_order, counters)
            if val > best_val:
                best_val, best_action = val, a
        return best_val, best_action
    else:  # pemain diasumsikan optimal = MIN (skenario terburuk buat NPC)
        best_val = math.inf
        for a in action_order:
            val, _ = minimax(apply_action_expected(state, a), depth - 1, eval_fn, action_order, counters)
            if val < best_val:
                best_val, best_action = val, a
        return best_val, best_action


def alphabeta(state, depth, alpha, beta, eval_fn, action_order, counters):
    counters["nodes"] += 1
    if state.is_terminal():
        return utility(state), None
    if depth == 0:
        return eval_fn(state), None
    best_action = None
    if state.to_move:
        best_val = -math.inf
        for a in action_order:
            val, _ = alphabeta(apply_action_expected(state, a), depth - 1, alpha, beta, eval_fn, action_order, counters)
            if val > best_val:
                best_val, best_action = val, a
            alpha = max(alpha, best_val)
            if alpha >= beta:
                counters["pruned"] = counters.get("pruned", 0) + 1
                break
        return best_val, best_action
    else:
        best_val = math.inf
        for a in action_order:
            val, _ = alphabeta(apply_action_expected(state, a), depth - 1, alpha, beta, eval_fn, action_order, counters)
            if val < best_val:
                best_val, best_action = val, a
            beta = min(beta, best_val)
            if alpha >= beta:
                counters["pruned"] = counters.get("pruned", 0) + 1
                break
        return best_val, best_action


def alphabeta_early_stop(state, depth, alpha, beta, eval_fn, action_order, counters, budget):
    """Sama seperti alpha-beta, tapi pencarian dihentikan paksa begitu jumlah
    node yang dieksplorasi mencapai `budget` — sisa cabang dianggap seadanya
    lewat eval_fn. Dipakai untuk eksperimen 'early stop' vs alpha-beta penuh."""
    counters["nodes"] += 1
    if state.is_terminal():
        return utility(state), None
    if depth == 0 or counters["nodes"] >= budget:
        return eval_fn(state), None
    best_action = None
    if state.to_move:
        best_val = -math.inf
        for a in action_order:
            if counters["nodes"] >= budget:
                break
            val, _ = alphabeta_early_stop(apply_action_expected(state, a), depth - 1, alpha, beta,
                                            eval_fn, action_order, counters, budget)
            if val > best_val:
                best_val, best_action = val, a
            alpha = max(alpha, best_val)
            if alpha >= beta:
                counters["pruned"] = counters.get("pruned", 0) + 1
                break
        return best_val, best_action
    else:
        best_val = math.inf
        for a in action_order:
            if counters["nodes"] >= budget:
                break
            val, _ = alphabeta_early_stop(apply_action_expected(state, a), depth - 1, alpha, beta,
                                            eval_fn, action_order, counters, budget)
            if val < best_val:
                best_val, best_action = val, a
            beta = min(beta, best_val)
            if alpha >= beta:
                counters["pruned"] = counters.get("pruned", 0) + 1
                break
        return best_val, best_action


def expectimax(state, depth, eval_fn, action_order, counters, player_policy=None):
    """Variasi opsional: giliran pemain diperlakukan sebagai CHANCE node
    (pemain tidak diasumsikan optimal, tapi mengikuti distribusi probabilitas
    `player_policy(state) -> {Action: prob}`). Default: uniform random."""
    counters["nodes"] += 1
    if state.is_terminal():
        return utility(state), None
    if depth == 0:
        return eval_fn(state), None
    if state.to_move:  # NPC tetap MAX
        best_val, best_action = -math.inf, None
        for a in action_order:
            val, _ = expectimax(apply_action_expected(state, a), depth - 1, eval_fn, action_order, counters, player_policy)
            if val > best_val:
                best_val, best_action = val, a
        return best_val, best_action
    else:  # CHANCE
        probs = player_policy(state) if player_policy else {a: 1.0 / len(action_order) for a in action_order}
        exp_val = 0.0
        for a in action_order:
            p = probs.get(a, 0.0)
            if p == 0.0:
                continue
            val, _ = expectimax(apply_action_expected(state, a), depth - 1, eval_fn, action_order, counters, player_policy)
            exp_val += p * val
        return exp_val, None


ALGORITHMS = {
    "minimax": minimax,
    "alphabeta": alphabeta,
    "early_stop": alphabeta_early_stop,
    "expectimax": expectimax,
}


# ---------------------------------------------------------------------------
# 7. KEPUTUSAN NPC (dipanggil dari game.py tiap giliran NPC) — juga
#    menghasilkan data debug: skor tiap aksi akar (#1) & jumlah node (#2).
# ---------------------------------------------------------------------------

def choose_npc_action(state, algorithm="alphabeta", depth=4, eval_fn=eval_hp_diff,
                    action_order=None, node_budget=60, player_policy=None):
    """Return (aksi_terpilih: Action, debug: dict).
    debug['considered'] = [(Action, skor_atau_None), ...]  — buat overlay #1
    debug['nodes']      = total node yang dieksplorasi     — buat overlay #2
    """
    order = list(action_order) if action_order else list(ACTIONS)
    counters = {"nodes": 0, "pruned": 0}
    considered = []
    t0 = time.perf_counter()

    for a in order:
        child = apply_action_expected(state, a)
        if algorithm == "minimax":
            val, _ = minimax(child, depth - 1, eval_fn, order, counters)
        elif algorithm == "alphabeta":
            val, _ = alphabeta(child, depth - 1, -math.inf, math.inf, eval_fn, order, counters)
        elif algorithm == "early_stop":
            if counters["nodes"] >= node_budget:
                considered.append((a, None))
                continue
            val, _ = alphabeta_early_stop(child, depth - 1, -math.inf, math.inf, eval_fn,
                                        order, counters, node_budget)
        elif algorithm == "expectimax":
            val, _ = expectimax(child, depth - 1, eval_fn, order, counters, player_policy)
        else:
            raise ValueError(f"algoritma tidak dikenal: {algorithm}")
        considered.append((a, val))

    scored = [(a, v) for a, v in considered if v is not None]
    best_action = max(scored, key=lambda x: x[1])[0] if scored else random.choice(order)

    debug = {
        "algorithm": algorithm, "depth": depth,
        "eval_fn": getattr(eval_fn, "__name__", str(eval_fn)),
        "considered": considered,
        "nodes": counters["nodes"],
        "pruned": counters.get("pruned", 0),
        "time_ms": (time.perf_counter() - t0) * 1000,
        "chosen": best_action,
    }
    return best_action, debug


# ---------------------------------------------------------------------------
# 8. KEBIJAKAN PEMAIN SEDERHANA (buat simulasi/eksperimen tanpa input manusia)
# ---------------------------------------------------------------------------

def player_policy_greedy(state: CombatState):
    """Pemain 'bot' sederhana buat simulasi: menyerang kalau HP masih aman,
    heal kalau HP rendah, sesekali bertahan. Dipakai di eksperimen supaya
    hasilnya reproducible tanpa perlu pemain manusia."""
    if state.player_hp <= 30:
        return Action.HEAL
    if state.player_hp <= 55 and random.random() < 0.4:
        return Action.DEFEND
    return Action.ATTACK


# ---------------------------------------------------------------------------
# 9. DEBUG OVERLAY (dipanggil dari draw_hud game.py) — menampilkan:
#    (1) aksi yang dipertimbangkan NPC & skornya, (2) jumlah node dieksplorasi.
#    Gaya kartu mengikuti dashboard di game.py (_card_title / _card_row).
# ---------------------------------------------------------------------------

def render_combat_debug_card(screen, pygame_font_bold, pygame_font_small, x, y, width, debug):
    """Gambar satu kartu debug pertarungan ke `screen` (pygame.Surface) di posisi
    (x, y), lebar `width`. Return posisi y setelah kartu (buat disambung kartu lain).
    `debug` adalah dict hasil choose_npc_action()."""
    import pygame  # lazy import: modul ini tetap bisa dipakai tanpa pygame (mis. eksperimen CLI)

    TXT, DIM, ACC = (235, 244, 230), (150, 168, 145), (255, 220, 110)
    GOOD, BAD = (130, 230, 150), (255, 140, 110)

    screen.blit(pygame_font_bold.render("DEBUG PERTARUNGAN NPC", True, (140, 205, 150)), (x, y))
    pygame.draw.line(screen, (52, 74, 56), (x, y + 19), (x + width, y + 19), 1)
    y += 25

    algo_label = {"minimax": "Minimax", "alphabeta": "Alpha-Beta", "early_stop": "Early Stop", "expectimax": "Expectimax"}
    screen.blit(pygame_font_small.render(
        f"Algoritma: {algo_label.get(debug['algorithm'], debug['algorithm'])}  "
        f"(depth={debug['depth']}, eval={debug['eval_fn']})", True, DIM), (x, y))
    y += 18

    # (1) aksi yang dipertimbangkan & skornya, aksi terpilih disorot
    scored = [(a, v) for a, v in debug["considered"] if v is not None]
    best_v = max(v for _, v in scored) if scored else None
    for a, v in debug["considered"]:
        chosen = a == debug["chosen"]
        label = ACTION_LABEL.get(a, a.value)
        color = ACC if chosen else TXT
        val_txt = f"{v:+.1f}" if v is not None else "(belum dievaluasi)"
        val_color = GOOD if (v is not None and v == best_v) else DIM
        prefix = "-> " if chosen else "   "
        screen.blit(pygame_font_small.render(f"{prefix}{label}", True, color), (x, y))
        vs = pygame_font_small.render(val_txt, True, val_color)
        screen.blit(vs, (x + width - vs.get_width(), y))
        y += 17
    y += 4

    # (2) node count (buat bandingkan minimax vs alpha-beta vs early stop)
    pruned_txt = f"  (dipangkas: {debug['pruned']})" if debug.get("pruned") else ""
    screen.blit(pygame_font_small.render(
        f"Node dieksplorasi: {debug['nodes']}{pruned_txt}", True, TXT), (x, y))
    y += 17
    screen.blit(pygame_font_small.render(f"Waktu: {debug['time_ms']:.2f} ms", True, DIM), (x, y))
    y += 20
    return y


def simulate_combat(algorithm="alphabeta", depth=4, eval_fn=eval_hp_diff,
                    action_order=None, node_budget=60, player_fn=player_policy_greedy,
                    start_hp=(100, 100), verbose=False):
    """Jalankan satu pertarungan penuh (NPC lewat search, pemain lewat player_fn)
    sampai terminal. Return log lengkap — dipakai eksperimen #5 (tingkah laku NPC)."""
    state = new_combat(start_hp[0], start_hp[1])
    log = []
    total_nodes = 0
    while not state.is_terminal():
        if state.to_move:
            action, dbg = choose_npc_action(state, algorithm, depth, eval_fn, action_order, node_budget)
            total_nodes += dbg["nodes"]
        else:
            action = player_fn(state)
            dbg = None
        state, event = apply_action(state, action)
        log.append((("npc" if not state.to_move else "player"), action, state, dbg, event))
        if verbose:
            who = "NPC" if dbg else "Pemain"
            print(f"  {who:8s} -> {action.value:8s}  | player_hp={state.player_hp:3d} npc_hp={state.npc_hp:3d}")
    return {"final": state, "winner": state.winner(), "turns": state.turn,
            "log": log, "total_nodes": total_nodes}
