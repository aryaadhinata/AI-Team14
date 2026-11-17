# Laporan: Banyak Musuh — Local Search & CSP
 
Modul: `src/optimasi.py`. 5 musuh beda "karakter" (stat berbeda) spawn sekaligus di peta
(`game.py`, `spawn_enemies()`). Pemain mengalahkan mereka; menang = reward (semua stat naik).
Dua pendekatan AI dipakai untuk **urutan** menghadapi mereka:
 
- **Local Search & Optimization** — mencari urutan **TERBAIK** (biaya terendah). Hasilnya
  ditampilkan lewat tombol **P**, dibanding greedy dan brute-force.
- **CSP** — mencari urutan yang **SAH** (syarat "stat pemain minimum sebelum boleh melawan musuh").
  Syarat yang sama dipakai game untuk **mengunci** musuh (§3.3).
## 1. Roster & Reward
 
| Musuh | Max HP | Damage | Peluang kena | Depth | Mistake | Gaya (eval) | Power |
|---|---|---|---|---|---|---|---|
| Pemburu Liar | 60 | 12–27 | 60%–74% | 2 | 0.35 | aggressive | 190.6 |
| Penjaga Hutan | 85 | 13–29 | 62%–76% | 2 | 0.25 | defensive | 229.9 |
| Pendekar Bayangan | 110 | 15–32 | 64%–78% | 3 | 0.18 | hp_diff | 276.9 |
| Ksatria Besi | 135 | 14–32 | 66%–80% | 3 | 0.10 | stance_aware | 302.9 |
| Naga Kecil | 160 | 16–35 | 68%–82% | 4 | 0.04 | aggressive | 351.2 |
 
Pemain awal: 100 HP, damage 10–25, peluang kena 70%–85% (power 235.6). Rumus
`power = max_hp + rata2_damage × rata2_peluang_kena × 10`.
 
Reward tiap menang (flat): `+8 max_hp, +2 atk_min/atk_max, +0.02 hit_base, +0.01 hit_cap`.
 
**Pemulihan HP antar duel** diatur `POST_FIGHT_RECOVERY` (`optimasi.py`): bagian HP yang hilang
yang dipulihkan setelah menang. Default **1.0** = HP pulih penuh (urutan hanya soal kesiapan stat).
Nilai < 1 membawa sisa HP ke duel berikutnya; lihat §2.3 untuk dampaknya.
 
## 2. Local Search & Optimization
 
**Ruang pencarian**: permutasi urutan ke-5 musuh. **Neighbor**: tukar 2 posisi.
**Objective (minimisasi)**: `evaluate_order()` — simulasi rangkaian duel secara deterministik lewat
`predict_duel()` (nilai-harapan, kedua pihak selalu Attack):
- duel **dimenangkan** → biaya += HP yang terkuras; stat naik (reward); HP pulih sesuai `POST_FIGHT_RECOVERY`;
- duel **diprediksi kalah** → biaya += **500 + HP musuh** (penalti); stat tidak naik; pemain pulih penuh.
**Algoritma**: Hill Climbing (steepest-ascent per sweep + random restart) dan Simulated Annealing
(menerima solusi lebih buruk dengan peluang `exp(-Δ/T)`).
 
### 2.1 Hasil nyata (seed=3, `POST_FIGHT_RECOVERY=1.0`)
 
| Algoritma | Biaya | Menang (prediksi) | Waktu* | Urutan ditemukan |
|---|---|---|---|---|
| Hill Climbing (12 restart) | **1039.8** | 4/5 | ±65 ms | Pemburu→Penjaga→Pendekar→Naga→Ksatria |
| Simulated Annealing (400 iter) | **1039.8** | 4/5 | ±90 ms | Pemburu→Penjaga→Naga→Pendekar→Ksatria |
| Brute-force (120 permutasi) | **1039.8** | 4/5 | ±25 ms | Pemburu→Penjaga→Pendekar→Ksatria→Naga |
| Greedy (`power` terkecil dulu) | **1039.8** | 4/5 | — | Pemburu→Penjaga→Pendekar→Ksatria→Naga |
 
