# Laporan: Sungai Dinamis & Integrasi Multi-Modul AI

Modul: `src/sungai.py` (tanpa pygame, bisa diuji terpisah) + integrasi di `src/game.py`.
Tes: `tests/test_sungai.py` (23 tes) dan `tests/test_turn.py` (9 tes, level game). Tombol: **K** panel KB · **J** panel rencana · **U** ganti planner.

> **Catatan asumsi.** Spesifikasi sumber terpotong di bagian 4 (`MDP_Tuple:` tanpa isi). Tuple MDP di §4
> dirumuskan oleh implementasi (lihat tabel §4). Aksi `MOVE`/`MOVE sunk` di §3 juga tambahan, karena
> spesifikasi hanya mendefinisikan `STEP_ON_WOOD`. Semua konstanta ada di bagian atas `sungai.py`.

## 1. Lingkungan & matriks biaya tile (Modul 03 & 09)

Sungai vertikal **organik** (`carve_river`), bukan pita lurus:

- **Garis tengah berkelok** (sinus + derau halus), lebar inti air dalam dan tebal pantai pasang **berubah**
  sepanjang aliran; tepi diberi derau sehingga tidak berbentuk kotak. Rata-rata lebar ±5.5 petak.
- Lapisan: inti = `DeepRiver_Fixed`, cincin luar = `HighTide_Area` (pantai pasang), sisanya daratan.
- **Jembatan batu** = jalur batu loncatan berliku dari tepi ke tepi (selalu menempel daratan di kedua ujung).
- **Kayu apung** = seluruh inti air dalam pada 2 baris dekat jalur lurus pemain-musuh.
- Semua tile sungai **tetap bisa dilewati** (hanya mahal), jadi peta tidak pernah terputus. Sungai dijaga di
  kolom 7–19 (diuji pada 500 peta) agar tidak menutupi spawn pemain.
- **Tampilan:** sudut membulat di tepi darat, warna air bertingkat menurut jarak ke pantai (`build_style`),
  riak beranimasi, pasir basah saat surut dan air dangkal berbusa saat pasang, batu berbentuk tidak seragam
  berlumut, gelondongan kayu miring dan bergoyang (kayu tenggelam digambar gelap).

| Tile | Biaya | Keterangan |
|---|---|---|
| Ground | 1 | |
| Rock_Fixed | 1 | jembatan permanen |
| HighTide_Area | 3 (pasang tinggi) / 1 (rendah) | pasang berantai Markov, tiap turn |
| DeepRiver_Fixed | 5 | penalti tinggi |
| Wood_Floating | 1 → 5 → 1 | langkah pertama 1; setelah diinjak jadi `Wood_Sunk` (5) selama 5 turn, lalu **muncul lagi** (1) |

Biaya diambil **dari KB lewat ASK** (`terrain_cost` → `RiverWorld.cost` → `RiverKB.ask_cost`), sehingga
`search()` (A*/UCS), debug overlay, dan perencana semua melihat biaya dinamis yang sama.
### 1.1 Sistem turn (sistem waktu utama)

Mode real-time **dihapus**; satu-satunya sistem waktu adalah **turn**, dan `t` pada KB = nomor turn.

- **Biaya turn = biaya tile.** Masuk ke tile berbiaya `c` memakan `c` turn (`turns_for_cost`, minimal 1):
  rumput 1, semak 3, pasang surut 1 / pasang tinggi 3, sungai dalam 5, batu 1, kayu apung 1, kayu tenggelam 5.
  Biaya dibaca **sebelum** waktu maju, dan untuk sungai langsung dari KB (ASK).
- Selama tiap turn berjalan: semua musuh hidup melangkah, pasang berganti, kayu tenggelam/muncul. Duel yang
  dimulai di tengah rangkaian turn menghentikan sisa turn.
- **Musuh tunduk pada aturan yang sama:** setelah masuk tile berbiaya `c`, musuh menunggu `c-1` turn berikutnya
  (mis. menyeberangi air dalam = 5 turn), sehingga menyeberang sungai juga membuat musuh lambat.
- **SPACE** = lewati 1 turn. Tombol **T** kini hanya memberi pesan bahwa mode real-time sudah tidak ada.
- A*/PDDL/MEU meminimalkan biaya yang sama dengan turn (selain faktor √2 pada langkah diagonal yang tetap
  dipakai sebagai jarak), jadi rute terbaik juga rute dengan turn paling sedikit.
