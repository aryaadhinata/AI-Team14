# AI-Team14 — Kejar-Kejaran di Desa

Game 2D berbasis **pygame** untuk tugas mata kuliah Kecerdasan Buatan. Pemain menjelajahi peta desa yang dibuat acak, melewati sungai dinamis, lalu mengalahkan 5 musuh dengan karakter berbeda. Di balik gameplay-nya dipakai berbagai teknik AI:

| Topik | Teknik | Modul |
|---|---|---|
| Pathfinding | A\* (4 heuristik) dan UCS | `game.py` |
| Pertarungan adversarial | Minimax, Alpha-Beta, Early Stop, Expectimax | `pertarungan.py` |
| Local Search & Optimization | Hill Climbing (random restart), Simulated Annealing | `optimasi.py` |
| CSP | Backtracking + MRV + LCV + AC-3 | `optimasi.py` |
| Representasi pengetahuan | Knowledge Base FOL/CNF dengan TELL/ASK | `sungai.py` |
| Perencanaan | PDDL (A\* atas ruang state STRIPS) | `sungai.py` |
| Keputusan di bawah ketidakpastian | MDP / MEU (value iteration) | `sungai.py` |

## Daftar Isi

1. [Menjalankan](#menjalankan)
2. [Cara Bermain](#cara-bermain)
3. [Kontrol](#kontrol)
4. [Fitur](#fitur)
5. [Detail Modul AI](#detail-modul-ai)
6. [Struktur Repo](#struktur-repo)
7. [Tes dan Eksperimen](#tes-dan-eksperimen)
8. [Laporan](#laporan)
9. [Anggota](#anggota)

## Menjalankan

Kebutuhan: Python 3 dan pygame.

```bash
pip install pygame        # atau pygame-ce jika pygame belum mendukung versi Python Anda
python src/game.py        # dari root repo (atau: cd src && python game.py)
```

Folder `src/assets/` harus tetap berada di samping `src/game.py`.

## Cara Bermain

1. Gerakkan pemain dengan WASD/panah atau klik kiri pada petak yang bisa dilewati.
2. Setiap langkah memakan **turn** sebesar biaya petak yang dimasuki. Selama turn berjalan, semua musuh ikut melangkah, pasang sungai berganti, dan kayu yang tenggelam muncul lagi.
3. Bila pemain bertemu musuh yang **tidak terkunci**, terjadi duel bergiliran. Pilih aksi dengan tombol **1–4**: Attack, Defend, Heal, Parry.
4. Menang berarti musuh hilang dan stat pemain naik. Kalah atau seri berarti pemain kembali ke titik spawn dengan HP penuh, dan musuh itu dipindah ke posisi acak.
5. Musuh yang terlalu kuat **terkunci** sampai stat pemain cukup (lihat [CSP di gameplay](#csp-di-gameplay-kunci-musuh)).
6. Mau melihat AI bekerja tanpa main sendiri? Tekan **O** untuk Mode Otomatis, atau **E** untuk debug pathfinding.

## Kontrol

**Saat menjelajah**

| Tombol | Fungsi |
|---|---|
| WASD / panah | Gerak (membatalkan Mode Otomatis) |
| Klik kiri | Pindah ke petak yang diklik |
| SPACE | Lewati 1 turn |
| N | Peta baru |
| R | Reset posisi (respawn) |
| F | Layar penuh / jendela |
| ESC | Keluar |

**Pathfinding dan debug**

| Tombol | Fungsi |
|---|---|
| 1 / 2 | Algoritma A\* / UCS |
| H | Ganti heuristik A\* (manhattan, euclidean, chebyshev, octile) |
| G | Nyala/mati gerak diagonal (8 arah) |
| E | Mode debug: tampilkan node yang dieksplorasi dan jalur pemain → musuh |
| TAB | Pilih target debug: semua musuh, lalu musuh 1, 2, dst. (tiap musuh beda warna) |
| L | Ganti angka di petak saat debug (urutan / g / h / f / panah / mati) |

**Panel AI**

| Tombol | Fungsi |
|---|---|
| O | Mode Otomatis: pemain mengejar musuh tidak terkunci yang paling mudah |
| P | Panel Local Search: Hill Climbing, SA, brute-force, dan greedy |
| C | Panel CSP (tekan lagi untuk ganti margin) |
| K | Panel KB sungai: aturan FOL/CNF dan hasil ASK |
| J | Panel rencana: PDDL vs A\* vs MEU ke musuh target |
| U | Ganti planner Mode Otomatis (PDDL → A\* → MEU) |
| X | Tutup panel hasil P / C |

**Saat duel:** **1** Attack · **2** Defend · **3** Heal · **4** Parry · **ESC** keluar. Tombol lain diabaikan selama duel.

> Tombol **T** (mode real-time) sudah tidak dipakai. Sistem turn adalah satu-satunya sistem waktu.

## Fitur

- **Peta acak** dengan pohon, semak, batu, dan sungai berkelok. Semua petak tetap bisa dilewati, jadi peta tidak pernah terputus.
- **Sistem turn:** masuk petak berbiaya *c* memakan *c* turn. Musuh tunduk pada aturan yang sama, jadi menyeberangi air dalam juga membuat musuh lambat.
- **Pathfinding A\*/UCS** untuk NPC dan musuh pengejar, dengan overlay debug.
- **Pertarungan bergiliran** dengan 4 aksi dan NPC yang memilih aksi lewat algoritma adversarial.
- **5 musuh** dengan stat dan gaya bertarung berbeda. Menang berarti stat pemain naik.
- **CSP di gameplay:** musuh terkunci selama power pemain masih terlalu rendah.
- **Local Search:** tombol P membandingkan Hill Climbing, Simulated Annealing, brute-force, dan greedy.
- **Sungai dinamis** dengan KB FOL/CNF, perencana PDDL, dan MDP/MEU.
- **Mode Otomatis (O):** pemain mengejar musuh tidak terkunci yang paling mudah, dan berhenti bila duel diprediksi kalah.

## Detail Modul AI

### Biaya petak dan sistem turn

| Petak | Biaya (= jumlah turn) |
|---|---|
| Rumput / batu jembatan | 1 |
| Semak | 3 |
| Area pasang (`HighTide_Area`) | 3 saat pasang tinggi, 1 saat rendah |
| Sungai dalam (`DeepRiver_Fixed`) | 5 |
| Kayu apung | 1 saat pertama diinjak, lalu tenggelam (5) selama 5 turn, lalu muncul lagi (1) |

### Pertarungan (`pertarungan.py`)

- **Aksi:** Attack, Defend, Heal, Parry. Branching factor 4 di setiap node.
- **Algoritma NPC:** Minimax, Alpha-Beta, Alpha-Beta Early Stop, dan Expectimax.
- **Evaluation function:** `eval_hp_diff`, `eval_defensive`, `eval_aggressive`, `eval_stance_aware`.
- **Mekanik:** peluang kena dan peluang Heal naik mengikuti deret Fibonacci seiring HP turun. Defend makin tembus bila dipakai beruntun. Parry membatalkan serangan lawan dan memantulkan damage.
- **Anti-kebuntuan (enrage):** mulai ronde 8 semua damage naik 10% per ronde. Bila batas giliran habis, pemenangnya yang rasio HP-nya lebih tinggi.
- **Debug overlay:** menampilkan aksi yang dipertimbangkan NPC beserta skornya, jumlah node, dan jumlah yang dipangkas.

### Musuh dan reward (`optimasi.py`)

| Musuh | Max HP | Damage | Gaya (eval) | Power |
|---|---|---|---|---|
| Pemburu Liar | 60 | 12–27 | aggressive | 190.6 |
| Penjaga Hutan | 85 | 13–29 | defensive | 229.9 |
| Pendekar Bayangan | 110 | 15–32 | hp_diff | 276.9 |
| Ksatria Besi | 135 | 14–32 | stance_aware | 302.9 |
| Naga Kecil | 160 | 16–35 | aggressive | 351.2 |

Pemain awal: 100 HP, damage 10–25, peluang kena 70%–85% (power 235.6). Rumus `power = max_hp + rata2_damage × rata2_peluang_kena × 10`.

Reward tiap kemenangan: `+8 max_hp`, `+2 atk_min/atk_max`, `+0.02 hit_base`, `+0.01 hit_cap`. Pemulihan HP antar duel diatur `POST_FIGHT_RECOVERY` di `optimasi.py`: bagian HP yang hilang yang dipulihkan setelah menang. Nilai di kode saat ini **0.5**, jadi separuh HP yang hilang pulih dan sisanya terbawa ke duel berikutnya. Angka di laporan dihitung dengan nilai 1.0 (HP pulih penuh); lihat catatan di bagian [Tes dan Eksperimen](#tes-dan-eksperimen).

### Local Search

Ruang pencarian adalah permutasi urutan 5 musuh, dan neighbor-nya adalah tukar 2 posisi. Objective yang diminimalkan adalah total HP yang terkuras, ditambah penalti besar untuk duel yang diprediksi kalah. Algoritma: Hill Climbing (steepest-ascent + random restart) dan Simulated Annealing.

### CSP di gameplay (kunci musuh)

- **Variables:** 5 musuh. **Domain:** slot urutan {1..5} yang kekuatan pemainnya memenuhi `power(musuh) × margin`. **Constraint:** all-different (AC-3).
- `LOCK_MARGIN = 0.8`: musuh terkunci selama `power(pemain) < 0.8 × power(musuh)`. Musuh terkunci diam, tidak dipilih Mode Otomatis, dan kontak dengannya tidak memulai duel.
- Pada kondisi awal, Ksatria Besi dan Naga Kecil terkunci. Setelah 2 kemenangan semua musuh terbuka.

### Sungai dinamis (`sungai.py`)

Modul ini bisa diuji tanpa pygame.

- **Knowledge Base FOL/CNF:** aturan R1–R11 untuk pasang, kayu apung, kayu tenggelam, dan kayu muncul lagi. `TELL` memasukkan kejadian dan menjalankan forward chaining. `ASK` menjawab biaya dan keamanan petak lewat backward chaining. Biaya semua pencarian diambil dari KB.
- **Perencana PDDL:** domain berisi aksi `STEP_ON_WOOD` dan `MOVE`. Planner memakai A\* atas ruang state STRIPS dan bisa menghasilkan file masalah PDDL standar (`to_pddl_problem`).
- **Replanning:** saat biaya berubah (pasang berganti, kayu diinjak atau tenggelam), rute otomatis dihitung ulang.
- **MDP / MEU:** pasang berantai Markov (rendah→tinggi 0.20, tinggi→rendah 0.30), γ = 0.97, dihitung dengan value iteration dan dijalankan sebagai kebijakan closed-loop.

### Mode Otomatis (O)

Pemain berjalan ke musuh tidak terkunci dengan `power` terkecil, dihitung ulang tiap langkah dan tiap kemenangan (greedy). **Rem:** bila duel melawan musuh itu diprediksi kalah, mode berhenti dan menampilkan pesan. Menekan **O** lagi melanjutkan, dan menekan WASD membatalkan.

## Struktur Repo

```
.
├── README.md
├── src/
│   ├── game.py              game utama: peta, pathfinding A*/UCS, HUD, mode otomatis, panel P/C/K/J
│   ├── pertarungan.py       duel bergiliran: Minimax, Alpha-Beta, Early Stop, Expectimax
│   ├── optimasi.py          5 musuh + reward; Local Search (Hill Climbing, SA) dan CSP (backtracking+MRV+LCV+AC-3)
│   ├── sungai.py            sungai dinamis: KB FOL/CNF (TELL/ASK), planner PDDL, MDP/MEU
│   ├── run_experiments.py   eksperimen pertarungan yang dipakai laporan
│   └── assets/              sprite dan tileset (harus di samping game.py)
├── report/
│   ├── LAPORAN_PERTARUNGAN.md
│   ├── LAPORAN_OPTIMASI.md
│   └── LAPORAN_SUNGAI.md
└── tests/
    ├── test_ai.py           12 tes: pertarungan, optimasi, CSP
    ├── test_sungai.py       23 tes: sungai, KB, PDDL, MDP
    └── test_turn.py         9 tes: sistem turn di level game
```

## Tes dan Eksperimen

```bash
python -m unittest discover -s tests -v     # 44 tes otomatis (±1 detik)
python src/run_experiments.py               # eksperimen pertarungan untuk laporan
```

Ringkasan hasil (angka lengkap ada di laporan).

> **Catatan:** angka di `LAPORAN_OPTIMASI.md` dihitung dengan `POST_FIGHT_RECOVERY = 1.0`, sedangkan nilai di `src/optimasi.py` sekarang 0.5. Tes sudah memakai `recovery=1.0` secara eksplisit sehingga tetap cocok dengan laporan, tetapi hasil panel **P** di game akan berbeda dari tabel laporan. Samakan salah satunya sebelum dikumpulkan.

- **Alpha-Beta vs Minimax:** hasil sama, tetapi node yang diperiksa jauh lebih sedikit (depth 6: 5461 → 438 node, hemat 92.0%).
- **Local Search:** dengan `POST_FIGHT_RECOVERY = 1.0` semua algoritma menemukan biaya terbaik 1039.8 dan greedy sudah optimal. Bila HP terbawa antar duel (`POST_FIGHT_RECOVERY` < 1), greedy tidak lagi optimal dan Local Search jadi bermakna.
- **CSP:** margin 0.5 dan 0.8 punya solusi, margin ≥ 1.0 tidak (ditolak sebelum backtracking dimulai).
- **PDDL vs A\*:** biaya rencana sama di 80/80 peta uji.
- **MEU vs A\*:** biaya rata-rata 19.52 vs 19.96 (N=300 peta), selisih kecil (±2.2%) tetapi signifikan.

## Laporan

| Berkas | Isi |
|---|---|
| [`report/LAPORAN_PERTARUNGAN.md`](report/LAPORAN_PERTARUNGAN.md) | Definisi formal state/aksi/utility, algoritma, perbandingan eval function, urutan aksi, dan kedalaman |
| [`report/LAPORAN_OPTIMASI.md`](report/LAPORAN_OPTIMASI.md) | Roster musuh, Local Search, CSP, kunci musuh, dan integrasi ke game |
| [`report/LAPORAN_SUNGAI.md`](report/LAPORAN_SUNGAI.md) | Sungai dan sistem turn, KB FOL/CNF, PDDL, MDP/MEU, dan batasan |

## Anggota

- Mohammad Arya Dhinata (2504992)
- Bentar Bintang Umeir (2509865)
- Luthfi Aulia Jodi (2521743)