\*Waktu bergantung mesin. Beberapa urutan berbeda punya biaya sama, jadi urutan yang dikembalikan tiap
algoritma boleh berbeda; biayanya tetap optimal. Satu dari 12 restart Hill Climbing berhenti di local
optimum (biaya 1553.9) — bukti kenapa random-restart penting. Urutan "sulit→mudah" berbiaya **2060.5**
(±2× lebih boros).
 
### 2.2 Cara membaca "biaya 1039.8" (penting)
 
Rincian untuk urutan Pemburu→Penjaga→Pendekar→Ksatria→Naga:
 
| Duel | HP maks pemain | Prediksi | Biaya |
|---|---|---|---|
| Pemburu Liar | 100 | menang, sisa 32.6 | 67.4 |
| Penjaga Hutan | 108 | menang, sisa 20.9 | 87.1 |
| Pendekar Bayangan | 116 | menang, sisa 11.6 | 104.4 |
| Ksatria Besi | 124 | menang, sisa 3.1 | 120.9 |
| Naga Kecil | 132 | **kalah** (penalti 500+160) | 660.0 |
| **Total** | | 4 menang, 1 kalah | **1039.8** |
 
Sekitar **63% biaya adalah penalti** untuk satu duel yang diprediksi kalah. Prediksi memakai kebijakan
"selalu Attack" sehingga **pesimis**: pemain sungguhan bisa memakai Heal/Parry. Karena itu panel P
menampilkan juga jumlah duel yang diprediksi menang, dan angka biaya dipakai untuk *membandingkan
urutan*, bukan sebagai jumlah HP sebenarnya.
 
### 2.3 Apakah urutan benar-benar berpengaruh? (`POST_FIGHT_RECOVERY`)
 
| Pemulihan | Biaya terbaik (menang) | Contoh urutan terbaik | Biaya greedy (menang) | Greedy optimal? |
|---|---|---|---|---|
| 1.0 (penuh) | 1039.8 (4) | Pemburu→Penjaga→Pendekar→Ksatria→Naga | 1039.8 (4) | **Ya** |
| 0.75 | 1541.9 (3) | Pemburu→Penjaga→Ksatria→Pendekar→Naga | 2047.5 (2) | Tidak |
| 0.5 | 1545.5 (3) | Penjaga→Pemburu→Ksatria→Pendekar→Naga | 2557.4 (1) | Tidak |
| 0.25 | 1553.9 (3) | Pemburu→Ksatria→Penjaga→Naga→Pendekar | 2557.4 (1) | Tidak |
 
Dengan HP pulih penuh, greedy sudah optimal sehingga Hill Climbing/SA tidak menemukan apa pun yang
greedy tidak temukan (ruang pencariannya juga hanya 120 permutasi, jadi brute-force cukup). Begitu
HP terbawa antar duel, **greedy tidak lagi optimal** dan Local Search menjadi bermakna. Default tetap
1.0 karena dampaknya ke kesulitan game belum diuji dengan pemain sungguhan (prediksi pesimis; pada 0.5
hanya 3 dari 5 musuh yang diprediksi bisa dikalahkan).
 
## 3. CSP — Backtracking + MRV + LCV + AC-3
 
**Variables**: 5 musuh. **Domain(musuh)**: slot {1..5} yang kekuatan pemain di slot itu
(`slot_power_table`, dari reward kumulatif) ≥ `required_power = power(musuh) × margin`.
**Constraint**: all-different, diselesaikan AC-3.
 
### 3.1 Hasil nyata per margin
 
