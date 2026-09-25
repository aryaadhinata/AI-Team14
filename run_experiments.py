# -*- coding: utf-8 -*-
"""Jalankan 6 eksperimen yang diminta & cetak hasilnya (dipakai buat mengisi
LAPORAN_PERTARUNGAN.md dengan angka asli, bukan perkiraan).

UPDATE: disesuaikan dengan mekanik probabilitas baru di pertarungan.py —
apply_action() sekarang balikin (state, event) bukan cuma state, jadi log
simulate_combat() jadi 5-tuple (who, action, state, dbg, event)."""
import math, random, time, json
import pertarungan as m

random.seed(7)

def fresh_state(php=100, nhp=70):
    # HP NPC sengaja dibuat < player supaya root punya cukup opsi menarik (bukan cuma "menang pasti")
    return m.new_combat(player_hp=php, npc_hp=nhp)

print("="*70)
print("EKSPERIMEN 1: minimax vs alpha-beta pruning (node count, waktu)")
print("="*70)
for depth in (2, 3, 4, 5, 6):
    s = fresh_state()
    c1 = {"nodes": 0}
    t0 = time.perf_counter()
    v1, a1 = m.minimax(s, depth, m.eval_hp_diff, m.ACTIONS, c1)
    t1 = (time.perf_counter()-t0)*1000
    c2 = {"nodes": 0, "pruned": 0}
    t0 = time.perf_counter()
    v2, a2 = m.alphabeta(s, depth, -math.inf, math.inf, m.eval_hp_diff, m.ACTIONS, c2)
    t2 = (time.perf_counter()-t0)*1000
    print(f"depth={depth:2d}  minimax: nodes={c1['nodes']:6d} val={v1:7.1f} t={t1:7.3f}ms  |  "
            f"alphabeta: nodes={c2['nodes']:6d} (pruned {c2['pruned']:4d}) val={v2:7.1f} t={t2:7.3f}ms  "
            f"-> hemat {100*(1-c2['nodes']/c1['nodes']):5.1f}%  | aksi sama? {a1==a2}")

print()
print("="*70)
print("EKSPERIMEN 2: perbandingan evaluation function (aksi terpilih & node)")
print("="*70)
s = fresh_state(php=100, nhp=55)  # NPC HP rendah -> di sinilah eval function paling kelihatan bedanya
for name, fn in m.EVAL_FUNCTIONS.items():
    a, dbg = m.choose_npc_action(s, algorithm="alphabeta", depth=4, eval_fn=fn)
    scores = {k.value: (round(v,1) if v is not None else None) for k, v in dbg["considered"]}
    print(f"{name:13s} -> pilih {a.value:8s} | skor tiap aksi: {scores} | nodes={dbg['nodes']}")

print()
print("="*70)
print("EKSPERIMEN 3: urutan aksi (pengaruh ke alpha-beta pruning)")
print("="*70)
orders = {
    "default (attack,defend,heal,parry)": list(m.ACTIONS),
    "acak-tetap (parry,heal,defend,attack)": [m.Action.PARRY, m.Action.HEAL, m.Action.DEFEND, m.Action.ATTACK],
    "heal-dulu (heal,defend,parry,attack)": [m.Action.HEAL, m.Action.DEFEND, m.Action.PARRY, m.Action.ATTACK],
}
s = fresh_state()
for name, order in orders.items():
    c = {"nodes": 0, "pruned": 0}
    v, a = m.alphabeta(s, 5, -math.inf, math.inf, m.eval_hp_diff, order, c)
    print(f"{name:42s} -> nodes={c['nodes']:6d} pruned={c['pruned']:4d} val={v:7.1f} aksi_akar={a.value if a else None}")

print()
print("="*70)
print("EKSPERIMEN 4: perbandingan kedalaman (ukuran tree & waktu)")
print("="*70)
s = fresh_state()
for depth in range(1, 8):
    c = {"nodes": 0, "pruned": 0}
    t0 = time.perf_counter()
    v, a = m.alphabeta(s, depth, -math.inf, math.inf, m.eval_hp_diff, m.ACTIONS, c)
    dt = (time.perf_counter()-t0)*1000
    print(f"depth={depth}  nodes={c['nodes']:7d}  pruned={c['pruned']:6d}  time={dt:8.3f}ms  aksi={a.value if a else '-':8s} val={v:.1f}")

