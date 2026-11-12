"""Tes ``ais.dengarkan`` tanpa jaringan: koneksi WebSocket diganti tiruan yang memutar pesan siap pakai."""

import json

import pytest
from websockets.exceptions import ConnectionClosedError

from src import ais
from tests.test_ais import _pesan


class WsTiruan:
    """Pengganti ``websockets.sync.client.connect``: mengembalikan pesan berurutan, lalu TimeoutError."""

    def __init__(self, pesan, galat=None):
        self.pesan = list(pesan)
        self.galat = galat
        self.terkirim = []

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send(self, data):
        self.terkirim.append(json.loads(data))

    def recv(self, timeout=None):
        if self.pesan:
            p = self.pesan.pop(0)
            return p if isinstance(p, str) else json.dumps(p)
        if self.galat is not None:
            raise self.galat
        raise TimeoutError


@pytest.fixture
def pasang_ws(monkeypatch):
    def _pasang(pesan, galat=None):
        ws = WsTiruan(pesan, galat)
        monkeypatch.setattr("websockets.sync.client.connect", ws)
        return ws
    return _pasang


def test_dengarkan_hanya_simpan_kapal_target(pasang_ws):
    ws = pasang_ws([
        {"MessageType": "SubscriptionConfirmation"},
        _pesan("351000001", lat=1.0),
        _pesan("999000009", lat=5.0),
        "bukan json",
        _pesan("351000001", lat=1.5),
    ])
    df, jumlah, unik = ais.dengarkan("kunci", ["351000001"], durasi=0.2)
    assert ws.terkirim[0]["FiltersShipMMSI"] == ["351000001"]
    assert jumlah == 3
    assert unik == 2
    assert list(df["mmsi"]) == ["351000001"]
    assert df.loc[0, "lat"] == 1.5  # posisi terakhir yang dipakai


def test_dengarkan_abaikan_pesan_tanpa_mmsi(pasang_ws):
    tanpa_mmsi = _pesan()
    tanpa_mmsi["MetaData"].pop("MMSI")
    pasang_ws([tanpa_mmsi, _pesan("351000001")])
    _, jumlah, unik = ais.dengarkan("kunci", ["351000001"], durasi=0.2)
    assert jumlah == 2
    assert unik == 1


def test_dengarkan_berhenti_di_maks_pesan(pasang_ws):
    pasang_ws([_pesan("351000001")] * 10)
    _, jumlah, _ = ais.dengarkan("kunci", ["351000001"], durasi=5, maks_pesan=3)
    assert jumlah == 3


def test_dengarkan_tanpa_mmsi_valid():
    with pytest.raises(ais.AisError, match="Tidak ada MMSI valid"):
        ais.dengarkan("kunci", ["123", "abc"], durasi=0.1)


def test_dengarkan_pesan_error_dari_server(pasang_ws):
    pasang_ws([{"error": "Api Key Is Not Valid"}])
    with pytest.raises(ais.AisError, match="menolak: Api Key Is Not Valid"):
        ais.dengarkan("salah", ["351000001"], durasi=1)


def test_dengarkan_koneksi_putus_sebelum_ada_pesan(pasang_ws):
    pasang_ws([], galat=ConnectionClosedError(None, None))
    with pytest.raises(ais.AisError, match="Koneksi ke aisstream.io ditutup"):
        ais.dengarkan("kunci", ["351000001"], durasi=1)


def test_dengarkan_koneksi_putus_setelah_ada_pesan(pasang_ws):
    pasang_ws([_pesan("351000001")], galat=ConnectionClosedError(None, None))
    df, jumlah, _ = ais.dengarkan("kunci", ["351000001"], durasi=1)
    assert jumlah == 1
    assert len(df) == 1
