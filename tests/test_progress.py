"""Tests de la progression réelle (callbacks FFmpeg, répartition par étapes, workers, barres de l'interface)."""

import wave
from pathlib import Path

import numpy as np
import pytest

from app.models.media import MediaInfo
from app.services import sequence_service
from app.services.export_service import export_project, export_sequences_separately
from app.services.ffmpeg_service import FFmpegService, wav_duration
from app.services.project_service import create_project_for_video
from app.services.audio_processor import process_sequence
from app.ui.audio_processing_panel import AudioProcessingPanel
from app.ui.export_dialog import ExportDialog
from app.utils.progress import sub_progress
from app.workers.ffmpeg_worker import FFmpegTaskWorker

_RATE = 16000


def _assert_valid_progress(values: list[float]) -> None:
    assert values, "aucune progression rapportée"
    assert all(0.0 <= v <= 1.0 for v in values)
    assert values == sorted(values), f"progression non monotone : {values}"
    assert values[-1] == pytest.approx(1.0)


@pytest.fixture
def project(ffmpeg_binaries):
    t = np.arange(int(_RATE * 6.0)) / _RATE
    samples = (0.3 * np.sin(2 * np.pi * 300 * t) * 32767).astype(np.int16)
    media_info = MediaInfo(
        path="demo.mp4", duration=6.0, container_format="mp4", video_codec="h264",
        audio_codec="aac", sample_rate=_RATE, channels=1, resolution=None, bitrate=None, size_bytes=1,
    )
    proj = create_project_for_video(media_info)
    wav_path = Path(proj.temp_dir) / "source.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(_RATE)
        wav_file.writeframes(samples.tobytes())
    proj.original_audio_path = str(wav_path)
    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    for start, end in ((0.0, 2.0), (2.0, 4.0), (4.0, 6.0)):
        sequence_service.add_sequence(proj, service, start, end)
    return proj, service


# --- utilitaires purs -----------------------------------------------------------------------------


def test_sub_progress_maps_into_slice_and_clamps():
    seen = []
    report = sub_progress(seen.append, 0.2, 0.6)

    report(0.0)
    report(0.5)
    report(1.0)
    report(7.0)   # au-delà de 1 : borné
    report(-3.0)  # en deçà de 0 : borné

    assert seen == pytest.approx([0.2, 0.4, 0.6, 0.6, 0.2])


def test_sub_progress_none_stays_none():
    assert sub_progress(None, 0.0, 1.0) is None


def test_sub_progress_nests():
    seen = []
    outer = sub_progress(seen.append, 0.5, 1.0)
    inner = sub_progress(outer, 0.0, 0.5)

    inner(1.0)

    assert seen == pytest.approx([0.75])


def test_wav_duration_reads_wav_and_tolerates_bad_files(project, tmp_path):
    proj, _ = project
    assert wav_duration(proj.original_audio_path) == pytest.approx(6.0)

    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"pas un wav")
    assert wav_duration(str(bad)) == 0.0
    assert wav_duration(str(tmp_path / "absent.wav")) == 0.0


# --- FFmpegService ---------------------------------------------------------------------------------


def test_ffmpeg_service_operations_report_progress(project, tmp_path):
    proj, service = project
    paths = [seq.audio_path for seq in proj.sequences]

    for name, run in {
        "apply_filters": lambda cb: service.apply_filters(paths[0], str(tmp_path / "f.wav"), "volume=2", cb),
        "export_audio": lambda cb: service.export_audio(paths[0], str(tmp_path / "e.mp3"), "mp3", "192", cb),
        "concat_audio": lambda cb: service.concat_audio(paths, str(tmp_path / "c.wav"), cb),
        "crossfade": lambda cb: service.concat_with_crossfade(paths, str(tmp_path / "x.wav"), 0.3, cb),
    }.items():
        values: list[float] = []
        run(values.append)
        _assert_valid_progress(values)


# --- services d'export / traitement ----------------------------------------------------------------