print()
print("="*70)
print("EKSPERIMEN 5: tingkah laku NPC (simulasi penuh per eval function, MAX_TURNS default)")
print("="*70)
for name, fn in m.EVAL_FUNCTIONS.items():
    random.seed(42)
    res = m.simulate_combat(algorithm="alphabeta", depth=4, eval_fn=fn, verbose=False)
    npc_actions = [a.value for who, a, st, dbg, event in res["log"] if who == "npc"]
    counts = {a: npc_actions.count(a) for a in ("attack","defend","heal","parry")}
    winner = {True: "NPC", False: "Pemain", None: "Seri/limit"}[res["winner"]]
    print(f"{name:13s} -> pemenang={winner:11s} turns={res['turns']:2d}  aksi NPC: {counts}")

print()
print("="*70)
print("EKSPERIMEN 6 (opsional): expectimax vs minimax (pemain acak vs pemain optimal)")
print("="*70)
def random_policy(state):
    return {a: 1/len(m.ACTIONS) for a in m.ACTIONS}

s = fresh_state()
c_mm = {"nodes": 0}
v_mm, a_mm = m.minimax(s, 4, m.eval_hp_diff, m.ACTIONS, c_mm)
c_em = {"nodes": 0}
v_em, a_em = m.expectimax(s, 4, m.eval_hp_diff, m.ACTIONS, c_em, player_policy=random_policy)
print(f"minimax   (asumsi pemain optimal) -> aksi={a_mm.value if a_mm else None} val={v_mm:.1f} nodes={c_mm['nodes']}")
print(f"expectimax(asumsi pemain acak)    -> aksi={a_em.value if a_em else None} val={v_em:.1f} nodes={c_em['nodes']}")

def run_many(algorithm, n=60, eval_fn=m.eval_hp_diff, **kw):
    wins = 0
    for i in range(n):
        random.seed(1000+i)
        res = m.simulate_combat(algorithm=algorithm, depth=3, eval_fn=eval_fn,
                                 player_fn=lambda st: random.choice(m.ACTIONS), **kw)
        if res["winner"] is True:
            wins += 1
    return wins

wins_minimax = run_many("minimax", n=60)
wins_expecti = run_many("expectimax", n=60)
print(f"lawan 60x pemain ACAK, MAX_TURNS default -> minimax menang {wins_minimax}/60   |   expectimax menang {wins_expecti}/60")

# ---------------------------------------------------------------------------
# BONUS: eksperimen 1 (pertama kali dijalankan lewat run_experiments.py, sebelum
# mekanik probabilitas ditambahkan) selalu berakhir menang. Setelah damage jadi
# probabilistik (hit 70-85%, dmg 5-10) & heal jadi kuat (10-95% + bonus kritikal),
# hasil di atas kemungkinan besar SERI SEMUA di MAX_TURNS default (20) karena
# rata-rata damage per giliran turun jauh (dulu pasti 18, sekarang efektif ~4-5).
# Bagian ini menjalankan ulang eksperimen 5 & 6 dengan MAX_TURNS dilonggarkan
# (HANYA di skrip ini, tidak mengubah game sungguhan) supaya kelihatan siapa yang
# sebenarnya lebih unggul kalau pertarungannya dibiarkan lebih panjang.
# ---------------------------------------------------------------------------
print()
print("="*70)
print("BONUS — EKSPERIMEN 5 & 6 diulang dengan MAX_TURNS=60 (analisis saja)")
print("="*70)
m.MAX_TURNS = 60

for name, fn in m.EVAL_FUNCTIONS.items():
    random.seed(42)
    res = m.simulate_combat(algorithm="alphabeta", depth=4, eval_fn=fn, verbose=False)
    npc_actions = [a.value for who, a, st, dbg, event in res["log"] if who == "npc"]
    counts = {a: npc_actions.count(a) for a in ("attack","defend","heal","parry")}
    winner = {True: "NPC", False: "Pemain", None: "Seri/limit"}[res["winner"]]
    print(f"{name:13s} -> pemenang={winner:11s} turns={res['turns']:2d}  aksi NPC: {counts}")

def run_many_long(algorithm, n=60, eval_fn=m.eval_hp_diff, **kw):
    wins, draws, total_turns = 0, 0, 0
    for i in range(n):
        random.seed(1000+i)
        res = m.simulate_combat(algorithm=algorithm, depth=3, eval_fn=eval_fn,
                                 player_fn=lambda st: random.choice(m.ACTIONS), **kw)
        total_turns += res["turns"]
        wins += res["winner"] is True
        draws += res["winner"] is None
    return wins, draws, total_turns / n

wm, dm, tm = run_many_long("minimax")
we, de, te = run_many_long("expectimax")
print(f"minimax    (MAX_TURNS=60) -> menang {wm}/60  seri {dm}/60  rata2 {tm:.1f} giliran")
print(f"expectimax (MAX_TURNS=60) -> menang {we}/60  seri {de}/60  rata2 {te:.1f} giliran")