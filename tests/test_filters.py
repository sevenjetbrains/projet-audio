"""Tests de app.audio.filters (construction pure de chaînes de filtres)."""

from app.audio.filters import build_filter_chain
from app.models.audio_settings import AudioSettings


def test_no_processing_returns_none():
    assert build_filter_chain(AudioSettings(), duration=5.0) is None


def test_gain_only():
    chain = build_filter_chain(AudioSettings(gain=3.0), duration=5.0)
    assert chain == "volume=3.0dB"


def test_fade_in_and_out():
    chain = build_filter_chain(AudioSettings(fade_in=0.5, fade_out=1.0), duration=5.0)
    assert "afade=t=in:st=0:d=0.5" in chain
    assert "afade=t=out:st=4.0:d=1.0" in chain


def test_noise_reduction_levels():
    chain = build_filter_chain(AudioSettings(noise_reduction=True, noise_reduction_level="forte"), duration=5.0)
    assert "afftdn=nr=20" in chain


def test_de_hum_includes_harmonics():
    chain = build_filter_chain(AudioSettings(de_hum=True, de_hum_freq=50), duration=5.0)
    assert "bandreject=f=50" in chain
    assert "bandreject=f=100" in chain
    assert "bandreject=f=150" in chain


def test_de_click():
    chain = build_filter_chain(AudioSettings(de_click=True), duration=5.0)
    assert chain == "adeclick"


def test_eq_bands():
    chain = build_filter_chain(AudioSettings(eq_bass_db=2.0, eq_mid_db=-1.0, eq_treble_db=3.0), duration=5.0)
    assert "bass=g=2.0" in chain
    assert "equalizer=f=1000:t=q:w=1:g=-1.0" in chain
    assert "treble=g=3.0" in chain


def test_compression():
    chain = build_filter_chain(AudioSettings(compression=True), duration=5.0)
    assert chain.startswith("acompressor=")


def test_normalize_peak_vs_loudness():
    peak_chain = build_filter_chain(AudioSettings(normalize=True, normalize_mode="peak"), duration=5.0)
    assert peak_chain == "dynaudnorm"

    loud_chain = build_filter_chain(
        AudioSettings(normalize=True, normalize_mode="loudness", normalize_target_lufs=-18.0), duration=5.0
    )
    assert "loudnorm=I=-18.0" in loud_chain


def test_order_cleanup_before_gain_and_fades():
    settings = AudioSettings(noise_reduction=True, gain=2.0, fade_in=0.5)
    chain = build_filter_chain(settings, duration=5.0)
    assert chain.index("afftdn") < chain.index("volume")
    assert chain.index("volume") < chain.index("afade")
