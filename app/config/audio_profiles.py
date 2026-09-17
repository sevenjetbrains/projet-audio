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
    "Conférence": AudioSettings(
        noise_reduction=True, noise_reduction_level="forte",
        de_hum=True, normalize=True, normalize_mode="loudness",
    ),
    "Enregistrement microphone": AudioSettings(
        noise_reduction=True, noise_reduction_level="moyenne",
        de_click=True, normalize=True, normalize_mode="peak",
    ),
    "Voix faible": AudioSettings(
        gain=6.0, compression=True, normalize=True, normalize_mode="loudness", normalize_target_lufs=-14.0,
    ),
}

CUSTOM_PROFILE_LABEL = "Personnalisé"
