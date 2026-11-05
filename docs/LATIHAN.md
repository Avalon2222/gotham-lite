# Latihan

Latihan bertingkat untuk memahami dan mengembangkan Gotham Lite. Setiap latihan menyebut berkas yang perlu dibaca dan
petunjuk cara memeriksa hasil. Kerjakan berurutan; tingkat lanjut mengandaikan tingkat dasar sudah selesai.

## Tingkat 1: membaca data

**1.1 Hitung sendiri.** Dengan pandas, muat `data/simpul.csv.gz` dan jawab: berapa kapal berbendera Panama? Berapa persen
orang tersanksi yang punya tanggal lahir? Negara mana yang paling sering muncul di kolom `negara`?
*Petunjuk:* `pd.read_csv(..., dtype=str, keep_default_na=False)`; kolom `negara` berisi beberapa kode dipisah `; `.

**1.2 Relasi paling umum per dataset.** Dari `data/relasi.csv.gz`, buat tabel silang `dataset` × `tipe`. Dataset mana yang
menyumbang hampir semua `Directorship`? Mengapa masuk akal?

**1.3 Baca satu entitas FtM.** Buka profil salah satu entitas di OpenSanctions (tautan ada di panel detail aplikasi) dan
cocokkan properti yang tampil di situs dengan kolom di `simpul.csv.gz`. Kolom mana yang "hilang" karena sengaja tidak
disalin oleh `baris_simpul()`?

## Tingkat 2: graf

**2.1 Tetangga tersembunyi.** Dengan `src/graf.py`, hitung ego-graf radius 1 untuk "Arkady Romanovich Rotenberg" dengan
`maks_simpul=20` lalu `maks_simpul=200`. Simpul mana yang muncul hanya pada batas 200? Jelaskan dari `_prioritas()`
mengapa mereka tersisih lebih dulu.

**2.2 Jalur baru.** Cari dua nama terkenal yang menurut kamu tidak berhubungan, lalu uji dengan `jalur_terpendek()`
pada panjang maksimum 8. Kalau ada jalur, bacakan dengan `ceritakan_jalur()` dan nilai: apakah jalur itu bermakna atau
hanya lewat hub netral (partai, badan klasifikasi)?

**2.3 Komponen kedua.** Komponen terbesar punya 22 ribu simpul; komponen kedua ±1.160. Temukan komponen kedua
(`nx.connected_components`), lihat negara dan dataset yang dominan, dan tebak "tentang apa" komponen itu.

**2.4 Uji baru.** Tambahkan satu tes di `tests/test_graf.py` untuk `perluas()` yang memastikan simpul pusat tidak pernah
dihapus oleh `sembunyikan()` di `app.py` (pindahkan logikanya ke `src/graf.py` dahulu agar bisa diuji).

## Tingkat 3: aplikasi

**3.1 Kasus siap pakai baru.** Tambahkan satu tombol di daftar `KASUS` di `app.py` (misalnya jaringan Hizbullah atau
kartel Sinaloa). Pastikan nama yang kamu pakai ditemukan oleh `cari_id()`; kalau ada beberapa entitas dengan nama sama,
pakai argumen `tipe`.

**3.2 Filter tipe di explorer.** Tambahkan multiselect di sidebar untuk menyembunyikan tipe tertentu (misalnya semua
perusahaan) dari graf tanpa mengubah `ss.tampil`. *Petunjuk:* saring `ids` sebelum `elemen_cytoscape()`, tetapi jangan
saring pusatnya.

**3.3 Sorot jalur di explorer.** Saat pengguna menekan "Buka jalur ini di Explorer", beri warna berbeda pada sisi yang
termasuk jalur. *Petunjuk:* beri `label` sisi khusus (misalnya `"Ownership_jalur"`) dan tambahkan `GayaRelasi` untuknya.

**3.4 Peta bendera.** Di tab Shadow fleet, tambahkan choropleth dunia jumlah kapal tersanksi per negara bendera
(`px.choropleth`, `locationmode="ISO-3"`). Kamu perlu tabel konversi ISO-2 → ISO-3; `pycountry` membantu.

## Tingkat 4: data dan algoritma

**4.1 Benih yang berbeda.** Ubah `TOPIK_BENIH` di `scripts/bangun_data.py` menjadi `{"role.pep"}` dan bangun ulang dari
satu dataset kecil (misalnya `wd_peps`). Bagaimana ukuran dan bentuk grafnya berubah? Mengapa PEP menghasilkan jauh
lebih banyak relasi `Family` dan `Membership`?

**4.2 PageRank berpersonalisasi.** Hitung `nx.pagerank(H, personalization={n: 1 for n in tersanksi})` dan bandingkan
20 simpul tak tersanksi teratas dengan hasil `paparan()`. Mana yang lebih masuk akal sebagai "risiko menular"? Tulis
temuanmu di README.

**4.3 Deteksi komunitas.** Jalankan `nx.community.louvain_communities` pada komponen terbesar. Beri warna komunitas di
Cytoscape (label simpul = nomor komunitas). Apakah komunitas yang ditemukan sejalan dengan negara?

**4.4 Linimasa relasi.** Kolom `mulai` dan `selesai` di `relasi.csv.gz` sering kosong, tetapi `pertama_terlihat` di
simpul selalu ada. Buat grafik jumlah entitas tersanksi baru per bulan sejak 2022 dan tandai lonjakan terbesar.

## Tingkat 5: rekayasa

**5.1 Cache yang benar.** `muat()` memakai `st.cache_resource` sedangkan statistik memakai `st.cache_data`. Jelaskan
perbedaannya dan apa yang terjadi bila keduanya ditukar (petunjuk: graf networkx tidak bisa di-*pickle* dengan murah).

**5.2 Action bulanan.** `perbarui-data.yml` mengunduh 2,5 GB tiap bulan. Ubah agar skrip memeriksa `version` di
`index.json` OpenSanctions dahulu dan berhenti bila sama dengan `META.json`.

**5.3 Ekspor GraphML.** Tambahkan tombol di tab Data & Sources untuk mengunduh subgraf yang sedang tampil sebagai
GraphML (`nx.write_graphml`) agar bisa dibuka di Gephi.

**5.4 Live AIS yang tahan banting.** `ais.dengarkan()` memblokir selama 30–90 detik. Pindahkan ke thread latar dengan
hasil disimpan di `st.session_state`, dan tampilkan indikator kemajuan per 5 detik.
