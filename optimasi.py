# -*- coding: utf-8 -*-
"""
optimasi.py — banyak musuh "karakter" beda stat, player harus mengalahkan
mereka berurutan (menang = reward stat naik). Dua pendekatan AI buat
MEMILIH urutannya:

LOCAL SEARCH & OPTIMIZATION  (§3): cari urutan TERBAIK (minimalkan total
    HP yang hilang sepanjang rangkaian pertarungan) lewat Hill Climbing
    (+ random restart) dan Simulated Annealing. Dipakai mode "Otomatis"
    di game.py.
CSP (§4): cari urutan yang SAH (bukan optimal — cukup memenuhi syarat
    "stat pemain minimum sebelum boleh lawan musuh itu") lewat Backtracking
    + MRV (Minimum Remaining Values) + LCV (Least Constraining Value) +
    AC-3 (Arc Consistency).

======================================================================
DEFINISI FORMAL — LOCAL SEARCH
======================================================================
STATE RUANG PENCARIAN : satu permutasi urutan ke-N musuh, order = [e0..e(N-1)]
NEIGHBOR              : tukar (swap) posisi 2 musuh mana pun dalam order
OBJECTIVE (MINIMISASI): evaluate_order(order) = total HP pemain yang hilang
                        sepanjang seluruh rangkaian duel (diprediksi scr
                        deterministik, lihat predict_duel), + penalti besar
                        kalau ada duel yang diprediksi KALAH
ALGORITMA             : Hill Climbing (steepest-ascent/descent per sweep,
                        + random restart biar tidak macet di local optimum)
                        dan Simulated Annealing (sbg pembanding — bisa
                        menerima solusi lebih buruk dgn peluang menurun)

======================================================================
DEFINISI FORMAL — CSP
======================================================================
VARIABLES   : satu per musuh (0..N-1)
DOMAIN(e)   : slot urutan {1..N} yang "layak" buat musuh e — slot k layak
                kalau kekuatan pemain SEBELUM duel ke-k (yaitu setelah k-1
                kemenangan beruntun, lihat slot_power_table) >= required_power(e)
CONSTRAINT  : all-different (tiap slot cuma dipakai 1 musuh) — binary
                constraint antar SETIAP pasang variabel
======================================================================
"""
import math
import random
from dataclasses import replace
import pertarungan as combat

# ---------------------------------------------------------------------------
# 1. ROSTER MUSUH — 5 karakter, stat & gaya tarung (eval function) beda-beda
# ---------------------------------------------------------------------------

# depth = kedalaman pencarian minimax/alpha-beta musuh; mistake = peluang musuh memilih aksi
# terbaik KEDUA. Musuh awal 'berpikir pendek' dan sering salah langkah, musuh akhir hampir
# sempurna -> kesulitan naik halus. Angka hasil tuning simulasi (lihat LAPORAN_BALANCE.md).
ENEMY_ROSTER = [
    combat.Stats(name="Pemburu Liar",      max_hp=60,  atk_min=12, atk_max=27, hit_base=0.60, hit_cap=0.74, depth=2, mistake=0.35),
    combat.Stats(name="Penjaga Hutan",     max_hp=85,  atk_min=13, atk_max=29, hit_base=0.62, hit_cap=0.76, depth=2, mistake=0.25),
    combat.Stats(name="Pendekar Bayangan", max_hp=110, atk_min=15, atk_max=32, hit_base=0.64, hit_cap=0.78, depth=3, mistake=0.18),
    combat.Stats(name="Ksatria Besi",      max_hp=135, atk_min=14, atk_max=32, hit_base=0.66, hit_cap=0.80, depth=3, mistake=0.10),
    combat.Stats(name="Naga Kecil",        max_hp=160, atk_min=16, atk_max=35, hit_base=0.68, hit_cap=0.82, depth=4, mistake=0.04),
]

