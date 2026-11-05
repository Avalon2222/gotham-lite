# Belajar dari Gotham Lite

Panduan ini menjelaskan konsep di balik aplikasi, dari format data sampai algoritma graf, dengan potongan kode dari
repo. Bacalah berurutan; setiap bagian berdiri sendiri tetapi memakai istilah dari bagian sebelumnya.

## 1. Apa itu analisis keterkaitan (link analysis)?

Analisis keterkaitan adalah cara melihat data sebagai **graf**: benda (orang, perusahaan, kapal) menjadi **simpul**
(*node*), hubungan di antaranya (memiliki, mengurus, keluarga) menjadi **sisi** (*edge*). Begitu data berbentuk graf,
pertanyaan yang sulit dijawab dengan tabel menjadi mudah:

| Pertanyaan | Istilah graf | Fungsi di `src/graf.py` |
|---|---|---|
| Siapa saja yang terhubung ke X? | tetangga, ego-graf | `tetangga()`, `ego()` |
| Lewat siapa A sampai ke B? | jalur terpendek | `jalur_terpendek()`, `ceritakan_jalur()` |
| Siapa pemilik di balik pemilik kapal ini? | penelusuran ke atas (DFS) | `rantai_pemilik()` |
| Siapa simpul paling sibuk? | derajat, hub | `peringkat_hub()` |
| Kelompok mana yang saling terpisah? | komponen terhubung | `ukuran_komponen()` |
| Siapa yang belum terdaftar tetapi dekat? | paparan | `paparan()` |

