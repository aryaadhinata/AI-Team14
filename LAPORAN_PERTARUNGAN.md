# Laporan Modul Pertarungan (NPC vs Pemain)

Modul: `pertarungan.py` · dipicu dari `game.py` saat NPC menangkap pemain
(`Game.on_capture()` → `Game.start_combat()`).

## 1. Definisi Formal

**State** `s = (player_hp, npc_hp, turn, to_move, player_last, npc_last)`
- `player_hp`, `npc_hp` — nyawa (0–100).
- `turn` — ronde ke berapa; 1 ronde = 1 giliran NPC + 1 giliran pemain.
- `to_move` — `True` = giliran NPC (pemaksimal/MAX), `False` = giliran pemain (peminimal/MIN).
- `player_last`, `npc_last` — aksi terakhir masing-masing pihak. Efek **Defend**/**Parry**
  baru berlaku saat **lawan** menyerang di giliran berikutnya (bukan giliran sendiri).

**Action** `A = {ATTACK, DEFEND, HEAL, PARRY}` — branching factor = 4 di setiap node.
| Aksi | Efek |
|---|---|
| **Attack** | Damage 18 ke lawan. Dibatalkan total + kena balik 10 kalau lawan *Parry*; dipotong 50% kalau lawan *Defend*. |
| **Defend** | Tidak ada efek langsung; mengurangi 50% damage serangan lawan di giliran berikut. |
| **Heal** | Pulihkan 15 HP milik sendiri (dibatasi maksimum 100). |
| **Parry** | Berisiko: kalau lawan menyerang giliran berikut, serangan dibatalkan total + lawan kena balik 10. Kalau lawan tidak menyerang, tidak berefek apa-apa (kesempatan terbuang). |

**Transition function** `RESULT(s, a)` — implementasi: `apply_action()`.

**Terminal test** `T(s) := player_hp ≤ 0 OR npc_hp ≤ 0 OR turn ≥ MAX_TURNS (20)`
Batas `MAX_TURNS` mencegah pohon pencarian maupun pertarungan sungguhan tak berkesudahan.

**Utility** `U(s)` (hanya didefinisikan di state terminal, dari sudut pandang NPC/MAX):
- NPC menang: `+10000 − turn` (menang lebih cepat = lebih baik)
- Pemain menang: `−10000 + turn`
- Seri / limit giliran habis: `0`

**Evaluation function** `Eval(s)` — dipakai sebagai pengganti `U(s)` saat pencarian
dipotong di kedalaman tertentu sebelum `s` terminal. Empat varian disediakan
untuk eksperimen #2 (lihat kode `pertarungan.py` bagian 5):
- `eval_hp_diff`: `npc_hp − player_hp` (netral)
- `eval_defensive`: `1.8·npc_hp − player_hp` (menghargai HP sendiri lebih tinggi)
- `eval_aggressive`: `npc_hp − 2.2·player_hp` (menghargai menghabisi lawan)
- `eval_stance_aware`: `hp_diff` + bonus kecil kalau posisi terakhir NPC *defend*/*parry*

## 2. Algoritma & Debug Overlay

Empat algoritma pencarian keputusan NPC (semua ada di `pertarungan.py`, dipanggil
lewat `choose_npc_action()`): **Minimax**, **Alpha-Beta**, **Early Stop**
(alpha-beta dengan batas jumlah node/"node budget", sisanya pakai evaluasi apa
adanya), dan **Expectimax** (opsional — giliran pemain jadi *chance node*
dengan distribusi probabilitas, bukan lawan optimal).

Overlay debug (`render_combat_debug_card`, muncul di modal pertarungan
`game.py`) menampilkan persis dua hal yang diminta:
1. **Aksi yang dipertimbangkan NPC & skornya** — nilai setiap aksi akar
   (Serang/Bertahan/Pulihkan/Tangkis), aksi terpilih disorot warna kuning.
2. **Node count** — jumlah node yang dieksplorasi + jumlah yang dipangkas
   (kalau alpha-beta), buat dibandingkan antar algoritma.

## 3. Hasil Eksperimen

