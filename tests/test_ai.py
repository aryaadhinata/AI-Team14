# -*- coding: utf-8 -*-
"""Tes otomatis AI-Team14.  Jalankan dari root repo:  python -m unittest discover -s tests -v
Tidak butuh pygame (modul AI-nya murni Python)."""
import itertools
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import optimasi as opt          # noqa: E402
import pertarungan as combat    # noqa: E402

ENEMIES = opt.ENEMY_ROSTER
PLAYER = opt.DEFAULT_PLAYER_STATS


class TestAdversarialSearch(unittest.TestCase):
    """Alpha-Beta harus bernilai SAMA dgn Minimax (hanya lebih sedikit node)."""

    def _root_value(self, fn, state, depth, eval_fn, order):
        counters = {"nodes": 0, "pruned": 0}
        if fn is combat.minimax:
            return fn(state, depth, eval_fn, order, counters)[0], counters
        return fn(state, depth, float("-inf"), float("inf"), eval_fn, order, counters)[0], counters

    def test_alphabeta_sama_dengan_minimax(self):
        order = list(combat.Action)
        states = [combat.new_combat(),
                    combat.new_combat(player_hp=55, npc_hp=40, npc_starts=True),
                    combat.new_combat(player_hp=20, npc_hp=90, npc_starts=True)]
        for st in states:
            for depth in (2, 3, 4):
                for ev in (combat.eval_hp_diff, combat.eval_defensive,
                            combat.eval_aggressive, combat.eval_stance_aware):
                    v_mm, c_mm = self._root_value(combat.minimax, st, depth, ev, order)
                    v_ab, c_ab = self._root_value(combat.alphabeta, st, depth, ev, order)
                    self.assertAlmostEqual(v_mm, v_ab, places=6)
                    self.assertLessEqual(c_ab["nodes"], c_mm["nodes"])


class TestLocalSearch(unittest.TestCase):
    def test_regresi_biaya_greedy_default(self):
        """Pin angka yang dipakai laporan (POST_FIGHT_RECOVERY=1.0)."""
        self.assertAlmostEqual(opt.evaluate_order([0, 1, 2, 3, 4], PLAYER, ENEMIES, recovery=1.0), 1039.79, places=1)

    def test_hill_climbing_adalah_local_optimum(self):
        order, cost, _ = opt.hill_climbing(ENEMIES, PLAYER, restarts=6, seed=1)
        for i, j in itertools.combinations(range(len(order)), 2):
            cand = order[:]
            cand[i], cand[j] = cand[j], cand[i]
            self.assertGreaterEqual(opt.evaluate_order(cand, PLAYER, ENEMIES), cost - 1e-6)

    def test_hill_climbing_tidak_lebih_buruk_dari_start_acak(self):
        order, cost, trace = opt.hill_climbing(ENEMIES, PLAYER, restarts=4, seed=2)
        self.assertLessEqual(cost, min(t["cost"] for t in trace) + 1e-9)

    def test_biaya_tidak_pernah_lebih_kecil_dari_brute_force(self):
        best = min(opt.evaluate_order(list(p), PLAYER, ENEMIES) for p in itertools.permutations(range(5)))
        _, hc_cost, _ = opt.hill_climbing(ENEMIES, PLAYER, restarts=12, seed=3)
        _, sa_cost, _ = opt.simulated_annealing(ENEMIES, PLAYER, iterations=400, seed=3)
        self.assertGreaterEqual(hc_cost, best - 1e-6)
        self.assertGreaterEqual(sa_cost, best - 1e-6)

    def test_predict_duel_tidak_meninggalkan_override(self):
        before = (combat.PLAYER_STATS_OVERRIDE, combat.NPC_STATS_OVERRIDE)
        opt.predict_duel(PLAYER, ENEMIES[0])
        self.assertEqual((combat.PLAYER_STATS_OVERRIDE, combat.NPC_STATS_OVERRIDE), before)

    def test_stat_overrides_dipulihkan_walau_error(self):
        with self.assertRaises(RuntimeError):
            with combat.stat_overrides(PLAYER, ENEMIES[0]):
                raise RuntimeError("x")
        self.assertIsNone(combat.PLAYER_STATS_OVERRIDE)
        self.assertIsNone(combat.NPC_STATS_OVERRIDE)

    def test_pemulihan_sebagian_membuat_urutan_berpengaruh(self):
        """Dgn recovery<1 urutan greedy tidak lagi otomatis optimal."""
        greedy = sorted(range(5), key=lambda k: opt.power(ENEMIES[k]))
        best = min(opt.evaluate_order(list(p), PLAYER, ENEMIES, recovery=0.75)
                    for p in itertools.permutations(range(5)))
        self.assertLess(best, opt.evaluate_order(greedy, PLAYER, ENEMIES, recovery=0.75))


class TestCSP(unittest.TestCase):
    def test_solusi_memenuhi_syarat_dan_all_different(self):
        for margin in (0.5, 0.8):
            order, _ = opt.backtracking_search(ENEMIES, PLAYER, margin=margin)
            self.assertIsNotNone(order)
            self.assertEqual(sorted(order), list(range(len(ENEMIES))))        # all-different
            table = opt.slot_power_table(PLAYER, len(ENEMIES))
            for slot, e in enumerate(order, start=1):                          # syarat stat per slot
                self.assertGreaterEqual(table[slot], opt.required_power(ENEMIES[e], margin) - 1e-9)

    def test_margin_terlalu_tinggi_tidak_punya_solusi(self):
        order, log = opt.backtracking_search(ENEMIES, PLAYER, margin=1.3)
        self.assertIsNone(order)
        self.assertEqual(log["nodes"], 0)

    def test_kunci_musuh_terbuka_setelah_menang(self):
        locked0 = [opt.is_locked(PLAYER, e) for e in ENEMIES]
        self.assertEqual(locked0, [False, False, False, True, True])
        s = opt.apply_reward(PLAYER)
        self.assertEqual([opt.is_locked(s, e) for e in ENEMIES], [False, False, False, False, True])
        s = opt.apply_reward(s)
        self.assertFalse(any(opt.is_locked(s, e) for e in ENEMIES))

    def test_recover_hp(self):
        self.assertIsNone(opt.recover_hp(20, 108, ratio=1.0))
        self.assertEqual(opt.recover_hp(20, 108, ratio=0.5), 64)
        self.assertLessEqual(opt.recover_hp(107, 108, ratio=0.5), 108)


if __name__ == "__main__":
    unittest.main()