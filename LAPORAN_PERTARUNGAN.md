# Laporan Modul Pertarungan (NPC vs Pemain)

Modul: `pertarungan.py` · dipicu dari `game.py` saat NPC menangkap pemain
(`Game.on_capture()` → `Game.start_combat()`).

> **Update terakhir:** rentang damage serangan diubah ke **`ATTACK_DMG_MIN, ATTACK_DMG_MAX = 10, 25`**
> (sebelumnya sempat dicoba 5–10, lalu 30–50 sebagai kalibrasi). Semua angka di
> laporan ini dari nilai **10–25** yang aktif sekarang. Lihat §3.5–3.6 dan §4 —
> nilai ini membuat pertarungan **hampir selalu berakhir seri**, sama seperti
> masalah yang ditemukan waktu rentangnya masih 5–10.

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
| **Attack** | Peluang kena: **70%** dasar → naik **Fibonacci** seiring HP penyerang turun → maks **85%**. Kalau kena, damage diacak dari **`[10, 13, 16, 19, 22, 25]`** dengan bobot `[13,8,5,3,2,1]` (10 paling sering, **25 paling jarang**) — rata-rata **≈13.75** per serangan yang kena. Kalau lawan *Parry* giliran lalu: serangan dibatalkan total, penyerang balik kena `random(0.5×–2×)` dari damage yang tadinya mau masuk. Kalau lawan *Defend*: damage dikali `defend_penetration`. |
| **Defend** | Tembus: **0.2** di pemakaian pertama → naik **Fibonacci** tiap dipakai **beruntun** → maks **1.0**. |
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

Angka di bawah dari run nyata `run_experiments.py` dengan `ATTACK_DMG_MIN, ATTACK_DMG_MAX = 10, 25` (`random.seed(7)`, state awal `player_hp=100, npc_hp=70` kecuali disebut lain).

### 3.1 Minimax vs Alpha-Beta Pruning

| Depth | Minimax (node) | Alpha-Beta (node) | Dipangkas | Hemat | Aksi sama? |
|---|---|---|---|---|---|
| 2 | 21 | 13 | 3 | 38.1% | Ya |
| 3 | 85 | 38 | 6 | 55.3% | Ya |
| 4 | 341 | 84 | 24 | 75.4% | Ya |
| 5 | 1365 | 219 | 45 | 84.0% | Ya |
| 6 | 5461 | 470 | 143 | 91.4% | Ya |

**Kesimpulan:** identik dengan run-run sebelumnya (5–10 maupun 30–50) — nilai damage tidak memengaruhi *bentuk* pohon pencarian sama sekali, karena `apply_action_expected` selalu deterministik dan bercabang 4 di tiap node terlepas dari besar damage-nya.

### 3.2 Perbandingan Evaluation Function

State uji: `player_hp=100, npc_hp=55`, depth 4:

| Eval function | Aksi terpilih | Skor Serang | Skor Bertahan | Skor Pulihkan | Skor Tangkis |
|---|---|---|---|---|---|
| `hp_diff` | **Serang** | −44.4 | −46.7 | −51.0 | −45.0 |
| `defensive` | **Tangkis** | −10.2 | −4.5 | −12.5 | **−1.0** |
| `aggressive` | **Serang** | −147.2 | −165.0 | −161.8 | −165.0 |
| `stance_aware` | **Tangkis** | −43.7 | −44.9 | −49.4 | −43.0 |

**Kesimpulan:** pola sama seperti sebelumnya (defensif → Tangkis, netral/agresif → Serang), dan menariknya **Heal justru selalu jadi skor terendah** di semua eval function — konsisten dengan temuan §3.5: dengan damage sekecil ini, NPC "melihat" bahwa healing tidak cukup menguntungkan dibanding menyerang/bertahan dalam pencarian jangka pendek (meski dalam simulasi jangka panjang Heal tetap membuat pertarungan berlarut/seri, lihat §3.5).

### 3.3 Perbandingan Urutan Aksi

Depth 5, eval `hp_diff`:

| Urutan aksi | Node | Dipangkas | Aksi akar |
|---|---|---|---|
| default: Serang, Bertahan, Pulihkan, Tangkis | **219** | 45 | Serang |
| Tangkis, Pulihkan, Bertahan, Serang | 486 | 100 | Serang |
| Pulihkan, Bertahan, Tangkis, Serang | 615 | 70 | Serang |