Semua angka di bawah adalah hasil run nyata `run_experiments.py`
(`random.seed(7)`, state awal `player_hp=100, npc_hp=70` kecuali disebutkan
lain), bukan estimasi.

### 3.1 Minimax vs Alpha-Beta Pruning

| Depth | Minimax (node) | Alpha-Beta (node) | Dipangkas | Hemat | Aksi sama? |
|---|---|---|---|---|---|
| 2 | 21 | 13 | 3 | 38.1% | Ya |
| 3 | 85 | 37 | 6 | 56.5% | Ya |
| 4 | 341 | 84 | 24 | 75.4% | Ya |
| 5 | 1365 | 212 | 46 | 84.5% | Ya |
| 6 | 5461 | 461 | 141 | 91.6% | Ya |

**Kesimpulan:** alpha-beta selalu memberi **aksi keputusan yang identik** dengan
minimax (sesuai teori — pruning tidak mengubah hasil, cuma mempercepat), dan
penghematan node makin besar seiring bertambahnya kedalaman (38% di depth 2,
lebih dari 90% di depth 6) karena makin banyak cabang yang bisa dipangkas.

### 3.2 Perbandingan Evaluation Function

State uji: `player_hp=100, npc_hp=55` (NPC terdesak, di sinilah gaya main paling kelihatan bedanya), depth 4:

| Eval function | Aksi terpilih | Skor Serang | Skor Bertahan | Skor Pulihkan | Skor Tangkis |
|---|---|---|---|---|---|
| `hp_diff` | **Serang** | −45 | −54 | −48 | −45 |
| `defensive` | **Tangkis** | −20.8 | −17.2 | −6.4 | −1.0 |
| `aggressive` | **Serang** | −151.8 | −167.4 | −161.4 | −165.0 |
| `stance_aware` | **Tangkis** | −45 | −52 | −46 | −43 |

**Kesimpulan:** fungsi evaluasi yang berat sebelah ke HP sendiri (`defensive`,
`stance_aware`) membuat NPC memilih **Tangkis** saat HP-nya rendah — main aman.
Fungsi yang netral/berat sebelah ke HP lawan (`hp_diff`, `aggressive`) tetap
memilih **Serang** meski HP sendiri rendah — mengejar kemenangan cepat.

### 3.3 Perbandingan Urutan Aksi (pengaruh ke pruning)

Depth 5, eval `hp_diff`:

| Urutan aksi | Node | Dipangkas | Aksi akar |
|---|---|---|---|
| default: Serang, Bertahan, Pulihkan, Tangkis | **212** | 46 | Serang |
| Tangkis, Pulihkan, Bertahan, Serang | 404 | 83 | Serang |
| Pulihkan, Bertahan, Tangkis, Serang | 510 | 89 | Serang |

**Kesimpulan:** hasil akhir (aksi yang dipilih) **sama** di ketiga urutan —
urutan tidak mengubah *jawaban*, hanya *efisiensi pencarian*. Urutan default
(mengevaluasi Serang lebih dulu, yang kebetulan mendekati aksi terbaik) hampir
**2.4× lebih hemat node** dibanding urutan terburuk (`Pulihkan` dulu) —
konsisten dengan teori bahwa alpha-beta paling efektif kalau kandidat terbaik
dievaluasi lebih awal (move ordering).

### 3.4 Perbandingan Kedalaman

Alpha-beta, eval `hp_diff`:

| Depth | Node | Dipangkas | Waktu (ms) |
|---|---|---|---|
| 1 | 5 | 0 | 0.027 |
| 2 | 13 | 3 | 0.054 |
| 3 | 37 | 6 | 0.150 |
| 4 | 84 | 24 | 0.308 |
| 5 | 212 | 46 | 0.792 |
| 6 | 461 | 141 | 1.859 |
| 7 | 1106 | 268 | 4.305 |

