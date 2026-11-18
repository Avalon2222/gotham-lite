"""Tes komponen terhubung dan distribusi derajat di src/graf.py."""

import networkx as nx

from src import graf


def test_ukuran_komponen_urut_dan_total_sama(H):
    ukuran = graf.ukuran_komponen(H)
    assert ukuran == sorted(ukuran, reverse=True)
    assert sum(ukuran) == H.number_of_nodes()


def test_komponen_dari_simpul_ada_dan_tidak_ada(H):
    komp = graf.komponen_dari(H, "P1")
    assert "P1" in komp and komp <= set(H.nodes)
    assert graf.komponen_dari(H, "TIDAK-ADA") == set()


def test_distribusi_derajat_jumlah_sama_dengan_simpul():
    H = nx.star_graph(4)            # satu pusat berderajat 4, empat daun berderajat 1
    d = graf.distribusi_derajat(H).set_index("derajat")["jumlah"]
    assert d["1"] == 4 and d["4-5"] == 1
    assert d.sum() == 5


def test_distribusi_derajat_menghitung_simpul_terisolasi():
    H = nx.path_graph(3)
    H.add_node("sendiri")
    d = graf.distribusi_derajat(H).set_index("derajat")["jumlah"]
    assert d["0"] == 1
    assert d.sum() == H.number_of_nodes()


def test_label_gaya_bedakan_tersanksi():
    assert graf.label_gaya("Person", 1) == "Person"
    assert graf.label_gaya("Vessel", 0) == "Vessel_luar"


def test_warna_tipe_punya_cadangan_abu():
    assert graf.warna_tipe("Tipe-Aneh") == "#9ca3af"
    semua = graf.label_tipe_semua()
    assert semua and all(graf.warna_tipe(t).startswith("#") for t in semua)
    semua["Person"] = "diubah"
    assert graf.label_tipe_semua().get("Person") != "diubah"   # salinan, bukan dict asli


def test_teks_relasi_persen_dan_peran_dipotong():
    teks = graf.teks_relasi({"tipe": "Ownership", "persen": 51.0, "peran": "x" * 80}, maks_peran=10)
    assert "51%" in teks and teks.endswith("x" * 10 + "…")
    assert "nan" not in graf.teks_relasi({"tipe": "Ownership", "persen": float("nan"), "peran": None})


def test_teks_relasi_peran_nan_diabaikan():
    assert graf.teks_relasi({"tipe": "Ownership", "peran": float("nan"), "persen": None}) == graf.label_relasi("Ownership")


def test_cari_tahan_nama_dan_alias_kosong(simpul_kecil, H):
    simpul = simpul_kecil.copy()
    simpul["alias"] = simpul["alias"].astype(object)
    simpul.loc["P1", "alias"] = None
    hasil = graf.cari(simpul, "oligarki", graf.derajat(H))
    assert hasil.index[0] == "P1"


def test_teks_relasi_persen_dibulatkan_dua_desimal():
    assert graf.teks_relasi({"tipe": "Ownership", "persen": 0.199203187250996}) == "memiliki 0.2%"
    assert graf.teks_relasi({"tipe": "Ownership", "persen": 99.97}) == "memiliki 99.97%"
    assert graf.teks_relasi({"tipe": "Ownership", "persen": 33.33333}) == "memiliki 33.33%"
