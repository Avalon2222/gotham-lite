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
