PRIORITY_RULES = {
    "FIRE":       {"HIGH": "CRITICAL", "MEDIUM": "HIGH",   "LOW": "MEDIUM"},
    "FLOOD":      {"HIGH": "HIGH",     "MEDIUM": "MEDIUM", "LOW": "LOW"},
    "EARTHQUAKE": {"HIGH": "CRITICAL", "MEDIUM": "HIGH",   "LOW": "MEDIUM"},
    "STORM":      {"HIGH": "HIGH",     "MEDIUM": "MEDIUM", "LOW": "LOW"},
    "ACCIDENT":   {"HIGH": "HIGH",     "MEDIUM": "MEDIUM", "LOW": "LOW"},
}

DEFAULT_PRIORITY = "MEDIUM"

def calculate_priority(incident_type: str, severity: str):
    t = (incident_type or "").upper()
    s = (severity or "").upper()
    rules = PRIORITY_RULES.get(t)
    if rules and s in rules:
        return rules[s], f"{t} + {s} severity"
    fallback = {"HIGH": "HIGH", "LOW": "LOW"}.get(s, DEFAULT_PRIORITY)
    return fallback, f"fallback rule: severity={s}"