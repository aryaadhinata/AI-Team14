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

ATTACK_DMG = 5
DEFEND_REDUCTION = 0.5      # damage masuk dikali ini kalau korban DEFEND giliran lalu
HEAL_AMOUNT = 15
PARRY_COUNTER_DMG = 10      # damage balik ke penyerang kalau korban PARRY giliran lalu
MAX_TURNS = 20               # batas ronde -> batas kedalaman tree (lihat TERMINAL TEST)


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

def apply_action(state: CombatState, action: Action) -> CombatState:
    """Terapkan satu aksi milik pihak yang sedang bergiliran (state.to_move),
    kembalikan state baru. Giliran penuh (turn) bertambah setelah PEMAIN
    bergerak, jadi satu 'turn' = satu ronde (NPC lalu pemain)."""
    player_hp, npc_hp = state.player_hp, state.npc_hp
    player_last, npc_last = state.player_last, state.npc_last

    if state.to_move:  # --- giliran NPC ---
        opp_last = player_last
        if action == Action.ATTACK:
            if opp_last == Action.PARRY:
                npc_hp -= PARRY_COUNTER_DMG          # tangkisan pemain berhasil
            else:
                dmg = ATTACK_DMG
                if opp_last == Action.DEFEND:
                    dmg = int(dmg * DEFEND_REDUCTION)
                player_hp -= dmg
        elif action == Action.HEAL:
            npc_hp = min(NPC_MAX_HP, npc_hp + HEAL_AMOUNT)
        npc_last = action
    else:  # --- giliran pemain ---
        opp_last = npc_last
        if action == Action.ATTACK:
            if opp_last == Action.PARRY:
                player_hp -= PARRY_COUNTER_DMG        # tangkisan NPC berhasil
            else:
                dmg = ATTACK_DMG
                if opp_last == Action.DEFEND:
                    dmg = int(dmg * DEFEND_REDUCTION)
                npc_hp -= dmg
        elif action == Action.HEAL:
            player_hp = min(PLAYER_MAX_HP, player_hp + HEAL_AMOUNT)
        player_last = action

    new_turn = state.turn + (1 if not state.to_move else 0)
    return CombatState(max(player_hp, 0), max(npc_hp, 0), new_turn,
                        not state.to_move, player_last, npc_last)


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
            val, _ = minimax(apply_action(state, a), depth - 1, eval_fn, action_order, counters)
            if val > best_val:
                best_val, best_action = val, a
        return best_val, best_action
    else:  # pemain diasumsikan optimal = MIN (skenario terburuk buat NPC)
        best_val = math.inf
        for a in action_order:
            val, _ = minimax(apply_action(state, a), depth - 1, eval_fn, action_order, counters)
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
            val, _ = alphabeta(apply_action(state, a), depth - 1, alpha, beta, eval_fn, action_order, counters)
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
            val, _ = alphabeta(apply_action(state, a), depth - 1, alpha, beta, eval_fn, action_order, counters)
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
            val, _ = alphabeta_early_stop(apply_action(state, a), depth - 1, alpha, beta,
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
            val, _ = alphabeta_early_stop(apply_action(state, a), depth - 1, alpha, beta,
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
            val, _ = expectimax(apply_action(state, a), depth - 1, eval_fn, action_order, counters, player_policy)
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
            val, _ = expectimax(apply_action(state, a), depth - 1, eval_fn, action_order, counters, player_policy)
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
        child = apply_action(state, a)
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
        state = apply_action(state, action)
        log.append((("npc" if not state.to_move else "player"), action, state, dbg))
        if verbose:
            who = "NPC" if dbg else "Pemain"
            print(f"  {who:8s} -> {action.value:8s}  | player_hp={state.player_hp:3d} npc_hp={state.npc_hp:3d}")
    return {"final": state, "winner": state.winner(), "turns": state.turn,
            "log": log, "total_nodes": total_nodes}
