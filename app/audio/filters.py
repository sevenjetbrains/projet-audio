"""Construction des chaînes de filtres FFmpeg pour le nettoyage/l'amélioration audio.

Fonctions pures (aucune exécution ffmpeg ici) : chaque fonction retourne un
fragment de filtre `-af`, ou None/liste vide si rien à appliquer. La
composition de la chaîne complète se fait dans app/services/audio_processor.py.
"""

from app.models.audio_settings import AudioSettings

_NOISE_REDUCTION_NR = {"faible": 6, "moyenne": 12, "forte": 20}

# Valeurs par défaut de compression légère adaptées à une voix parlée (§21).
_COMPRESSION_DEFAULT = "acompressor=threshold=-18dB:ratio=3:attack=5:release=50:makeup=2"


def gain_filter(gain_db: float) -> str | None:
    if gain_db == 0:
        return None
    return f"volume={gain_db}dB"


def fade_filters(fade_in: float, fade_out: float, duration: float) -> list[str]:
    filters = []
    if fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        start = max(duration - fade_out, 0.0)
        filters.append(f"afade=t=out:st={start}:d={fade_out}")
    return filters


def noise_reduction_filter(level: str) -> str | None:
    nr = _NOISE_REDUCTION_NR.get(level)
    if nr is None:
        return None
    return f"afftdn=nr={nr}"


def de_hum_filters(freq: int) -> list[str]:
    """Notch filters sur la fréquence de ronflement et ses deux premières harmoniques."""
    return [f"bandreject=f={freq * n}:w=4" for n in (1, 2, 3)]


def de_click_filter() -> str:
    return "adeclick"


def eq_filters(bass_db: float, mid_db: float, treble_db: float) -> list[str]:
    filters = []
    if bass_db:
        filters.append(f"bass=g={bass_db}")
    if mid_db:
        filters.append(f"equalizer=f=1000:t=q:w=1:g={mid_db}")
    if treble_db:
        filters.append(f"treble=g={treble_db}")
    return filters


def compression_filter() -> str:
    return _COMPRESSION_DEFAULT


def normalize_filter(mode: str, target_lufs: float) -> str:
    if mode == "loudness":
        return f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
    return "dynaudnorm"


def build_filter_chain(settings: AudioSettings, duration: float) -> str | None:
    """Compose la chaîne complète dans l'ordre : nettoyage -> EQ -> compression -> normalisation -> gain -> fades."""
    filters: list[str] = []

    if settings.noise_reduction:
        nr = noise_reduction_filter(settings.noise_reduction_level)
        if nr:
            filters.append(nr)

    if settings.de_hum:
        filters.extend(de_hum_filters(settings.de_hum_freq))

    if settings.de_click:
        filters.append(de_click_filter())

    filters.extend(eq_filters(settings.eq_bass_db, settings.eq_mid_db, settings.eq_treble_db))

    if settings.compression:
        filters.append(compression_filter())

    if settings.normalize:
        filters.append(normalize_filter(settings.normalize_mode, settings.normalize_target_lufs))

    gain = gain_filter(settings.gain)
    if gain:
        filters.append(gain)

    filters.extend(fade_filters(settings.fade_in, settings.fade_out, duration))

    return ",".join(filters) if filters else None
