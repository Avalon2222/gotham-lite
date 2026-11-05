# Sumber data

Semua berkas di folder ini dibuat oleh `scripts/bangun_data.py` dan dibaca aplikasi tanpa internet.

## OpenSanctions, koleksi *default*

- **URL:** https://data.opensanctions.org/datasets/latest/default/entities.ftm.json (±2,5 GB, JSON Lines, format FollowTheMoney)
- **Indeks dataset:** https://data.opensanctions.org/datasets/latest/index.json
- **Isi:** ±3,9 juta entitas dari 500 dataset: daftar sanksi resmi (OFAC AS, Uni Eropa, OFSI Inggris, DK PBB, NSDC Ukraina,
  SECO Swiss, Kanada, Australia, Jepang, dan lain-lain), daftar PEP, daftar wanted, pengecualian pengadaan, serta
  pengayaan dari register perusahaan (EGRUL Rusia, Companies House, GLEIF, ICIJ Offshore Leaks, OpenCorporates) dan Wikidata.
- **Lisensi:** CC BY-NC 4.0 untuk penggunaan non-komersial dengan atribusi; penggunaan komersial memerlukan lisensi dari
  OpenSanctions (https://www.opensanctions.org/licensing/).
- **Pembaruan:** OpenSanctions memperbarui koleksi beberapa kali sehari; repo ini membangun ulang snapshot tiap tanggal 1
  lewat GitHub Actions (`.github/workflows/perbarui-data.yml`). Tanggal snapshot ada di `META.json`.

## Berkas

### `simpul.csv.gz` (satu baris per entitas)

| Kolom | Isi |
|---|---|
| `id` | id OpenSanctions (`NK-...`, `Q...` untuk Wikidata, atau id sumber); profil: `https://www.opensanctions.org/entities/<id>/` |
| `tipe` | skema FtM: Person, Company, Organization, LegalEntity, PublicBody, Vessel, Airplane, Asset |
| `nama` | `caption` OpenSanctions (nama yang dipilih dari semua nama yang tersedia) |
| `alias` | sampai 3 nama lain, dipisah `; ` |
| `negara` | gabungan unik `country`, `jurisdiction`, `citizenship`, `nationality`, `flag` (kode ISO-2, dipisah `; `) |
| `topik` | topik OpenSanctions (`sanction`, `sanction.linked`, `role.pep`, ...) |
| `dataset` | id dataset sumber, dipisah `; ` (judul lengkap di `dataset.csv`) |
| `program` | sampai 6 `programId` (misalnya `US-SDN`, `EU-RUS`, `GB-RUS`) |
| `tanggal` | tanggal lahir (orang) / pendirian (badan) / pembuatan (kapal), apa adanya dari sumber |
| `jabatan` | sampai 2 `position` (orang) |
| `imo`, `mmsi`, `bendera`, `jenis_kapal` | khusus kapal; `imo` tanpa awalan "IMO" |
| `tersanksi` | 1 bila topik termasuk sanction / sanction.linked / sanction.counter / export.control |
| `catatan` | 240 huruf pertama `notes` / `description` / `summary` |
| `url_sumber` | `sourceUrl` pertama |
| `pertama_terlihat`, `terakhir_berubah` | tanggal dari OpenSanctions |

### `relasi.csv.gz` (satu baris per pasangan sumber → tujuan)

| Kolom | Isi |
|---|---|
| `id` | id entitas relasi di OpenSanctions |
| `sumber`, `tujuan` | id simpul; arah mengikuti skema FtM (owner → asset, director → organization, person → relative, employee → employer, agent → client, subject → object) |
| `tipe` | Ownership, Directorship, Membership, Employment, Family, Associate, Representation, UnknownLink |
| `peran` | `role` / `relationship` / `summary` (dipotong 120 huruf) |
| `mulai`, `selesai` | `startDate`, `endDate` bila ada |
| `dataset` | dataset sumber pertama |
| `persen` | `percentage` kepemilikan bila ada |

### `kapal_tersanksi.csv`

Ringkasan satu baris per kapal tersanksi (turunan dari dua berkas di atas): nama, bendera, jenis, IMO, MMSI, tahun
dibangun, program, dataset, pemilik/operator yang tercatat lewat relasi masuk, jumlah relasi, dan tanggal pertama
terlihat. Berkas CSV biasa agar mudah dipakai proyek lain.

### `dataset.csv`

Judul, penerbit, negara penerbit, URL, dan jumlah simpul/relasi untuk setiap id dataset yang muncul di graf.

### `META.json`

Tanggal pembangunan, jumlah simpul dan relasi, rincian per tipe, jumlah benih tersanksi, jumlah dataset.

## Aturan pemangkasan

1. **Benih** = entitas bertopik `sanction`, `sanction.linked`, `sanction.counter`, atau `export.control`.
2. Relasi disimpan bila menyentuh minimal satu benih.
3. Relasi dari dataset pengayaan `ext_*` disimpan hanya bila salah satu ujung tersanksinya **orang atau kapal**.
4. Setiap benih menyimpan paling banyak **60 tetangga tidak tersanksi**; relasi antar-benih selalu disimpan.
5. Relasi `Succession` (pergantian badan hukum) dan `Occupancy` (jabatan PEP) tidak dimuat.
6. Simpul yang ditulis = benih yang punya relasi + semua tetangganya. Entitas tersanksi tanpa relasi tidak dimuat.

Angka hasil pemangkasan pada snapshot saat ini ada di `META.json`.

## aisstream.io (opsional, tidak disimpan di repo)

- **URL:** wss://stream.aisstream.io/v0/stream, kunci API gratis dengan akun GitHub.
- **Dipakai untuk:** tab Live AIS, berlangganan sampai 200 MMSI kapal tersanksi per sesi (`FiltersShipMMSI`) dan
  mencatat laporan posisi (PositionReport, StandardClassBPositionReport) selama beberapa puluh detik. Tidak ada data AIS
  yang disimpan di repo.