# gaya tarung NPC tiap musuh saat combat sungguhan (biar kelihatan "beda karakter",
# bukan cuma beda angka) — dipetakan 1:1 dgn ENEMY_ROSTER lewat index
ENEMY_EVAL_FN = [combat.eval_aggressive, combat.eval_defensive, combat.eval_hp_diff,
                combat.eval_stance_aware, combat.eval_aggressive]

DEFAULT_PLAYER_STATS = combat.Stats(name="Pemain", max_hp=100, atk_min=10, atk_max=25,
                                    hit_base=0.70, hit_cap=0.85)

# ---------------------------------------------------------------------------
# 2. REWARD — naik rata (flat) tiap menang, berlaku sama utk musuh manapun
#    (sesuai spek: semua stat naik — HP maks, rentang damage, peluang kena)
# ---------------------------------------------------------------------------

REWARD_MAX_HP = 8
REWARD_ATK = 2
REWARD_HIT_BASE = 0.02
REWARD_HIT_CAP = 0.01


def apply_reward(stats):
    return replace(stats,
                    max_hp=stats.max_hp + REWARD_MAX_HP,
                    atk_min=stats.atk_min + REWARD_ATK,
                    atk_max=stats.atk_max + REWARD_ATK,
                    hit_base=min(0.95, stats.hit_base + REWARD_HIT_BASE),
                    hit_cap=min(0.98, stats.hit_cap + REWARD_HIT_CAP))


def power(stats):
    """Skor kekuatan 1-angka (kasar) — dipakai CSP sbg gerbang kelayakan cepat.
    BUKAN prediksi presisi (itu tugas predict_duel di bawah, dipakai Local Search)."""
    avg_atk = (stats.atk_min + stats.atk_max) / 2
    avg_hit = (stats.hit_base + stats.hit_cap) / 2
    return stats.max_hp + avg_atk * avg_hit * 10


# ---------------------------------------------------------------------------
# 3. LOCAL SEARCH & OPTIMIZATION
# ---------------------------------------------------------------------------

def predict_duel(player_stats, enemy_stats, player_hp=None, max_rounds=40):
    """Prediksi CEPAT & DETERMINISTIK (tanpa RNG, tanpa minimax) 1 duel:
    kedua pihak diasumsikan selalu Attack (kebijakan sederhana), dihitung
    pakai nilai-harapan yang sama dgn pertarungan.apply_action_expected.
    Dipakai sbg fungsi objektif Local Search — dipanggil ratusan/ribuan kali
    per pencarian jadi HARUS cepat, makanya tidak menjalankan minimax asli.
    Return (hp_pemain_sisa, hp_musuh_sisa, jumlah_ronde)."""
    php = player_hp if player_hp is not None else player_stats.max_hp
    ehp = enemy_stats.max_hp
    old_p, old_n = combat.PLAYER_STATS_OVERRIDE, combat.NPC_STATS_OVERRIDE
    combat.PLAYER_STATS_OVERRIDE, combat.NPC_STATS_OVERRIDE = player_stats, enemy_stats
    try:
        for r in range(max_rounds):
            php -= combat.attack_hit_chance(ehp, "npc") * combat.expected_attack_damage("npc")
            if php <= 0:
                return 0.0, ehp, r + 1
            ehp -= combat.attack_hit_chance(php, "player") * combat.expected_attack_damage("player")
            if ehp <= 0:
                return php, 0.0, r + 1
        return php, ehp, max_rounds
    finally:
        combat.PLAYER_STATS_OVERRIDE, combat.NPC_STATS_OVERRIDE = old_p, old_n


