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