- Klik mouse (`pindah`) tetap memindahkan pemain ke sel yang diklik dan juga memakan turn sebesar biaya sel itu.

## 2. Knowledge Base FOL/CNF (Modul 07)

Predikat statis: `IsRock`, `IsDeepRiver`, `TidalArea`, `Walkable`. Fluent: `HighTide(t)`,
`IsWoodFloating(x,y,t)`, `IsWoodSunk(x,y,t)`, `SteppedOn(x,y,t)`, `SunkSince(x,y,t)`, `Emerge(x,y,t)`. Aturan (klausa Horn = subset CNF),
ditampilkan apa adanya oleh tombol **K**:

```
R1  ¬HighTide(t) ∨ ¬TidalArea(x,y) ∨ TileCost(x,y,t,3)
R2  ¬SteppedOn(x,y,t) ∨ ¬IsWoodFloating(x,y,t) ∨ IsWoodSunk(x,y,t+1)
R3  ¬IsWoodSunk(x,y,t) ∨ TileCost(x,y,t,5)
R4  ¬IsWoodSunk(x,y,t) ∨ Emerge(x,y,t) ∨ IsWoodSunk(x,y,t+1)           (aksioma bingkai)
R5  ¬IsWoodFloating(x,y,t) ∨ SteppedOn(x,y,t) ∨ IsWoodFloating(x,y,t+1) (aksioma bingkai)
R6  ¬IsDeepRiver(x,y) ∨ TileCost(x,y,t,5)
R7  ¬Walkable(x,y) ∨ TileCost(x,y,t,1)
R8  ¬TileCost(x,y,t,5) ∨ Unsafe(x,y,t)
R9  ¬SteppedOn(x,y,t) ∨ ¬IsWoodFloating(x,y,t) ∨ SunkSince(x,y,t+1)
R10 ¬IsWoodSunk(x,y,t) ∨ ¬SunkSince(x,y,t−4) ∨ Emerge(x,y,t)
R11 ¬Emerge(x,y,t) ∨ IsWoodFloating(x,y,t+1)
```

**Kayu muncul lagi (R9–R11).** Kayu yang diinjak pada turn `T` tenggelam mulai `T+1` dan tetap tenggelam
selama `WOOD_RESPAWN_TURNS` = biaya kayu tenggelam = **5 turn** (`T+1 … T+5`), lalu mengapung lagi di `T+6`
dengan biaya 1 dan bisa diinjak kembali (siklus berulang). `SunkSince` mencatat awal tenggelam, `Emerge`
muncul pada turn terakhir tenggelam (`t = s+4`), dan R4 berhenti mempertahankan `IsWoodSunk` saat itu.
Tampilan: kayu tenggelam menampilkan **hitung mundur** (5…1) dan tooltip "muncul lagi N turn".

- **TELL(KB, Event)**: `("tide", t, high)` dan `("step", x, y, t)`. Aturan temporal R2/R4/R5/R9/R10/R11 dijalankan
  *forward chaining* (unifikasi + literal negatif sebagai negation-as-failure) ke waktu t+1.
- **ASK(KB, Query)**: `ask_cost(x,y,t)` dan `ask_safe(x,y,t)`; `ask(x,y,t) = (aman?, biaya)`.
  Inferensi *backward chaining* (resolusi SLD). Langkah **tidak aman** = `Unsafe` = biaya 5.
- **Semantik biaya** = biaya **terbesar yang terbukti** (CNF hanya menurunkan batas bawah; R7 memberi dasar 1).
- Hasil nyata: `ASK DeepRiver(0,13) → aman=False, biaya=5`; `ASK Rock(2,12) → aman=True, biaya=1`.

## 3. Perencanaan otomatis — PDDL (Modul 08)

`PDDL_DOMAIN` memuat aksi `STEP_ON_WOOD` persis seperti spesifikasi (precondition `at`, `wood-at`,
`wood-floating`, `adj`; efek `at`, ¬`at from`, ¬`wood-floating`, `wood-sunk`) plus `MOVE` (aksi umum) dan
`MOVE` ke kayu yang sedang tenggelam (biaya 5). `plan_pddl` memakai **A\* atas ruang state STRIPS**
(state = himpunan atom; aksi diterapkan lewat pre/add/delete), heuristik Chebyshev (admissible).
`to_pddl_problem` menghasilkan file masalah PDDL standar untuk planner eksternal.

