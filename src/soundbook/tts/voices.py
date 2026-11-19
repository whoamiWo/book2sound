"""Kokoro voice catalogue.

Source: the Kokoro-82M model card (hexgrad/Kokoro-82M) voice list, kept here so
``epub2m4b voices`` works without downloading the model. Only the metadata is
bundled; no weights, no audio samples.

Language codes follow misaki's ``KPipeline(lang_code=...)`` convention:
``a`` = American English, ``b`` = British English, ``z`` = Mandarin Chinese,
``j`` = Japanese, ``e`` = Spanish, ``f`` = French, ``h`` = Hindi,
``i`` = Italian, ``p`` = Brazilian Portuguese.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Voice:
    id: str
    lang_code: str
    language: str
    gender: str  # "female" | "male"


def _v(voice_id: str, lang_code: str, language: str) -> Voice:
    gender = "female" if voice_id[1] == "f" else "male"
    return Voice(voice_id, lang_code, language, gender)


# Mandarin Chinese (Kokoro v1.0 added the z* set; names as published).
ZH_VOICES = tuple(
    _v(v, "z", "zh")
    for v in (
        "zf_xiaobei",
        "zf_xiaoni",
        "zf_xiaoxiao",
        "zf_xiaoyi",
        "zm_yunjian",
        "zm_yunxi",
        "zm_yunxia",
        "zm_yunyang",
    )
)

EN_VOICES = tuple(
    _v(v, code, "en")
    for code, ids in (
        ("a", ("af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore",
               "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
               "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
               "am_onyx", "am_puck", "am_santa")),
        ("b", ("bf_alice", "bf_emma", "bf_isabella", "bf_lily",
               "bm_daniel", "bm_fable", "bm_george", "bm_lewis")),
    )
    for v in ids
)

OTHER_VOICES = tuple(
    _v(v, code, lang)
    for code, lang, ids in (
        ("j", "ja", ("jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo")),
        ("e", "es", ("ef_dora", "em_alex", "em_santa")),
        ("f", "fr", ("ff_siwis",)),
        ("h", "hi", ("hf_alpha", "hf_beta", "hm_omega", "hm_psi")),
        ("i", "it", ("if_sara", "im_nicola")),
        ("p", "pt", ("pf_dora", "pm_alex", "pm_santa")),
    )
    for v in ids
)

ALL_VOICES: tuple[Voice, ...] = ZH_VOICES + EN_VOICES + OTHER_VOICES
BY_ID: dict[str, Voice] = {v.id: v for v in ALL_VOICES}

DEFAULT_ZH_VOICE = "zf_xiaobei"


def lang_code_for(voice_id: str, default: str = "z") -> str:
    """Infer ``KPipeline(lang_code=...)`` from a voice id.

    Unknown ids (custom/community voices) fall back to ``default`` so users can
    still pass anything the installed model supports; ``SOUNDBOOK_KOKORO_LANG``
    overrides this in the backend.
    """

    voice = BY_ID.get(voice_id)
    if voice is not None:
        return voice.lang_code
    if len(voice_id) >= 2 and voice_id[1] in "fm":
        return voice_id[0]
    return default


def voices_for_lang(lang_code: str) -> tuple[Voice, ...]:
    return tuple(v for v in ALL_VOICES if v.lang_code == lang_code)