**Kesimpulan:** tetap konsisten — keputusan akhir sama di semua urutan, tapi urutan default **2.2–2.8× lebih hemat node**.

### 3.4 Perbandingan Kedalaman

| Depth | Node | Dipangkas | Waktu (ms) |
|---|---|---|---|
| 1 | 5 | 0 | 0.022 |
| 2 | 13 | 3 | 0.053 |
| 3 | 38 | 6 | 0.132 |
| 4 | 84 | 24 | 0.283 |
| 5 | 219 | 45 | 0.648 |
| 6 | 470 | 143 | 1.471 |
| 7 | 1175 | 264 | 3.403 |

**Kesimpulan:** sama seperti run-run sebelumnya — ukuran pohon murni fungsi dari depth & pruning, tidak dipengaruhi nilai damage.

### 3.5 & 3.6 — Dengan damage 10–25, masalah "kebanyakan seri" muncul lagi

| Eval function | Pemenang (MAX_TURNS=20) | Aksi NPC (serang/bertahan/pulih/tangkis) |
|---|---|---|
| `hp_diff` | **Seri** | 19 / 0 / 1 / 0 |
| `defensive` | **Seri** | 2 / 9 / 0 / 9 |
| `aggressive` | **Seri** | 19 / 0 / 1 / 0 |
| `stance_aware` | **Seri** | 14 / 5 / 0 / 1 |

**Semua seri** di batas 20 giliran — walau NPC (`hp_diff`, `aggressive`) sudah menyerang di 19 dari 20 giliran. Eksperimen #6 (lawan 60× pemain **acak murni**): minimax menang **14/60**, expectimax **25/60** — jauh dari 60/60 yang tercatat sebelumnya di rentang 30–50.

Saya longgarkan `MAX_TURNS` ke 60 khusus untuk melihat kalau diberi waktu lebih:

| Eval function | Pemenang (MAX_TURNS=60) | Aksi NPC |
|---|---|---|
| `hp_diff` | **NPC** (ronde 59) | 48 / 6 / 6 / 0 |
| `defensive` | Seri | 6 / 32 / 3 / 19 |
| `aggressive` | Seri | 49 / 0 / 11 / 0 |
| `stance_aware` | Seri | 39 / 8 / 12 / 1 |

Lawan 60× pemain acak di 60 giliran: minimax **50/60** menang (rata-rata 31.7 ronde), expectimax **59/60** menang (rata-rata 22.6 ronde) — jauh lebih baik, tapi butuh giliran **3× lebih banyak** dari batas default untuk mulai terlihat menentukan.

**Kesimpulan:** damage 10–25 (rata-rata ≈13.75, dikalikan peluang kena 70–85% → efektif ≈9.6–11.7 per serangan) **masih kalah** dibanding pemulihan Heal yang efektif ≈16.5 saat HP kritis. Ini pola yang persis sama seperti temuan di rentang 5–10 sebelumnya — cuma butuh lebih banyak giliran untuk terlihat (karena damage per-hit-nya lebih besar dari 5–10, tapi tetap belum melewati ambang yang dibutuhkan untuk mengalahkan laju heal dalam 20 giliran).

## 4. Ringkasan & Rekomendasi

- Struktur pencarian (node count, efek pruning/depth/urutan aksi) **tidak terpengaruh** oleh nilai damage — hanya bentuk *outcome* pertarungan yang berubah.
- **Damage 10–25 belum cukup** untuk mengembalikan tingkat kemenangan seperti versi lama (dulu 60/60 lawan pemain acak) dalam batas 20 giliran — hasilnya mayoritas seri, mirip masalah di rentang 5–10.
- Dari kalibrasi sebelumnya, rentang **30–50** adalah titik yang terbukti mengembalikan hasil mendekati versi lama (59–60/60 menang, nyaris tanpa seri) dalam `MAX_TURNS=20`. Titik tengah (mis. **20–35** atau **22–40**) kemungkinan bisa memberi keseimbangan antara "10–25 (kebanyakan seri)" dan "30–50 (cepat menang)" — beri tahu saya kalau ingin saya kalibrasi titik tengah itu juga.
- Alternatif lain tanpa menyentuh damage lagi: naikkan `MAX_TURNS`, atau turunkan `HEAL_CHANCE_CAP`/`HEAL_BASE` supaya Heal tidak sekuat sekarang relatif terhadap Attack.