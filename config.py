"""Single source of truth for sleeve blend and macro stress constants."""

BASE_BLEND_WEIGHTS = {
    "cpm": 0.60,
    "ndx": 0.15,
    "val": 0.15,
    "rpv": 0.10,
}

SAHM_STRESS_BLEND_WEIGHTS = {
    "cpm": 0.50,
    "ndx": 0.15,
    "val": 0.15,
    "rpv": 0.20,
}

SAHM_STRESS_THRESHOLD = 0.50
SAHM_PUBLICATION_LAG_MONTHS = 1
SAHM_PUBLICATION_LAG_DAYS = 7

CROSS_SLEEVE_REALLOCATION_COST_BPS = 10.0

# Backward-compatible aliases used across production modules.
CPM_WEIGHT = BASE_BLEND_WEIGHTS["cpm"]
NDX_WEIGHT = BASE_BLEND_WEIGHTS["ndx"]
VAL_WEIGHT = BASE_BLEND_WEIGHTS["val"]
RPV_WEIGHT = BASE_BLEND_WEIGHTS["rpv"]
