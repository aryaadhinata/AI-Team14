# AI-Team14 — Kejar-Kejaran di Desa

Game pygame untuk tugas AI: pathfinding, pertarungan adversarial, Local Search, dan CSP.

## Menjalankan
    pip install pygame        # atau pygame-ce jika pygame belum mendukung versi Python Anda
    python game.py
Letakkan folder `assets/` di samping `game.py`.

## Fitur AI
- Pathfinding A*/UCS (`game.py`) untuk NPC dan musuh pengejar
- Pertarungan bergiliran: Minimax, Alpha-Beta, Early Stop, Expectimax (`pertarungan.py`)
- 5 musuh + reward stat; Local Search (Hill Climbing, Simulated Annealing) dan
  CSP (backtracking + MRV + LCV + AC-3) di `optimasi.py`
- Eksperimen: `python run_experiments.py` (laporan: `LAPORAN_*.md`)

## Kontrol utama
WASD gerak · SPACE lewati giliran · T mode giliran/real-time · O mode otomatis ·
P Local Search · C CSP (tekan lagi = ganti margin) · X tutup panel · E debug · ESC keluar

## Anggota
- Mohammad Arya Dhinata (2504992)
- Bentar Bintang Umair (2509865)
- Luthfi Aulia Jodi (2521743)