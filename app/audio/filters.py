"""Construction des chaînes de filtres FFmpeg pour le nettoyage/l'amélioration audio.

Fonctions pures (aucune exécution ffmpeg ici) : chaque fonction retourne un
fragment de filtre `-af`, ou None/liste vide si rien à appliquer. La
composition de la chaîne complète se fait dans app/services/audio_processor.py.
"""

from app.models.audio_settings import AudioSettings

_NOISE_REDUCTION_NR = {"faible": 6, "moyenne": 12, "forte": 20}

# Attaque/relâchement d'une compression douce de voix parlée (§21) : seuls le seuil et le
# ratio sont réglables, ces deux constantes de temps conviennent à la parole dans tous les cas.
_COMPRESSION_ATTACK_MS = 5
_COMPRESSION_RELEASE_MS = 50
_COMPRESSION_MAKEUP_DB = 2
# En deçà de cet écart, la correction de crête est inaudible et ne vaut pas un filtre de plus.
_MIN_PEAK_CORRECTION_DB = 0.05


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


def compression_filter(ratio: float = 2.5, threshold_db: float = -18.0) -> str:
    """Compression douce : `ratio` (2,5 : 1) et `threshold_db` (-18 dB) sont les deux réglages exposés."""
    return (
        f"acompressor=threshold={threshold_db}dB:ratio={ratio}"
        f":attack={_COMPRESSION_ATTACK_MS}:release={_COMPRESSION_RELEASE_MS}:makeup={_COMPRESSION_MAKEUP_DB}"
    )


def normalize_filter(mode: str, target_lufs: float) -> str:
    """Normalisation en loudness (EBU R128) ; `mode` autre que « loudness » retombe sur un nivellement dynamique.

    La normalisation par crête n'entre pas ici : elle demande de mesurer le fichier au préalable
    (voir `peak_normalize_filter`), ce qu'une fonction pure ne peut pas faire."""
    if mode == "loudness":
        return f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
    return "dynaudnorm"


def peak_normalize_filter(target_dbfs: float, measured_peak_db: float) -> str | None:
    """Gain qui amène la crête mesurée exactement à `target_dbfs` ; None si l'écart est négligeable.

    C'est la vraie normalisation par crête : un gain constant, donc sans effet sur la dynamique
    (contrairement à `dynaudnorm`, qui la comprime)."""
    correction = target_dbfs - measured_peak_db
    if abs(correction) < _MIN_PEAK_CORRECTION_DB:
        return None
    return f"volume={correction:.2f}dB"


def build_filter_chain(
    settings: AudioSettings, duration: float, measured_peak_db: float | None = None
) -> str | None:
    """Compose la chaîne complète dans l'ordre : nettoyage -> EQ -> compression -> normalisation -> gain -> fades.

    `measured_peak_db` est la crête du fichier source, mesurée en amont : elle n'est nécessaire
    qu'en normalisation par crête, et son absence fait simplement sauter cette étape (le reste
    de la chaîne, lui, ne dépend d'aucune mesure)."""
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
        filters.append(compression_filter(settings.compression_ratio, settings.compression_threshold_db))

    if settings.normalize:
        if settings.normalize_mode == "loudness":
            filters.append(normalize_filter("loudness", settings.normalize_target_lufs))
        elif measured_peak_db is not None:
            peak = peak_normalize_filter(settings.normalize_peak_dbfs, measured_peak_db)
            if peak:
                filters.append(peak)

    gain = gain_filter(settings.gain)
    if gain:
        filters.append(gain)

    filters.extend(fade_filters(settings.fade_in, settings.fade_out, duration))

    return ",".join(filters) if filters else None
