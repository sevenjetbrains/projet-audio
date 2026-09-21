"""Tests du calcul rapide des peaks : version vectorisée, pyramide multi-résolution, et fluidité du redimensionnement.

Contexte : à chaque événement de redimensionnement, la forme d'onde relisait tout le fichier audio sur le fil de
l'interface (9 à 47 secondes pour 26 minutes d'audio), ce qui affichait « Ne répond pas ».
"""

import subprocess
import sys
import threading
import wave

import numpy as np
import pytest

from app.audio import waveform as waveform_module
from app.audio.waveform import PeakPyramid, compute_peaks
from app.services import ffmpeg_service as ffmpeg_module
from app.services.ffmpeg_service import FFmpegService, background_thread_count
from app.ui.waveform_widget import _DIRECT_READ_MAX_SECONDS, _RESIZE_DEBOUNCE_MS, WaveformWidget
from app.workers.waveform_worker import WaveformWorker

_RATE = 8000


def _write_wav(path, samples, channels=1, rate=_RATE):
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        wav_file.writeframes(np.asarray(samples, dtype=np.int16).tobytes())
    return str(path)


def _reference_peaks(wav_path, width, start_time=0.0, end_time=None):
    """Implémentation d'origine (lente, trame par trame avec np.minimum.at) : référence de comparaison."""
    with wave.open(wav_path, "rb") as f:
        rate, channels, total = f.getframerate(), f.getnchannels(), f.getnframes()
        raw = np.frombuffer(f.readframes(total), dtype=np.int16).reshape(total, channels)
    mono = raw.mean(axis=1)
    start = max(0, int(start_time * rate))
    end = total if end_time is None else min(total, int(end_time * rate))
    mono = mono[start:end]
    if len(mono) == 0:
        return np.zeros((width, 2), dtype=np.float32)
    spc = max(len(mono) / width, 1e-9)
    mins = np.full(width, np.inf, dtype=np.float32)
    maxs = np.full(width, -np.inf, dtype=np.float32)
    cols = np.minimum((np.arange(len(mono)) / spc).astype(np.int64), width - 1)
    np.minimum.at(mins, cols, mono)
    np.maximum.at(maxs, cols, mono)
    mins[np.isinf(mins)] = 0.0
    maxs[np.isinf(maxs)] = 0.0
    return np.stack([mins, maxs], axis=1) / 32768.0


@pytest.fixture
def noisy_wav(tmp_path):
    rng = np.random.default_rng(42)
    return _write_wav(tmp_path / "noise.wav", rng.integers(-20000, 20000, size=_RATE * 12))


# ============================ compute_peaks vectorisé =================================================


@pytest.mark.parametrize("width", [1, 7, 100, 999, 4000])
def test_vectorized_peaks_match_the_reference_for_the_whole_file(noisy_wav, width):
    np.testing.assert_allclose(compute_peaks(noisy_wav, width), _reference_peaks(noisy_wav, width), atol=1e-6)


@pytest.mark.parametrize(("start", "end"), [(0.0, 3.0), (2.5, 9.1), (11.0, None), (0.0, 0.01), (5.0, 5.0)])
def test_vectorized_peaks_match_the_reference_on_a_range(noisy_wav, start, end):
    np.testing.assert_allclose(
        compute_peaks(noisy_wav, 500, start, end), _reference_peaks(noisy_wav, 500, start, end), atol=1e-6
    )


def test_more_columns_than_frames_still_matches_the_reference(tmp_path):
    path = _write_wav(tmp_path / "short.wav", np.arange(-50, 50) * 300)

    np.testing.assert_allclose(compute_peaks(path, 400), _reference_peaks(path, 400), atol=1e-6)


def test_stereo_is_mixed_to_mono_like_before(tmp_path):
    left = np.tile([1000, -1000], 3000)
    right = np.tile([3000, -3000], 3000)
    path = _write_wav(tmp_path / "stereo.wav", np.stack([left, right], axis=1).ravel(), channels=2)

    np.testing.assert_allclose(compute_peaks(path, 60), _reference_peaks(path, 60), atol=1e-6)


