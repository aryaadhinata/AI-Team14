# AI-Team14 — Kejar-Kejaran di Desa

Game pygame untuk tugas AI: pathfinding, pertarungan adversarial, Local Search, dan CSP.

## Menjalankan
    pip install pygame        # atau pygame-ce jika pygame belum mendukung versi Python Anda
    python src/game.py        # dari root repo (atau: cd src && python game.py)
Folder `src/assets/` harus tetap berada di samping `src/game.py`.

## Struktur
    src/game.py             game utama: peta, pathfinding A*/UCS, HUD, mode otomatis, panel P/C
    src/pertarungan.py      duel bergiliran: Minimax, Alpha-Beta, Early Stop, Expectimax
    src/optimasi.py         5 musuh + reward; Local Search (Hill Climbing, SA) dan CSP (backtracking+MRV+LCV+AC-3)
    src/sungai.py           sungai dinamis: KB FOL/CNF (TELL/ASK), planner PDDL, MDP/MEU
    src/run_experiments.py  eksperimen yang dipakai laporan
    report/                 LAPORAN_PERTARUNGAN.md, LAPORAN_OPTIMASI.md, LAPORAN_SUNGAI.md
    tests/                  test_ai.py, test_sungai.py (tes otomatis)

## Fitur AI
- Pathfinding A*/UCS untuk NPC dan musuh pengejar (`game.py`)
- Pertarungan bergiliran dengan 4 aksi: Attack, Defend, Heal, Parry (`pertarungan.py`)
- 5 musuh dengan stat berbeda; menang = stat pemain naik (`optimasi.py`)
- **CSP di gameplay:** musuh *terkunci* selama power pemain < 0.8 x power musuh; menang membuka kunci
- **Local Search:** tombol P membandingkan Hill Climbing, Simulated Annealing, brute-force, dan greedy
- **Sungai dinamis:** batu (1), area pasang (3/1), sungai dalam (5), kayu apung (1 lalu 5); KB FOL/CNF, perencana PDDL, dan MDP/MEU (lihat `report/LAPORAN_SUNGAI.md`)
- **Mode otomatis (O):** pemain mengejar musuh *tidak terkunci* yang paling mudah; berhenti bila duel diprediksi kalah

## Kontrol
WASD gerak · SPACE lewati giliran · T mode giliran/real-time · O mode otomatis ·
P Local Search · C CSP (tekan lagi = ganti margin) · K KB sungai · J rencana PDDL/A*/MEU · U ganti planner · X tutup panel · E debug · ESC keluar

## Tes
    python -m unittest discover -s tests -v

## Anggota
- Mohammad Arya Dhinata (2504992)
- Bentar Bintang Umair (2509865)
- Luthfi Aulia Jodi (2521743)