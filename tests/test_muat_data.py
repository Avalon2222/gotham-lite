import os

import pandas as pd

from src import muat_data


def test_nama_negara():
    assert muat_data.nama_negara("ru") == "Rusia"
    assert muat_data.nama_negara("RU") == "Rusia"
    assert muat_data.nama_negara("zz") == "Internasional"
    assert muat_data.nama_negara("qq") == "QQ"
    assert muat_data.nama_negara("") == ""
    assert muat_data.daftar_negara("ru; cy; xq") == ["Rusia", "Siprus", "XQ"]


def test_label():
    assert muat_data.label_tipe("Vessel") == "Kapal"
    assert muat_data.label_tipe("Aneh") == "Aneh"
    assert muat_data.label_relasi("Ownership") == "memiliki"
    assert muat_data.label_relasi("Aneh") == "terkait dengan"
    assert set(muat_data.WARNA_TIPE) >= set(muat_data.LABEL_TIPE)
    assert set(muat_data.WARNA_RELASI) == set(muat_data.LABEL_RELASI)


def test_bendera_kemudahan_subset_negara():
    tidak_dikenal = [k for k in muat_data.BENDERA_KEMUDAHAN if k not in muat_data.NAMA_NEGARA]
    assert tidak_dikenal == [], tidak_dikenal


def test_url_opensanctions():
    assert muat_data.url_opensanctions("NK-abc") == "https://www.opensanctions.org/entities/NK-abc/"


def test_muat_dari_berkas_sementara(tmp_path):
    simpul = pd.DataFrame([{"id": "A", "tipe": "Person", "nama": "", "alias": "", "negara": "ru", "topik": "sanction",
                            "dataset": "uji", "program": "", "tanggal": "1970-05-05", "jabatan": "", "imo": "", "mmsi": "",
                            "bendera": "", "jenis_kapal": "", "tersanksi": 1, "catatan": "", "url_sumber": "",
                            "pertama_terlihat": "", "terakhir_berubah": ""}])
    simpul.to_csv(tmp_path / "simpul.csv.gz", index=False, compression="gzip")
    df = muat_data.muat_simpul(str(tmp_path / "simpul.csv.gz"))
    assert df.loc["A", "nama"] == "(tanpa nama)"
    assert int(df.loc["A", "tahun"]) == 1970
    assert df["tersanksi"].dtype.kind == "i"
    relasi = pd.DataFrame([{"id": "r", "sumber": "A", "tujuan": "B", "tipe": "Ownership", "peran": "", "mulai": "",
                            "selesai": "", "dataset": "uji", "persen": "40"}])
    relasi.to_csv(tmp_path / "relasi.csv.gz", index=False, compression="gzip")
    r = muat_data.muat_relasi(str(tmp_path / "relasi.csv.gz"))
    assert r.loc[0, "persen"] == 40.0


def test_snapshot_asli_ada_dan_konsisten():
    """Pengujian atas data sesungguhnya di data/ (tanpa internet)."""
    assert os.path.exists(os.path.join(muat_data.DIR_DATA, "simpul.csv.gz"))
    d = muat_data.muat_semua()
    assert len(d.simpul) == d.meta["jumlah_simpul"]
    assert len(d.relasi) == d.meta["jumlah_relasi"]
    assert d.simpul.index.is_unique
    assert set(d.relasi["sumber"]).issubset(d.simpul.index)
    assert set(d.relasi["tujuan"]).issubset(d.simpul.index)
    assert (d.simpul["tipe"] == "Vessel").sum() > 1000
    assert d.simpul["tersanksi"].isin([0, 1]).all()
    assert set(d.relasi["tipe"]).issubset(set(muat_data.LABEL_RELASI))
    assert "us_ofac_sdn" in muat_data.judul_dataset(d.dataset)


def test_setiap_tipe_di_snapshot_punya_label_dan_warna():
    """Tipe baru dari OpenSanctions harus diberi label Indonesia dan warna, jangan sampai jatuh ke abu-abu."""
    meta = muat_data.muat_meta()
    for tipe in meta["simpul_per_tipe"]:
        assert tipe in muat_data.LABEL_TIPE, tipe
        assert tipe in muat_data.WARNA_TIPE, tipe


def test_muat_dataset_tidak_mengubah_kosong_jadi_nan(tmp_path):
    path = tmp_path / "dataset.csv"
    pd.DataFrame([{"dataset": "uji", "judul": "Uji", "penerbit": "", "negara_penerbit": "",
                   "url": "", "jumlah_simpul": 3, "jumlah_relasi": 0}]).to_csv(path, index=False)
    df = muat_data.muat_dataset(str(path))
    assert df.loc[0, "penerbit"] == ""
    assert df.loc[0, "negara_penerbit"] == ""
