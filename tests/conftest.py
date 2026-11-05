"""Graf buatan kecil yang dipakai hampir semua pengujian.

    Oligarki (orang, tersanksi)
      ├─ memiliki 60% ─► Holding (perusahaan, tersanksi)
      │                     ├─ memiliki ─► Tanker Alpha (kapal, tersanksi, bendera pa)
      │                     └─ memiliki ─► Toko Roti (perusahaan, TIDAK tersanksi)
      ├─ keluarga dari ─► Anak (orang, TIDAK tersanksi)
      └─ mengurus ─► Yayasan (organisasi, tersanksi)
    Anak ─ mengurus ─► Toko Roti
    Pulau Terpencil (perusahaan, tersanksi) ─ memiliki ─► Kapal Sendiri (kapal) ; komponen terpisah
"""

import pandas as pd
import pytest

from src import graf
from src.muat_data import muat_simpul, muat_relasi  # noqa: F401  (memastikan modul terimpor)

KOLOM_SIMPUL = ["id", "tipe", "nama", "alias", "negara", "topik", "dataset", "program", "tanggal", "jabatan",
                "imo", "mmsi", "bendera", "jenis_kapal", "tersanksi", "catatan", "url_sumber",
                "pertama_terlihat", "terakhir_berubah"]
KOLOM_RELASI = ["id", "sumber", "tujuan", "tipe", "peran", "mulai", "selesai", "dataset", "persen"]


def _simpul(id_, tipe, nama, tersanksi=1, **kw):
    baris = {k: "" for k in KOLOM_SIMPUL}
    baris.update({"id": id_, "tipe": tipe, "nama": nama, "tersanksi": tersanksi})
    baris.update(kw)
    return baris


def _relasi(id_, sumber, tujuan, tipe, peran="", persen="", dataset="uji"):
    return {"id": id_, "sumber": sumber, "tujuan": tujuan, "tipe": tipe, "peran": peran, "mulai": "", "selesai": "",
            "dataset": dataset, "persen": persen}


@pytest.fixture(scope="session")
def simpul_kecil():
    df = pd.DataFrame([
        _simpul("P1", "Person", "Oligarki Besar", negara="ru", alias="O. Besar", program="EU-RUS", tanggal="1960-01-01"),
        _simpul("C1", "Company", "Holding Utama", negara="cy", program="EU-RUS"),
        _simpul("V1", "Vessel", "Tanker Alpha", negara="pa", bendera="pa", imo="9000001", mmsi="351000001",
                jenis_kapal="Crude Oil Tanker", tanggal="2001-01-01"),
        _simpul("C2", "Company", "Toko Roti", tersanksi=0, negara="ru"),
        _simpul("P2", "Person", "Anak Oligarki", tersanksi=0, negara="ru"),
        _simpul("O1", "Organization", "Yayasan Amal", negara="ru"),
        _simpul("C3", "Company", "Pulau Terpencil", negara="mh"),
        _simpul("V2", "Vessel", "Kapal Sendiri", negara="mh", bendera="mh", imo="9000002", mmsi="538000002"),
    ], columns=KOLOM_SIMPUL)
    df["tersanksi"] = df["tersanksi"].astype(int)
    df["tahun"] = pd.to_numeric(df["tanggal"].str[:4], errors="coerce").astype("Int64")
    return df.set_index("id", drop=False)


@pytest.fixture(scope="session")
def relasi_kecil():
    df = pd.DataFrame([
        _relasi("r1", "P1", "C1", "Ownership", "Shareholder", "60"),
        _relasi("r2", "C1", "V1", "Ownership", "Registered owner"),
        _relasi("r3", "C1", "C2", "Ownership"),
        _relasi("r4", "P1", "P2", "Family", "child"),
        _relasi("r5", "P1", "O1", "Directorship", "Chairman"),
        _relasi("r6", "P2", "C2", "Directorship", "Director"),
        _relasi("r7", "C3", "V2", "Ownership"),
    ], columns=KOLOM_RELASI)
    df["persen"] = pd.to_numeric(df["persen"], errors="coerce")
    return df


@pytest.fixture(scope="session")
def G(simpul_kecil, relasi_kecil):
    return graf.bangun_graf(simpul_kecil, relasi_kecil)


@pytest.fixture(scope="session")
def H(G):
    return graf.tak_berarah(G)
