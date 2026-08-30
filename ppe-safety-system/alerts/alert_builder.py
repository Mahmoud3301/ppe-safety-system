"""
Alert Builder Module — Bilingual (Arabic + English)
====================================================
Builds alert messages for PPE violations.
Returns both English and Arabic text for simultaneous TTS playback.
"""

import yaml
import os
from datetime import datetime

# ─── Load Config ────────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "config.yaml")
with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.safe_load(f)

VIOLATION_TO_PPE = CONFIG["classes"]["violation_to_ppe"]

# PPE names in Arabic
VIOLATION_TO_PPE_AR = {
    4: "بدلة السلامة",
    5: "قفازات السلامة",
    6: "نظارات الحماية",
    7: "خوذة السلامة",
    8: "قناع الوجه",
    9: "حذاء السلامة",
    "4": "بدلة السلامة",
    "5": "قفازات السلامة",
    "6": "نظارات الحماية",
    "7": "خوذة السلامة",
    "8": "قناع الوجه",
    "9": "حذاء السلامة",
}

# ─── Alert Templates ────────────────────────────────────────────────────────────
TEMPLATES_EN = {
    "single":   "⚠️ Warning! Worker {track_id} in {zone}: Missing {items}. Wear your {items} immediately.",
    "multiple": "🚨 Alert! Worker {track_id} in {zone}: Multiple PPE violations — missing {items}. Immediate action required!",
    "critical": "🔴 CRITICAL! Worker {track_id} in {zone}: Severe safety violation — missing {items}. Stop work and equip proper PPE now!",
}

TEMPLATES_AR = {
    "single":   "⚠️ تحذير! العامل {track_id} في {zone}: لا يرتدي {items}. ارتدِ {items} فوراً.",
    "multiple": "🚨 تنبيه! العامل {track_id} في {zone}: مخالفات متعددة — لا يرتدي {items}. مطلوب تصرف فوري!",
    "critical": "🔴 حرج! العامل {track_id} في {zone}: مخالفة سلامة خطيرة — لا يرتدي {items}. أوقف العمل وارتدِ معدات الحماية الآن!",
}

TTS_TEMPLATES_EN = {
    "single":   "Warning. Worker number {track_id} in {zone}. Not wearing {items}. Please wear safety equipment immediately.",
    "multiple": "Alert. Worker number {track_id} in {zone}. Multiple PPE violations. Missing {items}. Immediate action required.",
    "critical": "Critical alert. Worker number {track_id} in {zone}. Severe safety violation. Missing {items}. Stop work now.",
}

TTS_TEMPLATES_AR = {
    "single":   "تحذير. العامل رقم {track_id} في {zone}. لا يرتدي {items}. يرجى الالتزام بمعدات السلامة فوراً.",
    "multiple": "تنبيه. العامل رقم {track_id} في {zone}. مخالفات متعددة في معدات الحماية. لا يرتدي {items}. مطلوب تصرف فوري.",
    "critical": "تحذير حرج. العامل رقم {track_id} في {zone}. مخالفة سلامة خطيرة. لا يرتدي {items}. أوقف العمل فوراً.",
}


def _get_missing_items(violation_class_ids, lang="en"):
    """Map violation IDs to PPE names in the target language."""
    items = []
    lookup = VIOLATION_TO_PPE_AR if lang == "ar" else VIOLATION_TO_PPE
    for vid in violation_class_ids:
        vid_str = str(vid)
        if vid_str in lookup:
            items.append(lookup[vid_str])
        elif vid in lookup:
            items.append(lookup[vid])
    return items


def build_alert(track_id, violation_class_ids, zone_name="Work Zone", language="en"):
    """
    Build a bilingual alert for a detected violation.

    Returns:
        dict with 'text_en', 'text_ar', 'text', 'severity', 'timestamp', etc.
    """
    missing_en = _get_missing_items(violation_class_ids, "en")
    missing_ar = _get_missing_items(violation_class_ids, "ar")

    if not missing_en:
        return None

    # Determine severity
    n = len(missing_en)
    if n >= 3:
        severity = "critical"
    elif n >= 2:
        severity = "multiple"
    else:
        severity = "single"

    items_en = ", ".join(missing_en)
    items_ar = "، ".join(missing_ar) if missing_ar else items_en

    text_en = TEMPLATES_EN[severity].format(
        track_id=track_id, zone=zone_name, items=items_en
    )
    text_ar = TEMPLATES_AR[severity].format(
        track_id=track_id, zone=zone_name, items=items_ar
    )

    # Primary text depends on language setting
    text = text_ar if language == "ar" else text_en

    return {
        "text": text,
        "text_en": text_en,
        "text_ar": text_ar,
        "severity": severity,
        "timestamp": datetime.now().isoformat(),
        "track_id": track_id,
        "zone": zone_name,
        "missing_items": missing_en,
        "missing_items_ar": missing_ar,
        "violation_ids": list(violation_class_ids),
    }


def build_tts_texts(track_id, violation_class_ids, zone_name="Work Zone"):
    """
    Build clean TTS texts in both English and Arabic.

    Returns:
        (text_en, text_ar) tuple
    """
    missing_en = _get_missing_items(violation_class_ids, "en")
    missing_ar = _get_missing_items(violation_class_ids, "ar")

    if not missing_en:
        return None, None

    n = len(missing_en)
    if n >= 3:
        severity = "critical"
    elif n >= 2:
        severity = "multiple"
    else:
        severity = "single"

    items_en = " and ".join(missing_en)
    items_ar = " و ".join(missing_ar) if missing_ar else items_en

    text_en = TTS_TEMPLATES_EN[severity].format(
        track_id=track_id, zone=zone_name, items=items_en
    )
    text_ar = TTS_TEMPLATES_AR[severity].format(
        track_id=track_id, zone=zone_name, items=items_ar
    )

    return text_en, text_ar


# Keep backward compatibility
def build_alert_for_tts(track_id, violation_class_ids, zone_name="Work Zone", language="en"):
    """Legacy: Returns single-language TTS text."""
    text_en, text_ar = build_tts_texts(track_id, violation_class_ids, zone_name)
    if language == "ar":
        return text_ar
    return text_en


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Testing Bilingual Alert Builder")
    print("=" * 60)

    alert = build_alert(1, [7], "Construction Zone A")
    print(f"\n[EN] {alert['text_en']}")
    print(f"[AR] {alert['text_ar']}")

    alert = build_alert(2, [7, 5], "Construction Zone A")
    print(f"\n[EN] {alert['text_en']}")
    print(f"[AR] {alert['text_ar']}")

    text_en, text_ar = build_tts_texts(3, [7, 5, 6, 8], "Construction Zone A")
    print(f"\n[TTS EN] {text_en}")
    print(f"[TTS AR] {text_ar}")
