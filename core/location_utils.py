import re

US_STATE_MAP = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming"
}

# Reverse mapping: state name -> state code
STATE_TO_CODE = {v: k for k, v in US_STATE_MAP.items()}

COUNTRY_MAP = {
    "USA": "United States",
    "US": "United States",
    "United States": "United States",
    "UK": "United Kingdom",
    "IN": "India"
}

def normalize_location(raw_location):
    if not raw_location:
        return empty_loc(raw_location)

    raw = raw_location.strip()
    raw = raw.replace("---", " - ")

    # =========================
    # 1. CITY, STATE, COUNTRY
    # =========================
    if "," in raw:
        parts = [p.strip() for p in raw.split(",")]

        if len(parts) == 3:
            city, state, country = parts
            return build_loc(city, state, country)

        if len(parts) == 2:
            city, state = parts
            return build_loc(city, state, "United States")

    # =========================
    # 2. CITY STATE (Jasper TN)
    # =========================
    match = re.match(r"^(.+?)\s+([A-Z]{2})$", raw)
    if match:
        city = match.group(1)
        state_code = match.group(2)
        state = US_STATE_MAP.get(state_code)
        return build_loc(city, state, "United States")

    # =========================
    # 3. STATE - REMOTE
    # =========================
    if "-" in raw:
        parts = [p.strip() for p in raw.split("-")]

        if len(parts) == 2 and parts[1].lower() == "remote":
            place = parts[0]
            if place.upper() in COUNTRY_MAP:
                return build_loc("Remote", None, COUNTRY_MAP[place.upper()])
            return build_loc("Remote", place, "United States")

    # =========================
    # 4. REMOTE ONLY
    # =========================
    if "remote" in raw.lower():
        return build_loc("Remote", None, "United States")

    # =========================
    # 5. FALLBACK
    # =========================
    return empty_loc(raw)


def build_loc(city, state, country):
    state_code = None
    country_code = None

    if state:
        if state in STATE_TO_CODE:
            state_code = STATE_TO_CODE[state]
        elif state in US_STATE_MAP:
            state_code = state
            state = US_STATE_MAP[state]

    if country:
        if country.lower() in ["us", "usa"]:
            country = "United States"
        if country == "United States":
            country_code = "US"

    return {
        "city": city,
        "state": state,
        "state_code": state_code,
        "country": country,
        "country_code": country_code,
        "raw_location": f"{city} {state}" if state else city
    }


def empty_loc(raw):
    return {
        "city": None,
        "state": None,
        "state_code": None,
        "country": None,
        "country_code": None,
        "raw_location": raw
    }    