| Margin | Hasil | Node | Backtrack | Revisi AC-3 |
|---|---|---|---|---|
| 0.5 | Solusi ditemukan | 6 | 0 | 0 |
| 0.8 (default game) | Solusi ditemukan | 6 | 0 | 0 |
| 1.0 | **Tidak ada solusi** | 0 | 0 | 0 |
| 1.3 | **Tidak ada solusi** | 0 | 0 | 0 |
| 1.6 | **Tidak ada solusi** | 0 | 0 | 0 |
 
Pada margin ≥ 1.0 soal sudah tidak feasible sejak awal: filter domain awal membuat domain satu musuh
kosong, sehingga ditolak **sebelum backtracking menjalankan satu node pun** (`nodes=0`).
 
### 3.2 SAH bukan berarti optimal
 
Margin 0.8 menghasilkan urutan **Pemburu→Ksatria→Naga→Penjaga→Pendekar** dengan biaya **1553.9**
(menang 3/5), lebih boros dari optimum 1039.8. CSP hanya menjamin *kelayakan*; Local Search yang
mengejar *kualitas*.
 
### 3.3 CSP dipakai di gameplay (kunci musuh)
 
`optimasi.LOCK_MARGIN = 0.8`: musuh **terkunci** selama `power(pemain) < 0.8 × power(musuh)`.
 
| Kondisi pemain | Power | Musuh terkunci |
|---|---|---|
| Awal | 235.6 | Ksatria Besi (butuh 242.3), Naga Kecil (butuh 281.0) |
| Setelah 1 menang | 262.1 | Naga Kecil |
| Setelah 2 menang | 289.1 | — |
 
Musuh terkunci: diam (tidak mengejar), tidak dipilih Mode Otomatis, dan kontak dengannya tidak memulai
duel (muncul pesan "TERKUNCI"); label di peta diberi `[terkunci]`. Tombol **C** memakai margin
`LOCK_MARGIN` pada tekanan pertama.
 
## 4. Integrasi ke Game
 
- Kontak dengan musuh yang tidak terkunci memicu duel lewat `start_multi_combat()` dengan mesin
  pertarungan yang sama (minimax/alpha-beta/dst), stat musuh dipasang sementara lewat
  `combat.PLAYER_STATS_OVERRIDE`/`NPC_STATS_OVERRIDE`.
- Menang: musuh hilang, stat naik, HP awal duel berikutnya dihitung `recover_hp()` (penuh bila
  `POST_FIGHT_RECOVERY=1.0`). Kalah/seri: pemain mundur ke spawn dengan HP penuh dan musuh itu
  dipindah ke posisi acak baru.
- **Mode Otomatis (O)**: pemain berjalan (A*/UCS) ke musuh **tidak terkunci** dengan `power` terkecil,
  dihitung ulang tiap langkah dan setelah tiap kemenangan (greedy). **Rem**: bila duel melawan musuh
  termudah itu diprediksi KALAH (`predict_duel`), mode berhenti dan menampilkan pesan; menekan **O**
  lagi melanjutkan dengan menyerang. Menekan WASD membatalkan mode ini.
- **Tombol P**: Hill Climbing, SA, brute-force, dan greedy pada musuh yang masih hidup, lengkap dengan
  biaya, jumlah menang, dan waktu. **Tombol C**: CSP dengan margin berganti tiap tekan. **X** menutup panel.
- `predict_duel()` memasang stat lewat `combat.stat_overrides(...)` (context manager) sehingga stat lama
  selalu dipulihkan walau terjadi error.
## 5. Pengujian
 
`python -m unittest discover -s tests -v` (12 tes): Alpha-Beta bernilai sama dengan Minimax; biaya
greedy default 1039.8 (regresi); Hill Climbing menghasilkan local optimum; Hill Climbing/SA tidak
pernah lebih baik dari brute-force; solusi CSP memenuhi syarat stat dan all-different; margin 1.3 tidak
punya solusi dengan `nodes=0`; kunci musuh terbuka setelah menang; `predict_duel`/`stat_overrides` tidak
meninggalkan stat nyasar; pada pemulihan 0.75 greedy tidak lagi optimal.
 