def evaluate_order(order, player_base_stats, enemies):
    """Simulasikan SELURUH rangkaian pertarungan sesuai `order` (reward
    diterapkan tiap menang; pemain MULAI SETIAP DUEL dengan HP penuh —
    'istirahat' setelah menang, representasi jeda antar pertarungan).
    Return total biaya (HP hilang + penalti kalau diprediksi kalah) ->
    Local Search MEMINIMALKAN nilai ini. Karena HP selalu penuh di awal
    duel, biaya tiap duel murni mencerminkan SEBERAPA SIAP stat pemain
    saat itu — di sinilah urutan (lawan mudah dulu vs susah dulu) benar2
    berpengaruh ke hasil akhir."""
    stats, cost = player_base_stats, 0.0
    for idx in order:
        enemy = enemies[idx]
        hp_after, ehp_after, rounds = predict_duel(stats, enemy, player_hp=stats.max_hp)
        if hp_after <= 0:
            cost += 500 + enemy.max_hp       # penalti besar: diprediksi kalah, stat TIDAK naik
            continue
        cost += (stats.max_hp - hp_after)    # biaya = HP yang terkuras buat menang duel ini
        stats = apply_reward(stats)
    return cost


def hill_climbing(enemies, player_base_stats, restarts=8, seed=None):
    """Steepest-ascent hill climbing atas ruang PERMUTASI urutan musuh;
    neighbor = tukar 2 posisi. + random restart (local optimum diatasi
    dgn mulai ulang dari permutasi acak lain, bukan backtrack)."""
    rng = random.Random(seed)
    n = len(enemies)
    best_order, best_cost, trace = None, math.inf, []
    for r in range(restarts):
        order = list(range(n))
        rng.shuffle(order)
        cost = evaluate_order(order, player_base_stats, enemies)
        steps = 0
        improved = True
        while improved:
            improved = False
            best_swap, best_swap_cost = None, cost
            for i in range(n):
                for j in range(i + 1, n):
                    cand = order[:]
                    cand[i], cand[j] = cand[j], cand[i]
                    c = evaluate_order(cand, player_base_stats, enemies)
                    steps += 1
                    if c < best_swap_cost - 1e-9:
                        best_swap, best_swap_cost = (i, j), c
            if best_swap:
                i, j = best_swap
                order[i], order[j] = order[j], order[i]
                cost = best_swap_cost
                improved = True
        trace.append({"restart": r, "order": order[:], "cost": cost, "steps": steps})
        if cost < best_cost:
            best_order, best_cost = order[:], cost
    return best_order, best_cost, trace


def simulated_annealing(enemies, player_base_stats, iterations=400, t0=60.0, cooling=0.98, seed=None):
    """Pembanding Hill Climbing: boleh menerima solusi lebih buruk dgn
    peluang exp(-delta/T), T menurun (cooling) tiap iterasi -> makin lama
    makin 'pemilih', mencegah macet di local optimum tanpa random restart."""
    rng = random.Random(seed)
    n = len(enemies)
    order = list(range(n))
    rng.shuffle(order)
    cost = evaluate_order(order, player_base_stats, enemies)
    best_order, best_cost = order[:], cost
    T = t0
    accepted = rejected = 0
    for _ in range(iterations):
        i, j = rng.sample(range(n), 2)
        cand = order[:]
        cand[i], cand[j] = cand[j], cand[i]
        c = evaluate_order(cand, player_base_stats, enemies)
        delta = c - cost
        if delta < 0 or rng.random() < math.exp(-delta / max(T, 1e-6)):
            order, cost = cand, c
            accepted += 1
            if cost < best_cost:
                best_order, best_cost = order[:], cost
        else:
            rejected += 1
        T *= cooling
    return best_order, best_cost, {"accepted": accepted, "rejected": rejected, "final_T": T}


# ---------------------------------------------------------------------------
# 4. CSP — Backtracking + MRV + LCV + AC-3
# ---------------------------------------------------------------------------

def required_power(enemy_stats, margin=0.8):
    """Syarat kekuatan pemain minimum sebelum 'boleh' lawan musuh ini —
    margin<1 berarti pemain tidak perlu LEBIH kuat, cukup cukup dekat
    (karena tarungnya masih ada faktor taktik/RNG, bukan cuma angka)."""
    return power(enemy_stats) * margin


