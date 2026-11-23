# -*- coding: utf-8 -*-
"""Tes SISTEM TURN & kayu muncul lagi di level game (butuh pygame; dilewati bila tidak ada).
python -m unittest discover -s tests -v"""
import os
import random
import sys
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

try:
    import pygame  # noqa: F401
    import game
    import sungai
    HAVE = True
except Exception:          # pragma: no cover
    HAVE = False


@unittest.skipUnless(HAVE, "pygame tidak tersedia")
class TestTurnSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        random.seed(5)
        cls.g = game.Game()

    def fresh(self, seed=5):
        random.seed(seed)
        g = self.g
        g.new_map()
        g.respawn()
        g.in_combat = False
        for e in g.enemies:
            e["alive"] = False          # tanpa musuh: uji murni biaya turn & waktu sungai
        return g

    def place_next_to(self, g, tile):
        """Letakkan pemain di sebelah (kiri) sebuah tile jenis `tile`; return posisi tile itu."""
        for r in range(game.ROWS):
            for c in range(1, game.COLS):
                if g.grid[r][c] == tile and game.is_passable(g.grid, r, c - 1):
                    g.player = (r, c - 1)
                    return (r, c)
        self.fail("tile tidak ditemukan")

    def test_tidak_ada_mode_real_time(self):
        self.assertFalse(hasattr(self.g, "turn_based"))
        self.assertFalse(hasattr(self.g, "_poll_continuous_movement"))
        self.assertFalse(hasattr(self.g, "_poll_enemy_chase"))

    def test_langkah_di_rumput_memakan_1_turn(self):
        g = self.fresh()
        r, c = g.player
        nxt = next((r + dr, c + dc) for dr, dc in ((0, 1), (1, 0), (-1, 0), (0, -1), (1, 1), (-1, 1))
                   if game.in_bounds(r + dr, c + dc) and g.grid[r + dr][c + dc] == game.GRASS)
        t0 = g.river.t
        g.try_move_player(*nxt)
        self.assertEqual(g.river.t - t0, 1)

    def test_biaya_turn_sama_dengan_biaya_tile(self):
        g = self.fresh()
        for tile in (game.DEEP, game.BUSH, game.ROCK, game.WOOD):
            g = self.fresh()
            cell = self.place_next_to(g, tile) if any(tile in row for row in g.grid) else None
            if cell is None:
                continue
            expected = sungai.turns_for_cost(game.terrain_cost(g.grid, *cell))
            t0 = g.river.t
            g.try_move_player(*cell)
            self.assertEqual(g.river.t - t0, expected, f"tile {tile}")

    def test_sungai_dalam_5_turn_dan_kayu_1_turn(self):
        g = self.fresh()
        cell = self.place_next_to(g, game.DEEP)
        t0 = g.river.t
        g.try_move_player(*cell)
        self.assertEqual(g.river.t - t0, 5)
        g = self.fresh()
        cell = self.place_next_to(g, game.WOOD)
        t0 = g.river.t
        g.try_move_player(*cell)
        self.assertEqual(g.river.t - t0, 1)

    def test_space_melewati_1_turn(self):
        g = self.fresh()
        t0 = g.river.t
        g.handle_key(pygame.K_SPACE)
        self.assertEqual(g.river.t - t0, 1)

    def test_tombol_T_tidak_lagi_mengganti_mode(self):
        g = self.fresh()
        t0 = g.river.t
        g.handle_key(pygame.K_t)
        self.assertEqual(g.river.t, t0)

    def test_musuh_ikut_melangkah_tiap_turn_dan_menunggu_sesuai_biaya(self):
        g = self.fresh()
        e = g.enemies[0]
        e["alive"] = True
        r, c = g.player
        e["pos"] = (r, min(c + 6, game.COLS - 1))
        start = e["pos"]
        g._pass_turns(3)
        self.assertNotEqual(e["pos"], start)                 # bergerak mendekat
        # musuh yang baru masuk tile berbiaya 5 harus diam 4 turn berikutnya
        e["wait"] = 0
        e["pos"] = start
        deep = next((p for p in [(rr, cc) for rr in range(game.ROWS) for cc in range(game.COLS)] if g.grid[p[0]][p[1]] == game.DEEP))
        e["pos"] = deep
        e["wait"] = g.turn_cost(*deep) - 1
        before = e["pos"]
        g._pass_turns(e["wait"])
        self.assertEqual(e["pos"], before)

    def test_kayu_diinjak_tenggelam_lalu_muncul_lagi_setelah_cost_turn(self):
        g = self.fresh()
        cell = self.place_next_to(g, game.WOOD)
        w = g.river
        g.try_move_player(*cell)                             # 1 turn: kayu mulai tenggelam di turn berikutnya
        self.assertEqual(w.kb.wood_state(*cell), "sunk")
        self.assertEqual(w.kb.sunk_remaining(*cell), sungai.WOOD_RESPAWN_TURNS)
        g.player = (cell[0], cell[1] - 1)                    # menjauh agar tidak dihitung ulang
        floats_at = None
        for i in range(sungai.WOOD_RESPAWN_TURNS + 2):
            g._pass_turns(1)
            if w.kb.wood_state(*cell) == "floating":
                floats_at = i + 1
                break
        self.assertIsNotNone(floats_at)
        self.assertEqual(floats_at, sungai.WOOD_RESPAWN_TURNS)       # tenggelam persis 5 turn, lalu mengapung
        self.assertEqual(game.terrain_cost(g.grid, *cell), 1)         # biaya kembali 1

    def test_penyeberangan_kayu_dua_kali_mahal_lalu_murah_lagi(self):
        g = self.fresh()
        cell = self.place_next_to(g, game.WOOD)
        g.try_move_player(*cell)
        self.assertEqual(game.terrain_cost(g.grid, *cell), 5)         # tenggelam: mahal
        g._pass_turns(sungai.WOOD_RESPAWN_TURNS)
        self.assertEqual(game.terrain_cost(g.grid, *cell), 1)         # muncul lagi: murah


if __name__ == "__main__":
    unittest.main()