**Replanning trigger.** Saat biaya berubah (pasang berganti / kayu diinjak atau tenggelam) KB menaikkan
`version`; `Game._on_cost_update()` membuang rute otomatis dan cache pencarian, sehingga rute dihitung
ulang (PDDL/A*/MEU sesuai planner aktif). Di eksperimen 4 peta, 10–11 replanning terjadi dalam 16–20 langkah.

Hasil: biaya rencana PDDL **= biaya A\* di 80/80 peta uji** (keduanya optimal atas biaya yang sama); PDDL
menambah kemampuan memodelkan efek tenggelamnya kayu di dalam satu rencana. Waktu: ±10–16 ms rencana
pertama (grounding), 1–3 ms per tick sesudahnya (aksi ter-cache).

## 4. Keputusan di bawah ketidakpastian — MDP / MEU (Modul 09)

| Komponen | Definisi (asumsi implementasi) |
|---|---|
| S | (sel, pasang) dengan pasang ∈ {rendah, tinggi} |
| A | gerak ke tetangga (4/8 arah mengikuti pengaturan diagonal) |
| T | gerak deterministik; pasang berantai Markov: P(rendah→tinggi)=0.20, P(tinggi→rendah)=0.30 (P(tinggi) jangka panjang = 0.40) |
| R | −biaya(sel tujuan \| pasang saat tiba) × (√2 bila diagonal); +60 di tujuan |
| γ | 0.97 |

Kebijakan **MEU**: `argmax_a Σ T·[R + γV]`, dihitung dengan *value iteration* (±27 iterasi, 12–40 ms). Kayu
mengapung dihitung biaya 1 dan kayu tenggelam 5 menurut KB saat ini (aproksimasi: tiap kayu dilewati sekali).
Di game, MEU dijalankan sebagai **kebijakan closed-loop**: rute dihitung ulang saat pasang berganti.

**Evaluasi jujur (Monte Carlo, N=300 peta & urutan pasang acak, biaya terealisasi, replan tiap langkah):**

| Planner | Biaya rata-rata | Langkah rata-rata |
|---|---|---|
| A\* (biaya pasang saat ini) | 19.96 | 16.1 |
| MEU (MDP) | **19.52** | 15.4 |

MEU lebih murah di 114 peta, sama di 156, lebih mahal di 30; selisih rata-rata **0.45 ± 0.07 (1 SE)**, ±2.2%.
Penghematannya **kecil tapi signifikan**: tepi pasang ada di semua baris kecuali jembatan batu, sehingga
pilihan antar-rute jarang berbeda jauh. Metrik "harapan" pada panel **J** adalah biaya-harapan sebuah
*jalur tetap* (open-loop), jadi MEU tidak selalu tampak lebih murah di panel itu walau kebijakannya
closed-loop lebih hemat.

## 5. Integrasi ke game

- Musuh tidak lahir di tile sungai. **Siapa pun** (pemain/musuh) yang menginjak kayu memicu
  `TELL(SteppedOn)`; kayu tenggelam di t+1 dan toast muncul.
- Mode Otomatis memakai planner terpilih (**U**: PDDL → A\* → MEU); lencana kiri-atas menampilkan pasang,
  `t`, planner, dan jumlah kayu apung/tenggelam. Tile digambar prosedural (pasir saat surut, biru saat
  pasang, batu, kayu, kayu tenggelam).
- Tooltip debug menampilkan nama tile sungai dan biayanya saat ini.

## 6. Pengujian & batasan

`python -m unittest discover -s tests -v` (44 tes, ±1 detik): matriks biaya, bentuk sungai organik (berkelok,
lebar bervariasi, jembatan batu bersambung), R1–R5 (termasuk tenggelam di t+1 dan aksioma bingkai), **kayu muncul lagi tepat setelah 5 turn dan bisa diinjak ulang**, **biaya turn = biaya tile** (rumput 1, sungai dalam 5, kayu 1), musuh menunggu sesuai biaya tile, TELL/ASK,
tampilan CNF, distribusi stasioner pasang (±0.04), rencana PDDL = Dijkstra,
efek STRIPS `STEP_ON_WOOD`, replanning setelah kayu tenggelam, MDP konvergen dan kebijakan mencapai tujuan.

Batasan: (1) definisi tuple MDP & aksi `MOVE` adalah asumsi (lihat atas); (2) tide stokastik, bukan
periodik; (3) MDP dan planner PDDL memperlakukan kayu yang tenggelam sebagai tetap tenggelam selama horizon rencana (konservatif; rute dihitung ulang saat kayu muncul lagi); (4) belum diuji dengan pemain manusia.