def slot_power_table(player_base_stats, n):
    """power_at_slot[k] = kekuatan pemain SEBELUM duel ke-k (= setelah k-1
    kemenangan). Sama untuk SEMUA urutan karena reward flat (tidak tergantung
    musuh mana yang dikalahkan) — makanya domain tiap musuh bisa dihitung
    independen dari variabel lain, pas buat CSP klasik."""
    stats, table = player_base_stats, {}
    for k in range(1, n + 1):
        table[k] = power(stats)
        stats = apply_reward(stats)
    return table


def initial_domains(enemies, player_base_stats, margin=0.8):
    n = len(enemies)
    sp = slot_power_table(player_base_stats, n)
    return {e: set(k for k in range(1, n + 1) if sp[k] >= required_power(stats, margin))
            for e, stats in enumerate(enemies)}


def revise(domains, xi, xj):
    """AC-3 utk constraint 'not-equal' (all-different): domain(xi) direvisi
    kalau domain(xj) sudah mengerucut ke SATU nilai yang juga ada di domain(xi)."""
    if len(domains[xj]) == 1:
        (v,) = tuple(domains[xj])
        if v in domains[xi]:
            domains[xi] = domains[xi] - {v}
            return True
    return False


def ac3(domains, variables):
    queue = [(xi, xj) for xi in variables for xj in variables if xi != xj]
    revisions = 0
    while queue:
        xi, xj = queue.pop(0)
        if revise(domains, xi, xj):
            revisions += 1
            if not domains[xi]:
                return False, revisions
            for xk in variables:
                if xk != xi and xk != xj:
                    queue.append((xk, xi))
    return True, revisions


def select_unassigned_mrv(domains, assignment, variables):
    """MRV: pilih variabel (musuh) dgn domain TERSISA paling sedikit dulu —
    yang paling 'terjepit', biar kalau gagal ketahuan secepat mungkin."""
    unassigned = [v for v in variables if v not in assignment]
    return min(unassigned, key=lambda v: len(domains[v]))


def order_domain_lcv(var, domains, assignment, variables):
    """LCV: coba nilai (slot) yang PALING SEDIKIT mengunci pilihan variabel
    lain dulu — dihitung dari berapa variabel lain yang masih punya nilai
    itu di domainnya (lebih besar = lebih 'constraining')."""
    def conflicts(value):
        return sum(1 for other in variables
                    if other != var and other not in assignment and value in domains[other])
    return sorted(domains[var], key=conflicts)


def backtracking_search(enemies, player_base_stats, margin=0.8):
    """Return (order | None, stats_log). order=None berarti CSP TIDAK
    PUNYA SOLUSI (tidak ada urutan yang memenuhi syarat stat minimum)."""
    n = len(enemies)
    variables = list(range(n))
    domains = initial_domains(enemies, player_base_stats, margin)
    stats_log = {"nodes": 0, "backtracks": 0}
    ok, ac3_revisions = ac3(domains, variables)
    stats_log["ac3_revisions"] = ac3_revisions
    if not ok or any(not domains[v] for v in variables):
        return None, stats_log

    def backtrack(assignment, domains):
        stats_log["nodes"] += 1
        if len(assignment) == n:
            return dict(assignment)
        var = select_unassigned_mrv(domains, assignment, variables)
        for value in order_domain_lcv(var, domains, assignment, variables):
            if value in assignment.values():
                continue
            assignment[var] = value
            new_domains = {k: set(v) for k, v in domains.items()}
            new_domains[var] = {value}
            ok3, _ = ac3(new_domains, variables)
            if ok3 and all(new_domains[v] for v in variables):
                result = backtrack(assignment, new_domains)
                if result is not None:
                    return result
            del assignment[var]
            stats_log["backtracks"] += 1
        return None

    result = backtrack({}, domains)
    if result is None:
        return None, stats_log
    order = [None] * n
    for e, slot in result.items():
        order[slot - 1] = e
    return order, stats_log