def test_export_project_reports_monotone_progress_to_one(project, tmp_path):
    proj, service = project
    values: list[float] = []

    export_project(proj, service, str(tmp_path / "out.mp3"), "MP3", "192", on_progress=values.append)

    _assert_valid_progress(values)


def test_export_project_with_normalization_and_crossfade_reports_progress(project, tmp_path):
    proj, service = project
    proj.crossfade_duration = 0.3
    values: list[float] = []

    export_project(
        proj, service, str(tmp_path / "out.wav"), "WAV", "16", normalize_lufs=-16.0, on_progress=values.append
    )

    _assert_valid_progress(values)


def test_separate_export_progress_covers_every_sequence(project, tmp_path):
    proj, service = project
    values: list[float] = []

    written = export_sequences_separately(
        proj, service, str(tmp_path / "seqs"), "WAV", "16", normalize_lufs=-16.0, on_progress=values.append
    )

    assert len(written) == 3
    _assert_valid_progress(values)
    # Trois séquences : la progression passe par la fin de chaque tiers.
    assert any(v == pytest.approx(1 / 3) for v in values)
    assert any(v == pytest.approx(2 / 3) for v in values)


def test_process_sequence_reports_progress(project):
    proj, service = project
    sequence = proj.sequences[0]
    sequence.audio_settings.gain = 3.0
    values: list[float] = []

    process_sequence(proj, sequence, service, on_progress=values.append)

    _assert_valid_progress(values)


def test_process_sequence_without_processing_still_completes_progress(project):
    proj, service = project
    values: list[float] = []

    result = process_sequence(proj, proj.sequences[0], service, on_progress=values.append)

    assert result is None
    assert values[-1] == pytest.approx(1.0)


# --- worker et interface ---------------------------------------------------------------------------


def test_worker_relays_progress_as_percent(qtbot):
    def task(report):
        report(0.25)
        report(1.5)  # borné à 100 %
        return "ok"

    worker = FFmpegTaskWorker(task, with_progress=True)
    percents = []
    worker.progress.connect(percents.append)

    with qtbot.waitSignal(worker.succeeded, timeout=3000) as blocker:
        worker.start()
    worker.wait(2000)

    assert blocker.args == ["ok"]
    assert percents == [25, 100]


def test_worker_without_progress_calls_task_without_argument(qtbot):
    worker = FFmpegTaskWorker(lambda: 42)

    with qtbot.waitSignal(worker.succeeded, timeout=3000) as blocker:
        worker.start()
    worker.wait(2000)

    assert blocker.args == [42]


def test_export_dialog_progress_bar_is_determinate_and_fed(qtbot, project, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    proj, service = project
    dialog = ExportDialog(proj, service)
    qtbot.addWidget(dialog)
    assert (dialog._progress_bar.minimum(), dialog._progress_bar.maximum()) == (0, 100)

    seen = []
    dialog._progress_bar.valueChanged.connect(seen.append)
    dialog._path_edit.setText(str(tmp_path / "out.wav"))
    dialog._on_export_clicked()
    qtbot.waitUntil(lambda: "terminé" in dialog._status_label.text().lower(), timeout=10000)
    qtbot.waitUntil(lambda: dialog._worker.isFinished(), timeout=3000)

    assert seen and max(seen) == 100
    assert seen == sorted(seen)


def test_processing_panel_progress_bar_is_determinate_and_fed(qtbot, project):
    proj, service = project
    sequence = proj.sequences[0]
    panel = AudioProcessingPanel(service)
    qtbot.addWidget(panel)
    panel.set_project(proj)
    panel.set_sequence(sequence)
    assert (panel._progress_bar.minimum(), panel._progress_bar.maximum()) == (0, 100)

    seen = []
    panel._progress_bar.valueChanged.connect(seen.append)
    panel._gain_slider.set_value(3.0)
    with qtbot.waitSignal(panel.processed, timeout=10000):
        panel._on_apply_clicked()

    assert seen and max(seen) == 100