**Kesimpulan:** tanpa pruning jumlah node akan naik ~4× per level (branching
factor 4); dengan alpha-beta laju kenaikannya jauh lebih landai (~2.4×/level
rata-rata di sini) karena makin dalam pohonnya, makin banyak kesempatan
memangkas. Depth 4 (dipakai sebagai default di `game.py`) sudah cukup dalam
untuk mempertimbangkan ~2 ronde ke depan dengan biaya <1 ms — aman dipakai
real-time di dalam game.

### 3.5 Tingkah Laku NPC per Fungsi Evaluasi

Simulasi penuh (alpha-beta, depth 4) lawan pemain-bot sederhana
(`player_policy_greedy`, `seed=42`):

| Eval function | Pemenang | Ronde | Aksi NPC (serang/bertahan/pulih/tangkis) |
|---|---|---|---|
| `hp_diff` | NPC | 13 | 14 / 0 / 0 / 0 |
| `defensive` | Seri (limit) | 20 | 3 / 0 / 15 / 2 |
| `aggressive` | NPC | 13 | 14 / 0 / 0 / 0 |
| `stance_aware` | NPC | 15 | 13 / 0 / 2 / 1 |

**Kesimpulan (paling menarik):** `hp_diff` dan `aggressive` menghasilkan NPC
yang **100% menyerang** — dan justru **menang lebih cepat** (13 ronde).
`defensive` membuat NPC nyaris **hanya heal** (15 dari 20 aksi) — jadi terlalu
pasif untuk benar-benar menghabisi lawan dan berakhir **seri** karena kehabisan
giliran. Ini menunjukkan fungsi evaluasi yang "kelihatannya aman" (mengutamakan
HP sendiri) belum tentu optimal kalau tidak diimbangi dorongan untuk benar-benar
menyerang — trade-off klasik agresif vs defensif dalam desain AI game.

### 3.6 Expectimax vs Minimax (opsional)

Lawan pemain **acak murni** (bukan bot greedy), depth 3, 60 kali simulasi tiap algoritma:

```
minimax   (asumsi pemain optimal) -> aksi=attack  val=-30.0  nodes=341
expectimax(asumsi pemain acak)    -> aksi=heal    val=-9.0   nodes=341
lawan 60x pemain ACAK -> minimax menang 60/60   |   expectimax menang 60/60
```

**Kesimpulan:** pada state awal yang sama, **minimax memilih Serang** (berjaga
terhadap pemain terburuk yang selalu membalas optimal), sementara **expectimax
memilih Pulihkan** (karena rata-rata dari 4 kemungkinan aksi pemain acak jauh
lebih ringan daripada skenario terburuk, jadi tidak perlu buru-buru menyerang).
Jumlah node yang dieksplorasi sama (keduanya tetap membuka semua cabang tanpa
pruning di sini). Melawan pemain **acak sungguhan**, keduanya sama-sama menang
60/60 — pemain acak terlalu lemah untuk membedakan keduanya; perbedaan gaya
main (agresif vs sabar) akan lebih kelihatan lawan pemain yang lebih kuat/lebih
mendekati optimal.

## 4. Ringkasan

- Alpha-beta terbukti **selalu memberi keputusan yang sama** dengan minimax,
  dengan penghematan node hingga >90% pada depth 6.
- **Urutan aksi** memengaruhi efisiensi pruning (hingga 2.4×) tapi **tidak**
  memengaruhi hasil akhir.
- **Fungsi evaluasi** adalah pengaruh terbesar terhadap *gaya main* NPC:
  agresif vs defensif, dan defensif berlebihan bisa berujung seri, bukan menang.
  Cara membacanya: skor positif berarti menguntungkan NPC, kian tinggi kian
  baik bagi NPC — bukan skala mutlak yang bisa dibandingkan antar fungsi
  evaluasi (masing-masing punya skala sendiri).
- **Kedalaman** depth=4 dipakai sebagai default in-game karena waktu
  komputasinya <1 ms tapi sudah cukup "melihat" ke depan untuk main masuk akal.
- **Expectimax** (opsional) berguna kalau pemain diasumsikan tidak selalu
  optimal — menghasilkan NPC yang lebih berani mengambil risiko (mis. memilih
  heal alih-alih menyerang) dibanding minimax yang selalu berasumsi terburuk.
