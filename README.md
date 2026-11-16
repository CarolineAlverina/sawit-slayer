# Sawit Slayer

Pemadam kebakaran menebang pohon sawit di labirin hutan sambil dikejar monster api
(Hellish Banban). Monster mengejar memakai **A\*** atau **GBFS** (heuristic Manhattan).
Saat pemain mengambil air, monster berubah menjadi Baby Banban dan bisa dikalahkan, lalu
muncul papan informasi tentang karhutla.

## Menjalankan
Disarankan Python 3.10 - 3.12.
```
python -m pip install ursina
python main3d.py
```

## Kontrol
| Tombol | Fungsi |
|---|---|
| W / panah atas | Maju (arah hadap) |
| A / panah kiri, D / panah kanan | Belok kiri / kanan (kamera belakang) |
| S / panah bawah | Putar balik |
| TAB (1 / 2) | Ganti algoritma A* / GBFS |
| V | Visualisasi jalur dan node yang dieksplorasi |
| C | Ganti kamera: belakang pemadam / dari atas (pada kamera atas, WASD = arah mata angin) |
| Enter | Mulai / main lagi |

Tombol di header: **Back** (ke menu), **Pause** (popup Paused: Play, Restart, Settings, Quit), **Settings**.
Settings: algoritma pengejar dan tingkat kesulitan (Easy/Medium/Hard). Kesulitan berlaku di permainan berikutnya.
Toggle **Music** dan **Sound** di Settings mengatur musik latar dan efek suara.

## Aturan
- Tebang semua sawit untuk menang; nyawa (3) habis = kalah.
- 4 monster muncul di awal. Air aktif 8 detik: monster menjadi Baby Banban, melambat, dan menghindar.
- Skor: sawit 10, air 50, monster 200.

## Struktur
```
main3d.py        tampilan 3D, kamera, HUD, minimap, menu
sound.py         pengelola musik dan efek suara
core.py          logika game       pathfinding.py  A*, GBFS, benchmark     level.py  denah labirin
models/*.json    model hasil konversi (animasi sudah dibakar per frame)
textures/ ui/ fonts/ audio/
tools/           build_assets.py (poly.zip -> models, textures, ui), convert_models.py, build_ui.py, build_audio.py (membuat audio/)
```

## Mengganti aset
`pip install numpy pillow` lalu `python tools/build_assets.py poly.zip`.

## Kredit
Kenney Nature Kit (CC0), font Chau Philomene One (OFL), model Garten of Banban, model pemadam, pedang (Kenney.nl)