def test_result_does_not_depend_on_the_read_chunk_size(noisy_wav, monkeypatch):
    whole = compute_peaks(noisy_wav, 321)

    monkeypatch.setattr(waveform_module, "_CHUNK_FRAMES", 977)  # colonnes à cheval sur plusieurs lectures
    chunked = compute_peaks(noisy_wav, 321)

    np.testing.assert_allclose(chunked, whole, atol=1e-7)


def test_peaks_are_normalized_and_silence_is_flat(tmp_path):
    loud = _write_wav(tmp_path / "loud.wav", np.tile([32767, -32768], 4000))
    silent = _write_wav(tmp_path / "silent.wav", np.zeros(8000))

    peaks = compute_peaks(loud, 50)
    assert peaks.min() == pytest.approx(-1.0) and peaks.max() < 1.0 and peaks.max() > 0.99
    assert not compute_peaks(silent, 50).any()


def test_invalid_arguments_and_formats(tmp_path):
    path = _write_wav(tmp_path / "a.wav", np.zeros(100))
    with pytest.raises(ValueError):
        compute_peaks(path, 0)

    eight_bit = tmp_path / "8bit.wav"
    with wave.open(str(eight_bit), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(1)
        f.setframerate(8000)
        f.writeframes(bytes(100))
    with pytest.raises(ValueError, match="16-bit"):
        compute_peaks(str(eight_bit), 10)


# ============================ pyramide ================================================================


@pytest.fixture
def smooth_wav(tmp_path):
    """Sinus à enveloppe lente : les blocs de la pyramide approchent bien les min/max exacts de chaque colonne."""
    t = np.arange(_RATE * 60) / _RATE
    envelope = 0.2 + 0.7 * np.abs(np.sin(2 * np.pi * t / 17.0))
    return _write_wav(tmp_path / "smooth.wav", (envelope * np.sin(2 * np.pi * 220 * t) * 30000))


def test_pyramid_describes_the_file(smooth_wav):
    pyramid = PeakPyramid.build(smooth_wav)

    assert pyramid.duration == pytest.approx(60.0)
    assert pyramid.total_frames == _RATE * 60
    assert len(pyramid._levels) >= 2
    blocks = [level[0] for level in pyramid._levels]
    assert blocks == sorted(blocks) and blocks[0] == 64  # du plus fin au plus grossier


@pytest.mark.parametrize(
    ("start", "end", "width"), [(0.0, None, 800), (10.0, 40.0, 800), (20.0, 25.0, 300), (55.0, 60.0, 300)]
)
def test_pyramid_peaks_are_close_to_the_exact_ones(smooth_wav, start, end, width):
    pyramid = PeakPyramid.build(smooth_wav)

    approx = pyramid.peaks(start, end, width)
    exact = compute_peaks(smooth_wav, width, start, end)

    assert approx is not None and approx.shape == (width, 2) and approx.dtype == np.float32
    assert np.abs(approx - exact).max() < 0.12  # à la précision d'un bloc près : invisible à l'écran


def test_pyramid_columns_keep_min_below_max(smooth_wav):
    approx = PeakPyramid.build(smooth_wav).peaks(0.0, None, 500)

    assert (approx[:, 0] <= approx[:, 1]).all()  # min ≤ max dans chaque colonne
    assert approx[:, 0].min() < -0.3 and approx[:, 1].max() > 0.3  # le signal (amplitude ~0,9) est bien représenté


def test_pyramid_returns_none_when_the_view_is_finer_than_its_blocks(smooth_wav):
    pyramid = PeakPyramid.build(smooth_wav)

    assert pyramid.peaks(30.0, 30.2, 1000) is None  # 1600 trames pour 1000 colonnes : lecture directe, rapide


def test_pyramid_empty_range_and_bad_width(smooth_wav):
    pyramid = PeakPyramid.build(smooth_wav)

    assert not pyramid.peaks(10.0, 10.0, 50).any() and pyramid.peaks(10.0, 10.0, 50).shape == (50, 2)
    assert pyramid.peaks(0.0, None, 0) is None


def test_pyramid_handles_files_shorter_than_a_block(tmp_path):
    path = _write_wav(tmp_path / "tiny.wav", np.arange(30) * 100)

    pyramid = PeakPyramid.build(path)

    assert pyramid.total_frames == 30 and len(pyramid._levels[0][1]) == 1  # un seul bloc partiel
    assert pyramid.peaks(0.0, None, 10) is None  # trop court pour la pyramide : lecture directe


def test_pyramid_with_a_partial_last_block_covers_the_end_of_the_file(tmp_path):
    samples = np.zeros(64 * 100 + 17)
    samples[-1] = 30000  # dans la toute dernière trame, hors bloc complet
    path = _write_wav(tmp_path / "tail.wav", samples)

    peaks = PeakPyramid.build(path).peaks(0.0, None, 20)

    assert peaks[-1, 1] == pytest.approx(30000 / 32768)


def test_pyramid_query_is_fast_even_for_a_long_file(tmp_path):
    import time

    long_file = _write_wav(tmp_path / "long.wav", np.random.default_rng(1).integers(-9000, 9000, size=_RATE * 60 * 30))
    pyramid = PeakPyramid.build(long_file)  # 30 minutes

    started = time.perf_counter()
    for _ in range(50):
        pyramid.peaks(0.0, None, 1400)
        pyramid.peaks(600.0, 900.0, 1400)
    per_query = (time.perf_counter() - started) / 100

    assert per_query < 0.02  # bien en dessous d'une image à 60 Hz ; relire le fichier prenait plusieurs secondes


# ============================ partage et cache ============================================================


@pytest.fixture(autouse=True)
def _clean_cache():
    PeakPyramid._cache.clear()
    yield
    PeakPyramid._cache.clear()


def test_for_file_builds_once_and_reuses(smooth_wav, monkeypatch):
    builds = []
    original = PeakPyramid.build.__func__
    monkeypatch.setattr(PeakPyramid, "build", classmethod(lambda cls, p: builds.append(p) or original(cls, p)))

    first = PeakPyramid.for_file(smooth_wav)
    second = PeakPyramid.for_file(smooth_wav)

    assert first is second and len(builds) == 1


def test_for_file_rebuilds_when_the_file_changes(tmp_path):
    path = tmp_path / "a.wav"
    _write_wav(path, np.zeros(8000))
    first = PeakPyramid.for_file(str(path))

    _write_wav(path, np.ones(16000) * 5000)

    assert PeakPyramid.for_file(str(path)) is not first


def test_cache_keeps_only_a_few_recent_files(tmp_path):
    paths = [_write_wav(tmp_path / f"f{i}.wav", np.zeros(8000 + i)) for i in range(5)]

    for path in paths:
        PeakPyramid.for_file(path)

    assert len(PeakPyramid._cache) == 3


def test_concurrent_requests_build_only_once(smooth_wav, monkeypatch):
    """La forme d'onde et la vue d'ensemble demandent la pyramide en même temps : une seule lecture du fichier."""
    builds = []
    original = PeakPyramid.build.__func__

    def slow_build(cls, path):
        builds.append(path)
        threading.Event().wait(0.15)
        return original(cls, path)

    monkeypatch.setattr(PeakPyramid, "build", classmethod(slow_build))
    results = []
    threads = [threading.Thread(target=lambda: results.append(PeakPyramid.for_file(smooth_wav))) for _ in range(4)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(builds) == 1 and all(r is results[0] for r in results)


# ============================ worker ===================================================================


def test_worker_emits_peaks_then_the_pyramid(qtbot, smooth_wav):
    worker = WaveformWorker(smooth_wav, 600)
    order = []
    worker.peaks_ready.connect(lambda p: order.append(("peaks", p.shape)))
    worker.pyramid_ready.connect(lambda p: order.append(("pyramid", p)))

    with qtbot.waitSignal(worker.pyramid_ready, timeout=8000):
        worker.start()
    worker.wait(2000)

    assert [kind for kind, _ in order] == ["peaks", "pyramid"]  # l'onde s'affiche d'abord, la pyramide suit
    assert order[0][1] == (600, 2)
    assert isinstance(order[1][1], PeakPyramid)


def test_worker_falls_back_to_direct_reading_for_a_tiny_file(qtbot, tmp_path):
    path = _write_wav(tmp_path / "tiny.wav", np.arange(40) * 200)
    worker = WaveformWorker(path, 20)

    with qtbot.waitSignal(worker.peaks_ready, timeout=5000) as blocker:
        worker.start()
    worker.wait(2000)

    assert blocker.args[0].shape == (20, 2)


def test_worker_reports_unreadable_files(qtbot, tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"pas un wav")
    worker = WaveformWorker(str(bad), 100)

    with qtbot.waitSignal(worker.failed, timeout=5000):
        worker.start()
    worker.wait(2000)


def test_two_workers_share_one_pyramid(qtbot, smooth_wav, monkeypatch):
    builds = []
    original = PeakPyramid.build.__func__
    monkeypatch.setattr(PeakPyramid, "build", classmethod(lambda cls, p: builds.append(p) or original(cls, p)))
    first, second = WaveformWorker(smooth_wav, 600), WaveformWorker(smooth_wav, 800)

    with qtbot.waitSignal(first.pyramid_ready, timeout=8000):
        first.start()
    first.wait(2000)
    with qtbot.waitSignal(second.pyramid_ready, timeout=8000):
        second.start()
    second.wait(2000)

    assert len(builds) == 1  # forme d'onde + vue d'ensemble : le fichier n'est lu qu'une fois


# ============================ widget : redimensionnement fluide =============================================


@pytest.fixture
def widget(qtbot, smooth_wav):
    w = WaveformWidget()
    qtbot.addWidget(w)
    w.resize(700, 200)
    w.show()
    w.load(smooth_wav, 60.0)
    qtbot.waitUntil(lambda: w._pyramid is not None and w._peaks is not None, timeout=8000)
    return w


def test_widget_receives_the_pyramid_after_loading(widget):
    assert isinstance(widget._pyramid, PeakPyramid)
    assert widget._peaks.shape[1] == 2


def test_resize_never_rereads_the_audio_file_when_the_pyramid_is_ready(qtbot, widget, monkeypatch):
    monkeypatch.setattr("app.ui.waveform_widget.compute_peaks", lambda *a, **k: pytest.fail("relecture du fichier"))

    for step in range(30):
        widget.resize(700 + step * 9, 200)
    qtbot.wait(_RESIZE_DEBOUNCE_MS * 4)

    assert widget._peaks.shape[0] == widget.width()  # recalculé pour la nouvelle largeur, depuis la pyramide


def test_a_burst_of_resize_events_recomputes_only_once(qtbot, widget, monkeypatch):
    calls = []
    original = widget._recompute_peaks_sync
    monkeypatch.setattr(widget, "_recompute_peaks_sync", lambda: calls.append(1) or original())
    widget._resize_timer.timeout.disconnect()
    widget._resize_timer.timeout.connect(widget._recompute_peaks_sync)

    for step in range(25):
        widget.resize(700 + step * 7, 200)
    assert calls == []  # rien pendant la rafale : l'onde déjà calculée est simplement étirée
    qtbot.waitUntil(lambda: bool(calls), timeout=2000)
    qtbot.wait(_RESIZE_DEBOUNCE_MS * 3)

    assert len(calls) == 1


def test_resize_is_quick_on_the_ui_thread(qtbot, widget):
    import time

    worst = 0.0
    for step in range(40):
        started = time.perf_counter()
        widget.resize(700 + step * 10, 200)
        qtbot.wait(1)
        worst = max(worst, time.perf_counter() - started)

    assert worst < 0.25  # l'ancien code figeait l'interface plusieurs secondes à chaque pas sur un long fichier


def test_zoom_and_scroll_use_the_pyramid_too(widget, monkeypatch):
    monkeypatch.setattr("app.ui.waveform_widget.compute_peaks", lambda *a, **k: pytest.fail("relecture du fichier"))

    widget.set_view_range(10.0, 40.0)
    widget.set_view_range(20.0, 50.0)
    widget.reset_zoom()

    assert widget._peaks.shape == (widget.width(), 2)


def test_very_deep_zoom_reads_the_short_range_directly(widget):
    widget.set_view_range(30.0, 30.3)  # plus fin que la pyramide : lecture directe d'une plage minuscule

    assert widget._peaks.shape == (widget.width(), 2)
    assert np.abs(widget._peaks).max() > 0


def test_without_a_pyramid_a_long_view_keeps_the_current_display(qtbot, smooth_wav, monkeypatch):
    w = WaveformWidget()
    qtbot.addWidget(w)
    w.resize(600, 200)
    w._wav_path, w._duration = smooth_wav, 60.0
    w._view_start, w._view_end = 0.0, 60.0
    w._peaks = np.full((600, 2), [-0.5, 0.5], dtype=np.float32)
    monkeypatch.setattr("app.ui.waveform_widget.compute_peaks", lambda *a, **k: pytest.fail("calcul bloquant"))

    w._recompute_peaks_sync()  # pyramide pas encore prête, vue longue : ne doit rien lire

    assert (w._peaks == [-0.5, 0.5]).all()


def test_without_a_pyramid_a_short_view_is_read_directly(qtbot, smooth_wav):
    w = WaveformWidget()
    qtbot.addWidget(w)
    w.resize(600, 200)
    w._wav_path, w._duration = smooth_wav, 60.0
    w._view_start, w._view_end = 10.0, 10.0 + _DIRECT_READ_MAX_SECONDS - 1
    w._peaks = np.zeros((600, 2), dtype=np.float32)

    w._recompute_peaks_sync()

    assert np.abs(w._peaks).max() > 0.1  # lecture rapide d'une plage courte


def test_a_zoom_requested_while_loading_is_refined_when_the_pyramid_arrives(qtbot, smooth_wav, widget):
    widget._pyramid = None
    widget._view_start, widget._view_end = 5.0, 45.0
    before = widget._peaks.copy()

    widget._on_pyramid_ready(PeakPyramid.for_file(smooth_wav))

    assert widget._pyramid is not None and not np.array_equal(widget._peaks, before)


def test_loading_a_new_file_forgets_the_previous_pyramid(qtbot, widget, tmp_path):
    other = _write_wav(tmp_path / "other.wav", np.zeros(_RATE * 5))
    old = widget._pyramid

    widget.load(other, 5.0)

    assert widget._pyramid is None and old is not None


# ============================ aperçu vidéo : priorité basse ==============================================


class _FakeProcess:
    def __init__(self):
        self.stderr = iter([])
        self.returncode = 0

    def wait(self):
        return 0


def test_low_priority_option_is_passed_to_the_process(monkeypatch):
    captured = []
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", lambda cmd, **kw: captured.append(kw) or _FakeProcess())
    service = FFmpegService("ffmpeg")

    service._run(["ffmpeg"], low_priority=True)
    service._run(["ffmpeg"])

    if sys.platform == "win32":
        assert captured[0]["creationflags"] == subprocess.BELOW_NORMAL_PRIORITY_CLASS
    else:
        assert "preexec_fn" in captured[0]
    assert "creationflags" not in captured[1] and "preexec_fn" not in captured[1]  # les autres tâches restent normales


def test_preview_proxy_runs_in_background_with_limited_threads(monkeypatch, tmp_path):
    seen = {}

    def fake_run(self, cmd, **kwargs):
        seen["cmd"], seen["kwargs"] = cmd, kwargs
        (tmp_path / "preview.mp4.part.mp4").write_bytes(b"x")
        return []

    monkeypatch.setattr(FFmpegService, "_run", fake_run)
    service = FFmpegService("ffmpeg")

    service.create_preview_proxy("in.mp4", str(tmp_path / "preview.mp4"), 60.0, 360)

    assert seen["kwargs"]["low_priority"] is True  # l'interface doit toujours passer devant
    cmd = seen["cmd"]
    threads = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-threads"]
    assert len(threads) == 2 and set(threads) == {str(background_thread_count())}
    assert cmd.index("-threads") < cmd.index("-i")  # une fois pour le décodage, une pour l'encodage


def test_background_thread_count_leaves_cores_for_the_interface(monkeypatch):
    monkeypatch.setattr(ffmpeg_module.os, "cpu_count", lambda: 8)
    assert background_thread_count() == 4
    monkeypatch.setattr(ffmpeg_module.os, "cpu_count", lambda: 1)
    assert background_thread_count() == 1
    monkeypatch.setattr(ffmpeg_module.os, "cpu_count", lambda: None)
    assert background_thread_count() == 1


def test_normal_ffmpeg_jobs_are_not_slowed_down():
    from app.services.ffmpeg_service import _background_priority_options

    assert _background_priority_options(False) == {}
