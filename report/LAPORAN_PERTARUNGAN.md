# Laporan Modul Pertarungan (NPC vs Pemain)
 
Modul: `pertarungan.py` · dipicu dari `game.py` saat musuh dan pemain bertemu
(`Game.check_enemy_contact()` → `Game.start_multi_combat()`).
 
> **Update terakhir:** rentang damage serangan **`ATTACK_DMG_MIN, ATTACK_DMG_MAX = 16, 30`**
> (sebelumnya sempat dicoba 5–10, 10–25, dan 30–50). Semua angka di laporan ini dari nilai **16–30**
> yang aktif sekarang. Dengan nilai ini hasil duel **tidak lagi didominasi seri** (lihat §3.5–3.6).
> Duel juga punya anti-kebuntuan: mulai ronde 8 semua damage naik 10% per ronde (*enrage*), dan saat
> batas giliran habis pemenangnya yang rasio HP-nya lebih tinggi (seri hanya jika selisih ≤ 5%).
 
## 1. Definisi Formal
 
**State** `s = (player_hp, npc_hp, turn, to_move, player_last, npc_last, player_defend_streak, npc_defend_streak, player_last_dmg_taken, npc_last_dmg_taken)`
- `player_hp`, `npc_hp` — nyawa (0–100).
- `turn` — ronde ke berapa; 1 ronde = 1 giliran NPC + 1 giliran pemain.
- `to_move` — `True` = giliran NPC (pemaksimal/MAX), `False` = giliran pemain (peminimal/MIN).
- `player_last`, `npc_last` — aksi terakhir masing-masing pihak (dipakai Defend/Parry).
- `*_defend_streak` — berapa kali **beruntun** pihak itu memilih Defend (§1.2: makin sering bertahan, makin tembus).
- `*_last_dmg_taken` — damage nyata terakhir yang diterima pihak itu (§1.3: bonus Heal).
**Action** `A = {ATTACK, DEFEND, HEAL, PARRY}` — branching factor = 4 di setiap node.
 
| Aksi | Mekanik |
|---|---|
| **Attack** | Peluang kena: **70%** dasar → naik **Fibonacci** seiring HP penyerang turun → maks **85%**. Kalau kena, damage diacak dari **`[16, 19, 22, 24, 27, 30]`** dengan bobot `[13,8,5,3,2,1]` (16 paling sering, **30 paling jarang**) — rata-rata **≈19.6** per serangan yang kena. Kalau lawan *Parry* giliran lalu: serangan dibatalkan total, penyerang balik kena `random(0.5×–2×)` dari damage yang tadinya mau masuk. Kalau lawan *Defend*: damage dikali `defend_penetration`. |
| **Defend** | Tembus: **0.5** di pemakaian pertama → naik **Fibonacci** tiap dipakai **beruntun** → maks **1.0**. |
| **Heal** | Peluang berhasil: **10%** dasar → naik **Fibonacci** seiring HP kian rendah → maks **95%**. Berhasil: 75% dapat **15**; 25% dapat bonus `(15 + damage_terakhir_atau_5) × 1.10–1.67` (bobot sama, 1.10 paling sering). |
| **Parry** | Kena serang giliran berikut → serangan lawan batal total + lawan kena balik `random(0.5×–2×)` damage tsb. Kalau lawan tidak menyerang: percuma. |
 
**Transition function** — dua versi (tidak berubah dari sebelumnya):
`apply_action(s,a)` = RNG asli (dipakai pertarungan sungguhan, balikin `(state, event)`);
`apply_action_expected(s,a)` = versi nilai-harapan deterministik (dipakai khusus oleh minimax/alpha-beta/dst supaya pohon pencarian tidak berubah-ubah tiap dipanggil).
 
**Terminal test** `T(s) := player_hp ≤ 0 OR npc_hp ≤ 0 OR turn ≥ MAX_TURNS (20)`
 
**Utility** `U(s)`: NPC menang `+10000−turn` · Pemain menang `−10000+turn` · Seri `0`
 
**Evaluation function** — 4 varian: `eval_hp_diff`, `eval_defensive` (×1.8 HP sendiri), `eval_aggressive` (×2.2 HP lawan), `eval_stance_aware` (+bonus posisi).
 
## 2. Algoritma & Debug Overlay
 
Tidak berubah: **Minimax**, **Alpha-Beta**, **Early Stop**, **Expectimax** (opsional). Overlay debug menampilkan aksi yang dipertimbangkan NPC + skornya, dan node count + jumlah dipangkas. Jeda **0.8 detik** (`COMBAT_TURN_DELAY`) sebelum aksi NPC dieksekusi, log pakai `describe_event()` (menunjukkan hit/miss/parry/heal kritikal secara eksplisit).
 
## 3. Hasil Eksperimen
 
Angka di bawah dari run nyata `run_experiments.py` dengan `ATTACK_DMG_MIN, ATTACK_DMG_MAX = 16, 30` (`random.seed(7)`, state awal `player_hp=100, npc_hp=70` kecuali disebut lain). Jalankan ulang `python src/run_experiments.py` untuk memeriksa; bagian deterministik (node, pruning) pasti sama, bagian ber-RNG bisa sedikit berbeda.
 
### 3.1 Minimax vs Alpha-Beta Pruning
 
