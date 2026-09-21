"""Profils de traitement audio prédéfinis (§47) : point de départ pour un cas d'usage courant."""

from app.models.audio_settings import AudioSettings

AUDIO_PROFILES: dict[str, AudioSettings] = {
    "Voix parlée": AudioSettings(
        noise_reduction=True, noise_reduction_level="moyenne",
        de_hum=True, compression=True, normalize=True, normalize_mode="loudness",
    ),
    "Interview": AudioSettings(
        noise_reduction=True, noise_reduction_level="moyenne",
        de_hum=True, de_click=True, compression=True, normalize=True, normalize_mode="loudness",
    ),
    "Podcast": AudioSettings(
        noise_reduction=True, noise_reduction_level="faible",
        compression=True, normalize=True, normalize_mode="loudness", normalize_target_lufs=-16.0,
    ),
    # Salle sonorisée : on coupe le grondement de basses, on dégage la parole, on rattrape
    # le niveau souvent faible d'une captation au fond de la salle.
    "Conférence": AudioSettings(
        noise_reduction=True, noise_reduction_level="moyenne",
        de_hum=True, de_hum_freq=50,
        eq_bass_db=-3.0, eq_mid_db=2.0, eq_treble_db=1.5,
        compression=True, compression_ratio=2.5, compression_threshold_db=-18.0,
        normalize=True, normalize_mode="loudness", normalize_target_lufs=-16.0,
        gain=3.0, fade_in=0.04, fade_out=0.12,
    ),
    "Enregistrement micro": AudioSettings(
        noise_reduction=True, noise_reduction_level="moyenne",
        de_click=True, normalize=True, normalize_mode="peak",
    ),
    "Voix faible": AudioSettings(
        gain=6.0, compression=True, normalize=True, normalize_mode="loudness", normalize_target_lufs=-14.0,
    ),
}

CUSTOM_PROFILE_LABEL = "Personnalisé"
