import pandas as pd

from src import graf


def test_bangun_graf_ukuran(G, H):
    assert G.number_of_nodes() == 8
    assert G.number_of_edges() == 7
    assert H.number_of_edges() == 7
    assert G.nodes["V1"]["tipe"] == "Vessel"
    assert G.nodes["C2"]["tersanksi"] == 0


def test_relasi_tanpa_simpul_diabaikan(simpul_kecil, relasi_kecil):
    r = pd.concat([relasi_kecil, pd.DataFrame([{"id": "rx", "sumber": "P1", "tujuan": "TIDAK-ADA", "tipe": "Ownership",
                                                 "peran": "", "mulai": "", "selesai": "", "dataset": "", "persen": None}])])
    G2 = graf.bangun_graf(simpul_kecil, r)
    assert G2.number_of_edges() == 7


def test_cari_nama_alias_imo_mmsi(simpul_kecil, H):
    deg = graf.derajat(H)
    assert graf.cari(simpul_kecil, "oligarki", deg).index[0] == "P1"          # diawali teks -> paling atas
    assert "P2" in graf.cari(simpul_kecil, "oligarki", deg).index               # 'Anak Oligarki' juga cocok
    assert graf.cari(simpul_kecil, "o. besar", deg).index.tolist() == ["P1"]   # alias
    assert graf.cari(simpul_kecil, "9000001", deg).index.tolist() == ["V1"]    # IMO
    assert graf.cari(simpul_kecil, "538000002", deg).index.tolist() == ["V2"]  # MMSI
    assert graf.cari(simpul_kecil, "x", deg).empty                             # terlalu pendek
    assert graf.cari(simpul_kecil, "tidak ada sama sekali", deg).empty


def test_cari_saring_tipe(simpul_kecil, H):
    hasil = graf.cari(simpul_kecil, "ka", graf.derajat(H), tipe="Vessel")
    assert set(hasil["tipe"]) == {"Vessel"}


def test_tetangga_arah_dan_urutan(G):
    t = graf.tetangga(G, "C1")
    assert len(t) == 3
    arah = {(b["id"], b["arah"]) for b in t}
    assert ("P1", "masuk") in arah and ("V1", "keluar") in arah and ("C2", "keluar") in arah
    # tersanksi dahulu, lalu kapal sebelum orang, orang sebelum perusahaan
    assert [b["id"] for b in t][:2] == ["V1", "P1"]
    assert graf.tetangga(G, "TIDAK-ADA") == []


def test_ego_radius_dan_batas(H):
    assert graf.ego(H, "P1", 1)[0] == "P1"
    assert set(graf.ego(H, "P1", 1)) == {"P1", "C1", "P2", "O1"}
    assert set(graf.ego(H, "P1", 2)) == {"P1", "C1", "P2", "O1", "V1", "C2"}
    terbatas = graf.ego(H, "P1", 1, maks_simpul=3)
    assert len(terbatas) == 3 and terbatas[0] == "P1"
    assert "C1" in terbatas and "O1" in terbatas    # yang tersanksi diprioritaskan daripada P2
    assert graf.ego(H, "TIDAK-ADA") == []


def test_perluas_dan_tersembunyi(H):
    tampil = graf.ego(H, "P1", 1)
    assert graf.jumlah_tersembunyi(H, tampil)["C1"] == 2
    tampil2 = graf.perluas(H, tampil, "C1")
    assert set(tampil2) == set(tampil) | {"V1", "C2"}
    assert graf.jumlah_tersembunyi(H, tampil2)["C1"] == 0
    assert graf.perluas(H, tampil, "C1", maks_tambahan=1) == tampil + ["V1"]   # kapal diprioritaskan


def test_elemen_cytoscape(G, simpul_kecil, H):
    ids = graf.ego(H, "P1", 1)
    el = graf.elemen_cytoscape(G, simpul_kecil, ids, graf.jumlah_tersembunyi(H, ids), pusat="P1")
    assert {n["data"]["id"] for n in el["nodes"]} == set(ids)
    assert len(el["edges"]) == 3
    data_p1 = next(n["data"] for n in el["nodes"] if n["data"]["id"] == "P1")
    assert data_p1["label"] == "Person" and data_p1["pusat"] == "ya" and data_p1["negara"] == "Rusia"
    data_p2 = next(n["data"] for n in el["nodes"] if n["data"]["id"] == "P2")
    assert data_p2["label"] == "Person_luar" and data_p2["tersanksi"] == "tidak"
    sisi = next(e["data"] for e in el["edges"] if e["data"]["source"] == "P1" and e["data"]["target"] == "C1")
    assert sisi["keterangan"] == "memiliki 60% · Shareholder"
    # sisi yang salah satu ujungnya tidak ditampilkan tidak ikut
    assert all(e["data"]["source"] in ids and e["data"]["target"] in ids for e in el["edges"])


