PRIORITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

# Base priority ตาม incident_type (ใช้เสมอ ไม่สนว่า severity จะเป็นอะไร)
DEFAULT_PRIORITY_BY_TYPE = {
    "EARTHQUAKE": "HIGH",
    "FLOOD":      "MEDIUM",
    "STORM":      "MEDIUM",
}

# ขั้นต่ำของแต่ละ incident_type (floor)
FLOOR_PRIORITY = {
    "EARTHQUAKE": "MEDIUM",
    "FLOOD":      "LOW",
    "STORM":      "LOW",
}

# Keywords สำหรับ boost priority
BOOST_KEYWORDS = [
    "ติดอยู่", "trapped",
    "เสียชีวิต", "dead", "died",
    "บาดเจ็บสาหัส",
    "โรงพยาบาล", "hospital",
    "โรงเรียน", "school",
    "มหาวิทยาลัย", "university",
    "หลายร้อย", "หลายพัน", "hundreds", "thousands",
    "อพยพ", "evacuate",
    "ถล่ม", "collapsed",
]

# Keywords สำหรับ downgrade priority
DOWNGRADE_KEYWORDS = [
    "เล็กน้อย", "minor",
    "เบาๆ", "slight",
    "ขัง", "waterlogged",
    "ขัดการจราจร", "traffic",
]

# Keywords รุนแรง (ถ้าไม่มีเลยและ affected_count < 50 → downgrade)
SERIOUS_KEYWORDS = [
    "เสียหาย", "damage",
    "ติดอยู่", "trapped",
    "บาดเจ็บ", "injured",
    "เสียชีวิต", "dead",
    "อพยพ", "evacuate",
    "ถล่ม", "collapsed",
    "โรงพยาบาล", "hospital",
    "โรงเรียน", "school",
    "มหาวิทยาลัย", "university",
]


def _contains_any(text: str, keywords: list) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def calculate_priority(incident_type: str, severity: str = None,
                       affected_count: int = None, description: str = "",
                       address_name: str = "") -> tuple:

    t = (incident_type or "UNKNOWN").upper()
    combined_text = f"{description or ''} {address_name or ''}".strip()

    # Step 1 — Base priority (ใช้ DEFAULT เสมอ ไม่สนว่า severity จะเป็นอะไร)
    base_priority = DEFAULT_PRIORITY_BY_TYPE.get(t, "MEDIUM")
    base_index = PRIORITY_ORDER.index(base_priority)
    reason_parts = [f"{t} default={base_priority}"]

    # Step 2 — Boost (max +2)
    boost = 0
    boost_reasons = []

    if affected_count is not None:
        if affected_count >= 500:
            boost += 2
            boost_reasons.append(f"affected_count={affected_count}(>=500)")
        elif affected_count >= 100:
            boost += 1
            boost_reasons.append(f"affected_count={affected_count}(>=100)")

    if _contains_any(combined_text, BOOST_KEYWORDS):
        boost += 1
        matched = [kw for kw in BOOST_KEYWORDS if kw.lower() in combined_text.lower()]
        boost_reasons.append(f"keyword: {', '.join(matched[:3])}")

    boost = min(boost, 2)

    # Step 3 — Downgrade (max -2)
    downgrade = 0
    downgrade_reasons = []

    if affected_count is not None and affected_count < 20:
        downgrade += 1
        downgrade_reasons.append(f"affected_count={affected_count}(<20)")

    if _contains_any(combined_text, DOWNGRADE_KEYWORDS):
        downgrade += 1
        matched = [kw for kw in DOWNGRADE_KEYWORDS if kw.lower() in combined_text.lower()]
        downgrade_reasons.append(f"keyword: {', '.join(matched[:3])}")

    if (not _contains_any(combined_text, SERIOUS_KEYWORDS)
            and affected_count is not None and affected_count < 50):
        downgrade += 1
        downgrade_reasons.append("no serious keyword + affected_count<50")

    downgrade = min(downgrade, 2)

    # Step 4 — คำนวณ final priority
    final_index = base_index + boost - downgrade

    # Step 5 — Apply floor
    floor = FLOOR_PRIORITY.get(t, "LOW")
    floor_index = PRIORITY_ORDER.index(floor)
    final_index = max(final_index, floor_index)

    # Clamp ให้อยู่ใน range
    final_index = max(0, min(final_index, len(PRIORITY_ORDER) - 1))
    final_priority = PRIORITY_ORDER[final_index]

    # Build decision reason
    if boost_reasons:
        reason_parts.append(f"boost +{boost}: {'; '.join(boost_reasons)}")
    if downgrade_reasons:
        reason_parts.append(f"downgrade -{downgrade}: {'; '.join(downgrade_reasons)}")
    if final_index == floor_index and base_index + boost - downgrade < floor_index:
        reason_parts.append(f"floor={floor}")

    decision_reason = " | ".join(reason_parts)

    return final_priority, decision_reason