| Depth | Minimax (node) | Alpha-Beta (node) | Dipangkas | Hemat | Aksi sama? |
|---|---|---|---|---|---|
| 2 | 21 | 13 | 3 | 38.1% | Ya |
| 3 | 85 | 38 | 6 | 55.3% | Ya |
| 4 | 341 | 83 | 24 | 75.7% | Ya |
| 5 | 1365 | 213 | 45 | 84.4% | Ya |
| 6 | 5461 | 438 | 138 | 92.0% | Ya |
 
**Kesimpulan:** nilai damage tidak memengaruhi *bentuk* pohon pencarian — `apply_action_expected` selalu deterministik dan bercabang 4 di tiap node. Alpha-Beta bernilai sama dengan Minimax (diverifikasi otomatis di `tests/test_ai.py`) tapi memeriksa jauh lebih sedikit node.
 
### 3.2 Perbandingan Evaluation Function
 
State uji: `player_hp=100, npc_hp=55`, depth 4:
 
| Eval function | Aksi terpilih | Skor Serang | Skor Bertahan | Skor Pulihkan | Skor Tangkis |
|---|---|---|---|---|---|
| `hp_diff` | **Serang** | −44.3 | −51.3 | −54.9 | −45.0 |
| `defensive` | **Tangkis** | −13.4 | −13.3 | −19.8 | **−1.0** |
| `aggressive` | **Serang** | −138.1 | −165.0 | −161.8 | −165.0 |
| `stance_aware` | **Tangkis** | −44.3 | −49.8 | −53.5 | −43.0 |
 
**Kesimpulan:** defensif/stance-aware → Tangkis, netral/agresif → Serang. Aksi Pulihkan bernilai terendah pada `hp_diff`, `defensive`, dan `stance_aware`; pada `aggressive` yang terendah justru Bertahan/Tangkis (−165.0) karena eval ini hanya menghargai HP lawan.
 
### 3.3 Perbandingan Urutan Aksi
 
Depth 5, eval `hp_diff`:
 
| Urutan aksi | Node | Dipangkas | Aksi akar |
|---|---|---|---|
| default: Serang, Bertahan, Pulihkan, Tangkis | **213** | 45 | Serang |
| Tangkis, Pulihkan, Bertahan, Serang | 486 | 100 | Serang |
| Pulihkan, Bertahan, Tangkis, Serang | 1003 | 75 | Serang |
 
**Kesimpulan:** keputusan akhir sama di semua urutan, tapi urutan default **2.3–4.7× lebih hemat node**.
 
### 3.4 Perbandingan Kedalaman
 
| Depth | Node | Dipangkas | Waktu (ms) |
|---|---|---|---|
| 1 | 5 | 0 | 0.023 |
| 2 | 13 | 3 | 0.066 |
| 3 | 38 | 6 | 0.159 |
| 4 | 83 | 24 | 0.385 |
| 5 | 213 | 45 | 0.918 |
| 6 | 438 | 138 | 2.229 |
| 7 | 1080 | 255 | 4.679 |
 
**Kesimpulan:** ukuran pohon murni fungsi dari depth & pruning, tidak dipengaruhi nilai damage. Waktu (ms) bergantung mesin.
 
### 3.5 & 3.6 — Dengan damage 16–30, duel kembali berujung menang/kalah
 
| Eval function | Pemenang (MAX_TURNS=20) | Jumlah giliran | Aksi NPC (serang/bertahan/pulih/tangkis) |
|---|---|---|---|
| `hp_diff` | **NPC** | 5 | 4 / 0 / 0 / 2 |
| `defensive` | **NPC** | 17 | 2 / 0 / 0 / 16 |
| `aggressive` | **NPC** | 13 | 12 / 0 / 2 / 0 |
| `stance_aware` | **NPC** | 5 | 4 / 0 / 0 / 2 |
 
Keempat eval function berakhir dengan kemenangan NPC, **tidak ada seri**. Eksperimen #6 (lawan 60× pemain **acak murni**): minimax menang **60/60**, expectimax **60/60**. Dengan `MAX_TURNS=60`: minimax 60/60 (rata-rata 11.9 giliran), expectimax 60/60 (11.6 giliran), seri 0/60.
 
**Kesimpulan:** damage 16–30 (rata-rata ≈19.6, dikali peluang kena 70–85% → efektif ≈13.7–16.6 per serangan) sudah cukup mengalahkan laju pemulihan Heal, dan *enrage* (+10% per ronde mulai ronde 8) mencegah duel macet. Catatan: lawan di sini pemain acak, bukan pemain manusia; kesulitan sebenarnya bergantung pada pemain.
 
## 4. Ringkasan
 
- Struktur pencarian (node, efek pruning/depth/urutan aksi) **tidak terpengaruh** oleh nilai damage — hanya *outcome* duel yang berubah.
- **Damage 16–30 + enrage** menghilangkan dominasi seri yang muncul pada 5–10 dan 10–25.
- Parry yang "gratis" saat lawan tidak menyerang tetap menjadi akar kebuntuan; enrage dan aturan pemenang-by-HP adalah penanganannya. Memberi Parry biaya atau cooldown adalah opsi lanjutan.
- Tes otomatis: `python -m unittest discover -s tests -v`.
 