def test_teks_relasi():
    assert graf.teks_relasi({"tipe": "Ownership", "persen": 51.0, "peran": ""}) == "memiliki 51%"
    assert graf.teks_relasi({"tipe": "Family", "persen": None, "peran": "spouse"}) == "keluarga dari · spouse"
    assert graf.teks_relasi({"tipe": "UnknownLink"}) == "terkait dengan"


def test_jalur_terpendek_dan_cerita(G, H):
    jalur = graf.jalur_terpendek(H, "P1", "V1")
    assert jalur[0] == ["P1", "C1", "V1"]
    cerita = graf.ceritakan_jalur(G, jalur[0])
    assert cerita == ["Oligarki Besar memiliki 60% · Shareholder Holding Utama", "Holding Utama memiliki · Registered owner Tanker Alpha"]
    # dua jalur ke Toko Roti: lewat Holding dan lewat Anak
    assert len(graf.jalur_terpendek(H, "P1", "C2", maks_jalur=3)) == 2
    assert graf.jalur_terpendek(H, "P1", "V2") == []          # komponen berbeda
    assert graf.jalur_terpendek(H, "P1", "P1") == []
    assert graf.jalur_terpendek(H, "P1", "V1", maks_panjang=1) == []


def test_rantai_pemilik(G):
    rantai = graf.rantai_pemilik(G, "V1")
    assert rantai == [[("C1", "Ownership"), ("P1", "Ownership")]]
    assert graf.rantai_pemilik(G, "P1") == []
    assert graf.rantai_pemilik(G, "V1", maks_hop=1) == [[("C1", "Ownership")]]


def test_tabel_kapal(G, simpul_kecil):
    k = graf.tabel_kapal(G, simpul_kecil).set_index("id")
    assert set(k.index) == {"V1", "V2"}
    assert k.loc["V1", "pemilik"] == "Holding Utama"
    assert k.loc["V1", "nama_bendera"] == "Panama"
    assert k.loc["V1", "jumlah_relasi"] == 1


def test_statistik(H, simpul_kecil, relasi_kecil):
    assert graf.ukuran_komponen(H) == [6, 2]
    assert graf.komponen_dari(H, "V2") == {"C3", "V2"}
    r = graf.ringkasan(H, simpul_kecil, relasi_kecil)
    assert r["simpul"] == 8 and r["relasi"] == 7 and r["kapal"] == 2 and r["komponen"] == 2 and r["komponen_terbesar"] == 6
    assert r["tersanksi"] == 6 and r["derajat_maks"] == 3
    hub = graf.peringkat_hub(H, simpul_kecil, "Person", 5)
    assert hub.index[0] == "P1" and hub.iloc[0]["derajat"] == 3
    hub_luar = graf.peringkat_hub(H, simpul_kecil, n=5, hanya_tersanksi=False)
    assert set(hub_luar.index) == {"P2", "C2"}


def test_paparan(H, simpul_kecil):
    p = graf.paparan(H, simpul_kecil)
    assert p.iloc[0]["id"] in {"P2", "C2"}
    assert set(p["id"]) == {"P2", "C2"}
    assert int(p.set_index("id").loc["C2", "tetangga_tersanksi"]) == 1


def test_hitung_negara_program_dataset_derajat(H, simpul_kecil):
    neg = graf.hitung_per_negara(simpul_kecil)
    assert neg.iloc[0]["negara"] == "Rusia" and neg.iloc[0]["jumlah"] == 4
    prog = graf.hitung_program(simpul_kecil)
    assert prog.iloc[0].tolist() == ["EU-RUS", 2]
    dist = graf.distribusi_derajat(H)
    assert dist["jumlah"].sum() == 8
    assert graf.label_gaya("Vessel", 1) == "Vessel" and graf.label_gaya("Vessel", 0) == "Vessel_luar"
