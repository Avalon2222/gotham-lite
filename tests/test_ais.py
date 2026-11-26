import pandas as pd

from src import ais


def _pesan(mmsi="351000001", lat=1.2, lon=103.8, sog=12.5, cog=90, tipe="PositionReport", status=0):
    return {
        "MessageType": tipe,
        "MetaData": {"MMSI": int(mmsi), "ShipName": "TANKER ALPHA@@@", "latitude": lat, "longitude": lon,
                     "time_utc": "2026-11-05 10:00:00.123456789 +0000 UTC"},
        "Message": {tipe: {"UserID": int(mmsi), "Latitude": lat, "Longitude": lon, "Sog": sog, "Cog": cog,
                           "TrueHeading": 91, "NavigationalStatus": status}},
    }


def test_pesan_langganan():
    p = ais.pesan_langganan("kunci")
    assert p["APIKey"] == "kunci"
    assert p["BoundingBoxes"] == [[[-90.0, -180.0], [90.0, 180.0]]]
    assert "FiltersShipMMSI" not in p
    assert ais.pesan_langganan("k", mmsi=["1", 2])["FiltersShipMMSI"] == ["1", "2"]


def test_urai_posisi_normal():
    b = ais.urai_posisi(_pesan())
    assert b["mmsi"] == "351000001"
    assert b["nama_ais"] == "TANKER ALPHA"
    assert (b["lat"], b["lon"], b["sog_knot"], b["cog"]) == (1.2, 103.8, 12.5, 90)
    assert b["status_nav"] == "berlayar dengan mesin"
    assert b["waktu_pesan"] == pd.Timestamp("2026-11-05 10:00:00", tz="UTC")


def test_urai_posisi_nilai_tidak_tersedia():
    b = ais.urai_posisi(_pesan(sog=102.3, cog=360, status=15))
    assert b["sog_knot"] is None and b["cog"] is None and b["status_nav"] == "tidak ditentukan"
    assert ais.urai_posisi(_pesan(lat=91)) is None
    assert ais.urai_posisi({"MessageType": "ShipStaticData", "MetaData": {"MMSI": 1}}) is None
    assert ais.urai_posisi({"MessageType": "PositionReport", "MetaData": {}}) is None
    kelas_b = ais.urai_posisi(_pesan(tipe="StandardClassBPositionReport"))
    assert kelas_b["status_nav"] == ""


def test_ke_dataframe_dan_gabung():
    kosong = ais.ke_dataframe({})
    assert kosong.empty and list(kosong.columns) == ais.KOLOM
    df = ais.ke_dataframe({"351000001": ais.urai_posisi(_pesan())})
    kapal = pd.DataFrame([{"id": "V1", "mmsi": "351000001", "nama": "Tanker Alpha", "bendera": "pa", "imo": "9000001",
                           "program": "EU-RUS", "jenis_kapal": "Crude Oil Tanker"},
                          {"id": "V2", "mmsi": "", "nama": "Tanpa MMSI", "bendera": "", "imo": "", "program": "",
                           "jenis_kapal": ""}])
    gabung = ais.gabung_dengan_kapal(df, kapal)
    assert gabung.loc[0, "nama"] == "Tanker Alpha" and gabung.loc[0, "bendera"] == "pa"
    assert ais.gabung_dengan_kapal(kosong, kapal).empty


def test_ambil_api_key(monkeypatch):
    monkeypatch.setenv("AISSTREAM_API_KEY", "  abc ")
    assert ais.ambil_api_key() == "abc"
    monkeypatch.setenv("AISSTREAM_API_KEY", "")
    assert ais.ambil_api_key() is None


def test_pilih_mmsi():
    assert ais.pilih_mmsi(["351000001", "351000001", " 538000002 ", "123", "abcdefghi", ""]) == ["351000001", "538000002"]
    banyak = [str(100000000 + i) for i in range(250)]
    assert len(ais.pilih_mmsi(banyak)) == ais.MAKS_MMSI == 200
    assert ais.pilih_mmsi(banyak, maks=3) == banyak[:3]
    assert ais.pilih_mmsi([]) == []


def test_angka_aman():
    assert ais._angka("12.5") == 12.5
    assert ais._angka(None) is None and ais._angka("x") is None
    assert ais._angka(float("nan"), 0) == 0


def test_waktu_meta():
    assert ais._waktu_meta({"time_utc": "2026-11-05 08:00:01.5 +0000 UTC"}) == pd.Timestamp("2026-11-05 08:00:01", tz="UTC")
    assert ais._waktu_meta({}) is None
    assert ais._waktu_meta({"time_utc": "rusak"}) is None


def test_sekarang_utc_punya_zona():
    assert ais.sekarang_utc().utcoffset().total_seconds() == 0


def test_urai_posisi_buang_null_island():
    assert ais.urai_posisi(_pesan(lat=0, lon=0)) is None
    assert ais.urai_posisi(_pesan(lat=0, lon=103.8)) is not None   # khatulistiwa tetap valid


def test_urai_posisi_koordinat_null_pakai_metadata():
    p = _pesan(lat=-6.1, lon=106.8)
    p["Message"]["PositionReport"]["Latitude"] = None
    p["Message"]["PositionReport"]["Longitude"] = None
    b = ais.urai_posisi(p)
    assert b is not None
    assert (b["lat"], b["lon"]) == (-6.1, 106.8)


def test_pilih_mmsi_float_dan_maks_nol():
    assert ais.pilih_mmsi(["273126430.0", 572469210.0, "273126430"]) == ["273126430", "572469210"]
    assert ais.pilih_mmsi(["273126430"], maks=0) == []


def test_urai_posisi_nilai_di_luar_rentang():
    baris = ais.urai_posisi(_pesan(sog=-1, cog=-5, status=float("inf")))
    assert baris["sog_knot"] is None and baris["cog"] is None
    assert baris["status_nav"] == ""
    assert ais.urai_posisi(_pesan(status=99))["status_nav"] == ""
    assert ais.urai_posisi(_pesan(status=14))["status_nav"] == "kode 14"


def test_teks_hover_kecepatan_kosong_bukan_nol():
    baris = {"nama": "Tanker Alpha", "nama_ais": "ALPHA", "bendera": "pa", "imo": "9187629", "mmsi": "351000001",
             "status_nav": "berlabuh jangkar", "sog_knot": None}
    teks = ais.teks_hover(baris, lambda k: {"pa": "Panama"}[k])
    assert teks.split("<br>") == ["Tanker Alpha", "Bendera: Panama", "IMO 9187629 · MMSI 351000001",
                                  "berlabuh jangkar", "Kecepatan tidak dilaporkan"]
    assert "0 knot" not in teks


def test_teks_hover_tanpa_imo_status_dan_nama_daftar():
    baris = pd.Series({"nama": float("nan"), "nama_ais": "GHOST", "bendera": float("nan"), "imo": float("nan"),
                       "mmsi": "273000002", "status_nav": "", "sog_knot": 12.345})
    assert ais.teks_hover(baris).split("<br>") == ["GHOST", "MMSI 273000002", "12.3 knot"]


def test_mmsi_float_dirapikan_supaya_cocok_dengan_target():
    p = _pesan()
    p["MetaData"]["MMSI"] = 351000001.0
    assert ais._mmsi_pesan(p) == "351000001"
    assert ais.urai_posisi(p)["mmsi"] == "351000001"
    p["MetaData"]["MMSI"] = "351000001.0"
    assert ais.urai_posisi(p)["mmsi"] == "351000001"