Perangkat komersial (Palantir Gotham, i2 Analyst's Notebook, Maltego) menambahkan banyak hal lain, tetapi intinya tetap
enam pertanyaan di atas.

## 2. Format data: FollowTheMoney

OpenSanctions menyimpan semuanya dalam **FollowTheMoney (FtM)**, skema yang dirancang untuk jurnalisme investigasi.
Setiap baris berkas `entities.ftm.json` adalah satu entitas:

```json
{"id": "NK-abc", "schema": "Person", "caption": "Oligarki Besar",
 "properties": {"name": ["Oligarki Besar"], "birthDate": ["1960-01-01"], "topics": ["sanction"],
                "country": ["ru"], "programId": ["EU-RUS"]},
 "datasets": ["eu_fsf", "gb_fcdo_sanctions"]}
```

Hal penting: **relasi juga entitas**. `Ownership` punya properti `owner` dan `asset`; `Directorship` punya `director`
dan `organization`; `Family` punya `person` dan `relative`. Masing-masing berisi *id* entitas lain. Jadi untuk membangun
graf, cukup ubah setiap entitas relasi menjadi sisi `sumber -> tujuan`:

```python
RELASI = {"Ownership": ("owner", "asset"), "Directorship": ("director", "organization"),
          "Family": ("person", "relative"), "UnknownLink": ("subject", "object"), ...}

def baris_relasi(e):
    k_sumber, k_tujuan = RELASI[e["schema"]]
    for s in e["properties"][k_sumber]:
        for t in e["properties"][k_tujuan]:
            yield {"sumber": s, "tujuan": t, "tipe": e["schema"], ...}
```

Properti `topics` memberi tahu *mengapa* sebuah entitas ada di OpenSanctions: `sanction` (disanksi langsung),
`sanction.linked` (terkait pihak tersanksi), `role.pep` (pejabat publik), `crime`, `debarment`, dan lain-lain.
Aplikasi ini memakai topik sanksi sebagai **benih** graf.

## 3. Memproses 2,5 GB tanpa kehabisan memori

Koleksi *default* OpenSanctions berisi 3,9 juta baris. Memuatnya ke pandas sekaligus butuh belasan GB RAM. Solusinya:
baca baris demi baris (**streaming**) dan hanya simpan yang perlu, dalam **dua lintasan**:

1. **Lintasan 1**: simpan id entitas bertopik sanksi (±123 ribu id, kecil) dan semua relasi (±400 ribu dict kecil).
2. Saring relasi: hanya yang menyentuh benih. Hitung himpunan id simpul yang dibutuhkan.
3. **Lintasan 2**: baca ulang berkas, tulis baris CSV untuk id yang dibutuhkan saja.

```python
def _iter_entitas(path):
    with open(path, encoding="utf-8") as f:
        for baris in f:              # satu baris = satu entitas; memori tetap kecil
            yield json.loads(baris)
```

Dua lintasan atas 2,5 GB memang membaca berkas dua kali, tetapi masing-masing hanya ±40 detik dan memori puncaknya di
bawah 1 GB. Ini pola umum untuk data yang lebih besar dari RAM.

## 4. Masalah hub dan pemangkasan

Percobaan pertama menghasilkan 228 ribu simpul, dan 139 ribu di antaranya perusahaan Rusia dari register EGRUL. Sebabnya:
kementerian Rusia yang disanksi tercatat "memiliki" ribuan badan usaha negara, dan badan usaha itu saling memiliki lagi.
Secara teknis benar, tetapi tidak menambah cerita dan membuat graf tidak terbaca.

Tiga aturan pemangkasan di `saring_relasi()`:

1. Relasi dari dataset pengayaan (`ext_*`) hanya disimpan bila salah satu ujungnya **orang atau kapal** tersanksi
   (oligarki → perusahaannya, kapal → pemiliknya), bukan lembaga → anak usahanya.
2. Setiap benih menyimpan paling banyak **60 tetangga yang tidak tersanksi**; relasi antar-benih selalu disimpan.
3. Duplikat (sumber, tujuan, tipe, peran) dibuang.

Hasilnya 85 ribu simpul dan 97 ribu relasi (10 MB terkompresi). Pemangkasan selalu punya harga: hub besar tampak lebih
kecil dari aslinya, dan itu ditulis terang-terangan di tab Data & Sources.

## 5. Graf di networkx

```python
G = nx.MultiDiGraph()                       # berarah, boleh sisi ganda (memiliki + mengurus)
G.add_nodes_from((i, {"tipe": t, "nama": n, "tersanksi": s}) for ...)
G.add_edge(sumber, tujuan, key=id_relasi, tipe="Ownership", peran="Shareholder", persen=60.0)
H = nx.Graph(G)                             # versi tak berarah untuk BFS dan jalur
```

Mengapa dua graf? Arah penting saat *membaca* relasi ("A memiliki B"), tetapi tidak penting saat bertanya "apakah A
terhubung ke B". Graf tak berarah juga lebih cepat untuk BFS dan `connected_components`.

Atribut simpul sengaja minimal (tipe, nama, tersanksi). Atribut lain (alias, program, IMO) dibaca dari DataFrame lewat
id. Dengan 85 ribu simpul, ini menghemat ratusan MB memori.

## 6. Ego-graf dengan BFS berprioritas

**BFS** (*breadth-first search*) menelusuri lapis demi lapis: pusat, lalu semua tetangga pusat, lalu tetangga dari
tetangga. Versi di `ego()` menambah dua hal: batas jumlah simpul dan **prioritas** saat satu lapis terlalu besar.

```python
def _prioritas(H, n):
    d = H.nodes[n]
    return (-d["tersanksi"], PRIORITAS_TIPE.get(d["tipe"], 9), -H.degree(n), n)
    #        tersanksi dulu   kapal/orang dulu                 paling sibuk dulu   id (agar deterministik)
```

Kunci pengurutan berupa *tuple*: Python membandingkan elemen pertama, lalu kedua bila seri, dan seterusnya. Elemen
terakhir (id) memastikan hasil selalu sama untuk masukan yang sama, penting agar tampilan tidak "melompat" saat halaman
dirender ulang.

Tetangga yang tidak ikut ditampilkan dihitung oleh `jumlah_tersembunyi()` dan ditulis sebagai `(+n)` di label simpul,
lalu bisa dibuka dengan `perluas()`. Inilah pola "expand node" yang dipakai semua perangkat analisis keterkaitan.

## 7. Jalur terpendek dan jalur alternatif

Untuk graf tak berbobot, jalur terpendek dihitung BFS dari kedua ujung (`nx.shortest_path`). Untuk beberapa jalur
alternatif, `nx.shortest_simple_paths` memakai **algoritma Yen**: cari jalur terpendek, lalu berulang kali "melarang"
satu sisi dari jalur sebelumnya untuk menemukan jalur berikutnya. Karena jalur dihasilkan satu per satu (generator),
kita bisa berhenti kapan saja:

```python
for jalur in nx.shortest_simple_paths(H, a, b):
    if len(jalur) - 1 > maks_panjang:
        break
    hasil.append(jalur)
    if len(hasil) >= maks_jalur:
        break
```

`ceritakan_jalur()` mengubah daftar id menjadi kalimat dengan membaca relasi asli dari `G` (yang berarah), sehingga
"Holding Utama memiliki 60% Tanker Alpha" selalu ditulis dengan arah yang benar, apa pun arah penelusurannya.

## 8. Rantai kepemilikan: DFS ke atas

Untuk kapal, pertanyaannya "siapa di balik pemilik?" bukan "siapa tetangganya". `rantai_pemilik()` hanya mengikuti
sisi **masuk** bertipe Ownership, Directorship, Representation, UnknownLink, dengan **DFS** (*depth-first search*)
rekursif yang membawa jejaknya:

```python
def telusur(n, jejak, terlihat):
    atas = [(u, d["tipe"]) for u, _, d in G.in_edges(n, data=True) if d["tipe"] in DIIKUTI and u not in terlihat]
    if not atas or len(jejak) >= maks_hop:
        rantai.append(jejak); return
    for u, t in atas:
        telusur(u, jejak + [(u, t)], terlihat | {u})
```

`terlihat` mencegah putaran (A memiliki B, B memiliki A), dan `maks_hop` mencegah ledakan jumlah rantai.

## 9. Ukuran jaringan

- **Derajat**: jumlah sisi sebuah simpul. Distribusinya "ekor panjang": kebanyakan simpul berderajat 1–2, segelintir
  berderajat ratusan. Graf sosial dan graf perusahaan hampir selalu begini.
- **Komponen terhubung**: `nx.connected_components(H)`. Graf sanksi punya ribuan komponen kecil dan satu raksasa.
- **Paparan**: untuk simpul tak tersanksi, jumlah tetangga tersanksi. Ini versi paling sederhana "risiko menular".
  Versi lanjutannya memakai **PageRank berpersonalisasi** dengan vektor awal di simpul tersanksi, sehingga risiko
  mengalir beberapa lapis dengan bobot mengecil.

Catatan penting: semua ukuran ini mengukur **struktur data**, bukan kesalahan. Badan klasifikasi kapal punya paparan
tinggi karena ia memeriksa ribuan kapal, bukan karena ia bersalah.

## 10. Cytoscape di dalam Streamlit

Plotly bisa menggambar graf, tetapi tidak mengembalikan simpul yang diklik dan tidak punya tata letak gaya
(*force-directed*) yang dihitung di browser. **Cytoscape.js** dibuat khusus untuk graf. Komponen `st-link-analysis`
membungkusnya untuk Streamlit:

```python
st_link_analysis(elemen, layout="fcose", node_styles=GAYA_SIMPUL, edge_styles=GAYA_RELASI,
                 key="graf_utama", on_change=aksi_graf, node_actions=["remove", "expand"],
                 events=[Event("klik_simpul", "tap", "node")])
```

Alurnya: Python mengirim `{"nodes": [...], "edges": [...]}`, JavaScript menggambar dan menangani zoom/drag, dan setiap
peristiwa dikirim balik sebagai `{"action": "klik_simpul", "data": {"target_id": ...}}`. Callback `aksi_graf()`
memperbarui `st.session_state` (simpul terpilih, daftar simpul tampil), lalu Streamlit merender ulang halaman.
Prinsipnya: **JavaScript menggambar, Python memegang keadaan.**

Gaya simpul bawaan komponen memakai huruf 3,6 px dan menyembunyikan label bila terlalu kecil
(`min-zoomed-font-size: 10`). Kelas `GayaSimpul` di `app.py` menimpanya lewat selector `node[label='Person']` yang
lebih spesifik, cara yang sama seperti CSS.

## 11. AIS dan MMSI

**AIS** (*Automatic Identification System*) adalah siaran radio VHF yang wajib dipancarkan kapal besar: identitas,
posisi, kecepatan, haluan. Tiga identitas kapal yang perlu dibedakan:

| Identitas | Sifat | Dipakai untuk |
|---|---|---|
| **IMO** | 7 digit, melekat seumur hidup pada lambung | identitas utama di daftar sanksi |
| **MMSI** | 9 digit, identitas radio; berubah bila ganti bendera | pencocokan dengan pesan AIS |
| Nama / call sign | mudah diganti | petunjuk tambahan |

aisstream.io meneruskan pesan AIS dari ribuan penerima sukarelawan lewat WebSocket. Aplikasi berlangganan seluruh dunia,
menyaring pesan yang `MMSI`-nya ada di himpunan kapal tersanksi, dan menyimpan posisi terakhir per kapal. Kapal yang
mematikan AIS (praktik umum armada bayangan) tidak akan muncul, dan ketiadaan sinyal itu sendiri informasi.

## 12. Membaca hasil dengan hati-hati

- Nama di graf **bukan bukti**. Banyak entitas tak tersanksi hadir karena satu relasi netral.
- Data gabungan mengandung duplikat dan transliterasi ganda (Rotenberg/Rottenberg).
- `UnknownLink` berarti sumber menyebut keterkaitan tanpa jenis.
- Snapshot adalah potret satu hari; sanksi ditambah dan dicabut setiap minggu.

Kalau ingin menambah kemampuan, tiga arah yang masuk akal: PageRank berpersonalisasi, deteksi komunitas (Louvain) untuk
mewarnai gugus di komponen raksasa, dan linimasa tanggal relasi. Lihat `docs/LATIHAN.md`.
