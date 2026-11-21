# -*- coding: utf-8 -*-
"""Tes sungai.py (KB FOL/CNF, planner PDDL, MDP/MEU).  python -m unittest discover -s tests -v"""
import heapq
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import sungai as S  # noqa: E402

ROWS, COLS = 19, 26


def make_world(seed=4, tide_seed=1):
    g = [[S.GRASS] * COLS for _ in range(ROWS)]
    info = S.carve_river(g, random.Random(seed))
    return g, info, S.RiverWorld(g, seed=tide_seed)


def cells_of(g, tile):
    return [(r, c) for r in range(ROWS) for c in range(COLS) if g[r][c] == tile]


def nbrs(r, c):
    return [(r + dr, c + dc) for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
            if 0 <= r + dr < ROWS and 0 <= c + dc < COLS]


def dijkstra(world, start, goal):
    dist, pq = {start: 0.0}, [(0.0, start)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == goal:
            return d
        if d > dist[u]:
            continue
        for v in nbrs(*u):
            f = math.sqrt(2) if (v[0] != u[0] and v[1] != u[1]) else 1.0
            nd = d + f * world.cost(*v)
            if nd < dist.get(v, 1e9):
                dist[v] = nd
                heapq.heappush(pq, (nd, v))


class TestTileCostMatrix(unittest.TestCase):
    def test_matriks_biaya_statis(self):
        self.assertEqual(S.static_cost(S.GRASS), 1)
        self.assertEqual(S.static_cost(S.ROCK), 1)
        self.assertEqual(S.static_cost(S.TIDE, high_tide=True), 3)
        self.assertEqual(S.static_cost(S.TIDE, high_tide=False), 1)
        self.assertEqual(S.static_cost(S.DEEP), 5)
        self.assertEqual(S.static_cost(S.WOOD), 1)

    def test_sungai_organik_berkelok_dan_bisa_dilewati(self):
        for seed in range(12):
            g = [[S.GRASS] * COLS for _ in range(ROWS)]
            info = S.carve_river(g, random.Random(seed))
            band = [[c for c in range(COLS) if g[r][c] in S.RIVER_TILES] for r in range(ROWS)]
            self.assertTrue(all(band[r] for r in range(ROWS)))
            self.assertTrue(all(t not in (S.TREE, S.PROP) for row in g for t in row))
            self.assertGreaterEqual(len({min(b) for b in band}), 4)
            self.assertGreaterEqual(len({max(b) - min(b) for b in band}), 2)
            self.assertTrue(all(min(b) >= 5 for b in band))
            self.assertGreaterEqual(len(cells_of(g, S.WOOD)), 4)
            self.assertGreaterEqual(len(cells_of(g, S.TIDE)), 10)

    def test_jembatan_batu_bersambung_dari_tepi_ke_tepi(self):
        for seed in range(12):
            g = [[S.GRASS] * COLS for _ in range(ROWS)]
            info = S.carve_river(g, random.Random(seed))
            path = info["rock_path"]
            self.assertTrue(all(g[r][c] == S.ROCK for r, c in path))
            for (r1, c1), (r2, c2) in zip(path, path[1:]):
                self.assertLessEqual(max(abs(r1 - r2), abs(c1 - c2)), 1)
            r0, c0 = path[0]
            r1, c1 = path[-1]
            self.assertNotIn(g[r0][c0 - 1], S.RIVER_TILES)
            self.assertTrue(all(g[rr][c1 + 1] not in S.RIVER_TILES
                                for rr in (r1 - 1, r1, r1 + 1) if 0 <= rr < ROWS))

    def test_style_kedalaman_dan_garis_pantai(self):
        g = [[S.GRASS] * COLS for _ in range(ROWS)]
        S.carve_river(g, random.Random(3))
        style = S.build_style(g)
        river_cells = cells_of(g, S.TIDE) + cells_of(g, S.DEEP) + cells_of(g, S.ROCK) + cells_of(g, S.WOOD)
        self.assertEqual(set(style), set(river_cells))
        self.assertTrue(any(v["depth"] == 0 for v in style.values()))
        self.assertTrue(any(v["depth"] >= 2 for v in style.values()))
        self.assertTrue(any(any(v["land"]) for v in style.values()))


class TestKnowledgeBase(unittest.TestCase):
    def test_ask_biaya_awal(self):
        g, info, w = make_world()
        deep, rock, wood, tide = (cells_of(g, k)[0] for k in (S.DEEP, S.ROCK, S.WOOD, S.TIDE))
        self.assertEqual(w.kb.ask_cost(*deep, 0), 5)
        self.assertEqual(w.kb.ask_cost(*rock, 0), 1)
        self.assertEqual(w.kb.ask_cost(*wood, 0), 1)
        self.assertEqual(w.kb.ask_cost(*tide, 0), 1)
        self.assertEqual(w.kb.ask(*deep, 0), (False, 5))
        self.assertEqual(w.kb.ask(*tide, 0), (True, 1))
        self.assertEqual(w.kb.ask(0, 0, 0), (True, 1))

    def test_R1_pasang_tinggi_membuat_biaya_3(self):
        g, info, w = make_world()
        tide = cells_of(g, S.TIDE)[0]
        w.kb.tell(("tide", 5, True))
        self.assertEqual(w.kb.ask_cost(*tide, 5), 3)
        self.assertEqual(w.kb.ask_cost(*tide, 4), 1)
        self.assertEqual(w.kb.ask_cost(*tide, 5, assume_high=False), 1)

    def test_R2_R3_kayu_diinjak_tenggelam_di_t_plus_1(self):
        g, info, w = make_world()
        x, y = cells_of(g, S.WOOD)[0]
        self.assertEqual(w.kb.wood_state(x, y, 0), "floating")
        self.assertTrue(w.step_on(x, y))                        # TELL SteppedOn(x,y,0)
        self.assertEqual(w.kb.ask_cost(x, y, 0), 1)             # masih 1 pada waktu injak
        w.advance()
        self.assertEqual(w.kb.wood_state(x, y, 1), "sunk")
        self.assertEqual(w.kb.ask_cost(x, y, 1), 5)             # t+1 => 5
        self.assertFalse(w.safe(x, y))
        for _ in range(5):                                      # tetap tenggelam (aksioma bingkai R4)
            w.advance()
        self.assertEqual(w.kb.wood_state(x, y, w.t), "sunk")

    def test_kayu_tidak_diinjak_tetap_mengapung(self):
        g, info, w = make_world()
        for _ in range(8):
            w.advance()
        x, y = cells_of(g, S.WOOD)[-1]
        self.assertEqual(w.kb.wood_state(x, y, w.t), "floating")

    def test_perubahan_biaya_menaikkan_version(self):
        g, info, w = make_world()
        v0 = w.version
        w.step_on(*cells_of(g, S.WOOD)[0])
        self.assertGreater(w.version, v0)

    def test_aturan_dapat_ditampilkan_sebagai_cnf(self):
        cnf = S.RiverKB().rules_text("cnf")
        self.assertIn("R1  ¬HighTide(t) ∨ ¬TidalArea(x,y) ∨ TileCost(x,y,t,3)", cnf)
        self.assertTrue(any("IsWoodSunk(x,y,t+1)" in r and r.startswith("R2") for r in cnf))

    def test_pasang_markov_mendekati_distribusi_stasioner(self):
        g, info, w = make_world(tide_seed=7)
        highs = 0
        for _ in range(4000):
            w.advance()
            highs += w.high
        expected = S.TIDE_P_UP / (S.TIDE_P_UP + S.TIDE_P_DOWN)
        self.assertAlmostEqual(highs / 4000, expected, delta=0.04)


class TestPDDLPlanner(unittest.TestCase):
    def test_biaya_rencana_sama_dengan_dijkstra(self):
        g, info, w = make_world()
        start, goal = (info["wood_rows"][0], 3), (info["wood_rows"][0], 22)
        res = S.plan_pddl(w, nbrs, start, goal, w.cost)
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(res["cost"], dijkstra(w, start, goal), places=6)
        self.assertEqual(res["path"][0], start)
        self.assertEqual(res["path"][-1], goal)

    def test_rencana_memakai_STEP_ON_WOOD_dan_efek_strips(self):
        g, info, w = make_world()
        res = S.plan_pddl(w, nbrs, (info["wood_rows"][0], 3), (info["wood_rows"][0], 22), w.cost)
        steps = [a for a in res["plan"] if a.name == "STEP_ON_WOOD"]
        self.assertGreaterEqual(len(steps), 1)
        a = steps[0]
        self.assertEqual(a.delete, frozenset({("at", "ag", a.frm), ("wood-floating", a.to)}))
        self.assertEqual(a.add, frozenset({("at", "ag", a.to), ("wood-sunk", a.to)}))
        self.assertEqual(a.pre, frozenset({("at", "ag", a.frm), ("wood-floating", a.to)}))

    def test_replanning_setelah_kayu_tenggelam(self):
        g, info, w = make_world()
        start, goal = (info["wood_rows"][0], 3), (info["wood_rows"][0], 22)
        before = S.plan_pddl(w, nbrs, start, goal, w.cost)["cost"]
        for x, y in [p for p in cells_of(g, S.WOOD) if p[0] == info["wood_rows"][0]]:
            w.step_on(x, y)
        w.advance()
        after = S.plan_pddl(w, nbrs, start, goal, w.cost)
        self.assertTrue(after["ok"])
        self.assertGreater(after["cost"], before - 1e-9)          # tidak mungkin lebih murah
        self.assertAlmostEqual(after["cost"], dijkstra(w, start, goal), places=6)

    def test_domain_dan_problem_pddl(self):
        g, info, w = make_world()
        self.assertIn("(:action STEP_ON_WOOD", S.PDDL_DOMAIN)
        self.assertIn("(not (wood-floating ?to)) (wood-sunk ?to)", S.PDDL_DOMAIN)
        prob = S.to_pddl_problem(w, (9, 3), (9, 20))
        self.assertIn("(wood-floating", prob)
        self.assertIn("(:goal (at ag c9_20))", prob)


class TestMDP(unittest.TestCase):
    def setUp(self):
        self.g, self.info, self.w = make_world()
        cells = [(r, c) for r in range(ROWS) for c in range(COLS)]
        self.goal = (ROWS // 2, 22)
        self.mdp = S.RiverMDP(cells, nbrs, self.w.cost_hyp, self.goal).solve()

    def test_value_iteration_konvergen_dan_kebijakan_mencapai_tujuan(self):
        self.assertLess(self.mdp.iterations, 300)
        for high in (False, True):
            path, _ = self.mdp.rollout((ROWS // 2, 3), high)
            self.assertEqual(path[-1], self.goal)

    def test_nilai_lebih_tinggi_makin_dekat_tujuan(self):
        v_dekat = self.mdp.V[False][self.mdp.idx[(ROWS // 2, 21)]]
        v_jauh = self.mdp.V[False][self.mdp.idx[(ROWS // 2, 5)]]
        self.assertGreater(v_dekat, v_jauh)

    def test_pasang_tinggi_tidak_menaikkan_nilai(self):
        i = self.mdp.idx[(ROWS // 2, 5)]
        self.assertLessEqual(self.mdp.V[True][i], self.mdp.V[False][i] + 1e-9)

    def test_aksi_meu_menuju_utilitas_harapan_terbesar(self):
        cell = (ROWS // 2, 8)
        qs = self.mdp.q_values(cell, False)
        self.assertEqual(self.mdp.best_action(cell, False), max(qs)[1])


if __name__ == "__main__":
    unittest.main()
