CORE_THEMES = [
    "INFLATION",
    "LABOR_MARKETS",
    "GROWTH_OUTLOOK",
    "POLICY_STANCE",
    "FINANCIAL_CONDITIONS",
    "HOUSING",
    "CONSUMER_SPENDING",
    "GLOBAL_FACTORS",
    "BALANCE_SHEET",
    "FINANCIAL_STABILITY",
]

THEME_KEYWORDS = {
    "INFLATION": ["inflation", "prices", "price stability", "disinflation", "pce", "cpi"],
    "LABOR_MARKETS": ["labor market", "labor markets", "employment", "jobs", "job growth", "wages", "unemployment", "payroll"],
    "GROWTH_OUTLOOK": ["growth", "gdp", "activity", "recession", "demand", "output"],
    "POLICY_STANCE": ["policy", "rates", "restrictive", "accommodative", "federal funds", "tightening", "easing"],
    "FINANCIAL_CONDITIONS": ["financial conditions", "credit", "lending", "yields", "market functioning"],
    "HOUSING": ["housing", "shelter", "rent", "home prices", "real estate"],
    "CONSUMER_SPENDING": ["consumer", "consumption", "spending", "household demand"],
    "GLOBAL_FACTORS": ["global", "international", "trade", "china", "europe", "geopolitical"],
    "BALANCE_SHEET": ["balance sheet", "qt", "quantitative tightening", "asset holdings"],
    "FINANCIAL_STABILITY": ["financial stability", "banking", "liquidity", "stress", "capital"],
}

HEDGING_WORDS = {
    "may",
    "might",
    "could",
    "appears",
    "appear",
    "seems",
    "seem",
    "somewhat",
    "generally",
    "largely",
    "possibly",
    "potentially",
    "uncertain",
    "uncertainty",
    "perhaps",
}

LOW_SIGNAL_PHRASES = {
    "federal reserve",
    "board of governors",
    "thank you",
    "good morning",
    "good afternoon",
    "good evening",
    "press release",
}

DEFAULT_PROMPT_VERSION = "v2"
DEFAULT_MODEL_VERSION = "claude-sonnet-4-20250514"
