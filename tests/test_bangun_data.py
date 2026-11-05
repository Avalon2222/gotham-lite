import importlib.util
import json
import os

import pandas as pd

_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "bangun_data.py")
_spec = importlib.util.spec_from_file_location("bangun_data", _path)
bd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bd)


def _entitas(id_, schema, props, datasets=("uji",), caption=None):
    return {"id": id_, "schema": schema, "caption": caption, "datasets": list(datasets), "properties": props,
            "first_seen": "2024-01-01T00:00:00", "last_change": "2025-02-02T00:00:00"}


def test_baris_simpul_kapal():
    e = _entitas("V1", "Vessel", {"name": ["TANKER ALPHA", "Tanker Alpha"], "flag": ["PA"], "imoNumber": ["IMO9000001"],
                                  "mmsi": ["351000001"], "topics": ["sanction"], "programId": ["EU-RUS", "EU-RUS"],
                                  "type": ["Crude Oil Tanker"], "buildDate": ["2001"], "notes": ["baris 1\nbaris 2"]},
                 caption="Tanker Alpha")
    b = bd.baris_simpul(e)
    assert b["nama"] == "Tanker Alpha" and b["alias"] == "TANKER ALPHA"
    assert b["imo"] == "9000001" and b["mmsi"] == "351000001" and b["bendera"] == "pa"
    assert b["tersanksi"] == 1 and b["program"] == "EU-RUS" and b["tanggal"] == "2001"
    assert b["catatan"] == "baris 1 baris 2" and b["pertama_terlihat"] == "2024-01-01"


def test_baris_simpul_orang_tanpa_sanksi():
    e = _entitas("P2", "Person", {"name": ["Anak"], "topics": ["role.pep"], "citizenship": ["ru"], "country": ["ru", "cy"]})
    b = bd.baris_simpul(e)
    assert b["tersanksi"] == 0 and b["negara"] == "ru; cy" and b["imo"] == "" and b["jenis_kapal"] == ""


def test_baris_relasi():
    e = _entitas("r1", "Ownership", {"owner": ["P1"], "asset": ["C1", "C2"], "role": ["Shareholder"], "percentage": ["60"]})
    r = bd.baris_relasi(e)
    assert [(x["sumber"], x["tujuan"]) for x in r] == [("P1", "C1"), ("P1", "C2")]
    assert r[0]["peran"] == "Shareholder" and r[0]["persen"] == "60" and r[0]["tipe"] == "Ownership"
    assert bd.baris_relasi(_entitas("r2", "Ownership", {"owner": ["P1"]})) == []
    assert bd.baris_relasi(_entitas("r3", "Ownership", {"owner": ["P1"], "asset": ["P1"]})) == []   # sisi ke diri sendiri
    assert bd.baris_relasi(_entitas("r4", "Sanction", {"entity": ["P1"]})) == []


def test_saring_relasi_aturan():
    benih = {"P1": "Person", "ORG": "Organization", "C9": "Company"}
    relasi = [
        {"sumber": "P1", "tujuan": "C1", "tipe": "Ownership", "peran": "", "dataset": "ext_ru_egrul"},   # orang tersanksi: simpan
        {"sumber": "ORG", "tujuan": "C2", "tipe": "Ownership", "peran": "", "dataset": "ext_ru_egrul"},  # lembaga: buang
        {"sumber": "ORG", "tujuan": "C9", "tipe": "Ownership", "peran": "", "dataset": "ext_ru_egrul"},  # dua benih tapi bukan orang/kapal: buang
        {"sumber": "ORG", "tujuan": "C3", "tipe": "Ownership", "peran": "", "dataset": "us_ofac_sdn"},   # bukan ext_: simpan
        {"sumber": "X", "tujuan": "Y", "tipe": "Ownership", "peran": "", "dataset": "us_ofac_sdn"},      # tanpa benih: buang
        {"sumber": "P1", "tujuan": "C1", "tipe": "Ownership", "peran": "", "dataset": "ext_ru_egrul"},   # duplikat
    ]
    hasil = bd.saring_relasi(benih, relasi)
    assert [(r["sumber"], r["tujuan"]) for r in hasil] == [("ORG", "C3"), ("P1", "C1")]


def test_saring_relasi_batas_tetangga():
    benih = {"P1": "Person", "P2": "Person"}
    relasi = [{"sumber": "P1", "tujuan": f"C{i}", "tipe": "Ownership", "peran": "", "dataset": "a"} for i in range(5)]
    relasi.append({"sumber": "P1", "tujuan": "P2", "tipe": "Family", "peran": "", "dataset": "a"})
    hasil = bd.saring_relasi(benih, relasi, maks_tetangga=2)
    assert len(hasil) == 3                     # 2 tetangga luar + relasi antar-benih selalu disimpan
    assert any(r["tujuan"] == "P2" for r in hasil)


def test_bangun_end_to_end(tmp_path):
    baris = [
        _entitas("P1", "Person", {"name": ["Oligarki"], "topics": ["sanction"]}),
        _entitas("C1", "Company", {"name": ["Holding"], "topics": []}),
        _entitas("V1", "Vessel", {"name": ["Tanker"], "topics": ["sanction"], "imoNumber": ["IMO1"]}),
        _entitas("P9", "Person", {"name": ["Sendirian"], "topics": ["sanction"]}),           # tanpa relasi: tidak dimuat
        _entitas("A1", "Address", {"full": ["Jalan"]}),
        _entitas("r1", "Ownership", {"owner": ["P1"], "asset": ["C1"]}),
        _entitas("r2", "Ownership", {"owner": ["C1"], "asset": ["V1"]}),
        _entitas("r3", "Ownership", {"owner": ["X"], "asset": ["Y"]}),                        # tanpa benih
    ]
    sumber = tmp_path / "entities.ftm.json"
    sumber.write_text("\n".join(json.dumps(b) for b in baris) + "\n", encoding="utf-8")
    indeks = tmp_path / "index.json"
    indeks.write_text(json.dumps({"datasets": [{"name": "uji", "title": "Dataset Uji", "publisher": {"name": "Tim"}}]}))
    keluaran = tmp_path / "data"
    meta = bd.bangun(str(sumber), str(keluaran), str(indeks))
    assert meta["jumlah_simpul"] == 3 and meta["jumlah_relasi"] == 2 and meta["benih_tersanksi"] == 3
    simpul = pd.read_csv(keluaran / "simpul.csv.gz", dtype=str, keep_default_na=False)
    assert set(simpul["id"]) == {"P1", "C1", "V1"}
    dataset = pd.read_csv(keluaran / "dataset.csv")
    assert dataset.loc[0, "judul"] == "Dataset Uji" and dataset.loc[0, "jumlah_simpul"] == 3
