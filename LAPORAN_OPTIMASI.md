# Laporan: Banyak Musuh — Local Search & CSP

Modul: `optimasi.py`. 5 musuh beda "karakter" (stat berbeda) spawn sekaligus
di peta (`game.py`, lihat `spawn_enemies()`). Pemain harus mengalahkan
mereka — menang = reward (semua stat naik). Dua pendekatan AI buat **memilih
urutan** menghadapi mereka:

- **Local Search & Optimization** — cari urutan **TERBAIK** (hemat HP paling
  banyak sepanjang rangkaian). Dipakai Mode Otomatis (tombol **O**).
- **CSP** — cari urutan yang **SAH** (bukan optimal, cukup memenuhi syarat
  "stat pemain minimum sebelum boleh lawan musuh itu").

## 1. Roster & Reward

| Musuh | Max HP | Damage | Peluang kena |
|---|---|---|---|
| Pemburu Liar | 60 | 8–18 | 65%–80% |
| Penjaga Hutan | 90 | 10–22 | 68%–82% |
| Pendekar Bayangan | 115 | 12–26 | 70%–85% |
| Ksatria Besi | 140 | 14–28 | 72%–86% |
| Naga Kecil | 170 | 16–32 | 75%–88% |

Reward tiap menang (flat, sama utk musuh manapun): `+8 max_hp, +2 atk_min/atk_max,
+0.02 hit_base, +0.01 hit_cap`. Pemain **pulih penuh** (full HP) sebelum tiap
duel baru dimulai — representasi "istirahat" antar pertarungan. Ini penting:
tanpa ini, HP tersisa dari duel sebelumnya akan mendominasi hasil dan urutan
jadi tidak terlalu berpengaruh (sudah saya coba & buktikan sendiri saat
mengembangkan — lihat catatan desain di kode).

## 2. Local Search & Optimization

**Ruang pencarian**: satu permutasi urutan ke-5 musuh.
**Neighbor**: tukar (swap) posisi 2 musuh.
**Objective (minimisasi)**: `evaluate_order()` = total HP yang terkuras
sepanjang seluruh rangkaian duel, diprediksi deterministik lewat
`predict_duel()` (nilai-harapan, bukan RNG — supaya bisa dievaluasi ribuan
kali dengan cepat tanpa simulasi acak berulang).

**Algoritma**: Hill Climbing (steepest-ascent per sweep + random restart) dan
Simulated Annealing (pembanding, bisa terima solusi lebih buruk dgn peluang
`exp(-Δ/T)`, T menurun tiap iterasi).

### Hasil nyata (seed=3)

| Algoritma | Cost | Waktu | Urutan ditemukan |
|---|---|---|---|
| Hill Climbing (12 restart) | **1021.0** | 57.0 ms | Pemburu→Penjaga→Pendekar→Naga→Ksatria |
| Simulated Annealing (400 iter) | **1021.0** | 81.7 ms | Pemburu→Penjaga→Naga→Pendekar→Ksatria |
| **Brute-force (semua 120 permutasi)** | **1021.0** | — | (sama, cost minimum) |

**Kedua local search menemukan hasil yang terbukti OPTIMAL** (diverifikasi lewat
brute-force atas seluruh 5!=120 kemungkinan urutan — langka bisa diverifikasi
selengkap ini, N=5 cukup kecil utk brute-force).

Sebagai perbandingan, 1 dari 12 restart Hill Climbing (tanpa random-restart)
akan **kejebak local optimum** (cost lebih tinggi dari 1021) — bukti nyata
kenapa random-restart penting. Urutan "mudah→susah" (cost 1021) hampir **2×
lebih hemat** dibanding urutan "susah→mudah" (cost ≈2048, dicoba manual) —
konfirmasi bahwa strategi intuitif (kalahkan yang lemah dulu biar stat naik
sebelum hadapi yang kuat) memang terbukti optimal di sini, bukan cuma dugaan.

## 3. CSP — Backtracking + MRV + LCV + AC-3

**Variables**: 5 musuh. **Domain(musuh)**: slot urutan {1..5} yang kekuatan
pemain di slot itu (`slot_power_table`, dihitung dari reward kumulatif —
sama utk semua urutan krn reward flat) cukup (`required_power = power(musuh) × margin`).
**Constraint**: all-different (tiap slot cuma 1 musuh) — binary antar SETIAP
pasang variabel, diselesaikan AC-3.

### Hasil nyata: feasible vs infeasible per margin

| Margin | Hasil | Node dikunjungi | Backtrack | Revisi AC-3 |
|---|---|---|---|---|
| 0.5 (longgar) | Solusi ditemukan | 6 | 0 | 0 |
| 0.8 (default) | Solusi ditemukan | 6 | 0 | 0 |
| 1.0 | **Tidak ada solusi** | 0 | 0 | 0 |
| 1.3 | **Tidak ada solusi** | 0 | 0 | **2** |
| 1.6 | **Tidak ada solusi** | 0 | 0 | 1 |

**Kesimpulan menarik**: di margin 1.0+, soal ini sudah **tidak feasible SEJAK
AWAL** — AC-3/filter domain awal langsung mendeteksinya SEBELUM backtracking
sempat jalan satu node pun (`nodes=0`). Ini pas sekali menunjukkan nilai AC-3:
memangkas ruang pencarian di depan, bukan menunggu backtracking gagal berulang
kali buat ketahuan tidak ada solusi.

Catatan: CSP (margin 0.8) menemukan urutan **Pemburu→Ksatria→Penjaga→Naga→Pendekar**
— SAH (semua syarat stat minimum terpenuhi) tapi **BUKAN** urutan optimal
Local Search (1021). Ini memang disengaja/sesuai definisi masing-masing:
CSP cuma menjamin *kelayakan*, bukan *keoptimalan* — Local Search itulah yang
mengejar hasil terbaik.

## 4. Integrasi ke Game

- Musuh digambar sbg lingkaran berwarna + nama (`_draw_enemy_marker_unit`), beda
  warna tiap karakter.
- Jalan ke petak musuh (manual atau Mode Otomatis) memicu pertarungan lewat
  `start_multi_combat()` — pakai mesin pertarungan yg SAMA persis (minimax/
  alpha-beta/dst, debug overlay, delay giliran) dgn stat musuh itu di-override
  sementara (`combat.PLAYER_STATS_OVERRIDE` / `NPC_STATS_OVERRIDE`).
- Menang: musuh hilang dari peta, stat pemain naik (reward). Kalah/seri:
  pemain mundur ke titik spawn (supaya tidak ke-trigger ulang terus-menerus).
- **Mode Otomatis** (tombol **O**): hitung urutan via Hill Climbing atas musuh
  yang masih hidup, lalu pemain auto-jalan (pakai A*/UCS yang SAMA dgn sistem
  kejar-kejaran) ke musuh berikutnya sesuai urutan itu, bertarung otomatis,
  lanjut ke musuh berikutnya. Menekan WASD kapan saja membatalkan mode ini.
