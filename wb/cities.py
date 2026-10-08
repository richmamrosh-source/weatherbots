"""Verification sites: NWS climate-report (CLI) stations with coordinates.
ICAO id, display name, state, lat, lon."""

CITIES = [
    ("KBOS", "Boston", "MA", 42.36, -71.01), ("KORH", "Worcester", "MA", 42.27, -71.88), ("KPVD", "Providence", "RI", 41.72, -71.43),
    ("KBDL", "Hartford", "CT", 41.94, -72.68), ("KBDR", "Bridgeport", "CT", 41.16, -73.13), ("KISP", "Islip", "NY", 40.79, -73.10),
    ("KNYC", "Central Park", "NY", 40.78, -73.97), ("KEWR", "Newark", "NJ", 40.69, -74.17), ("KACY", "Atlantic City", "NJ", 39.45, -74.57),
    ("KPHL", "Philadelphia", "PA", 39.87, -75.23), ("KILG", "Wilmington", "DE", 39.67, -75.60), ("KBWI", "Baltimore", "MD", 39.17, -76.68),
    ("KDCA", "Washington", "DC", 38.85, -77.04), ("KIAD", "Dulles", "VA", 38.94, -77.46), ("KRIC", "Richmond", "VA", 37.51, -77.32),
    ("KORF", "Norfolk", "VA", 36.90, -76.19), ("KRDU", "Raleigh", "NC", 35.88, -78.79), ("KGSO", "Greensboro", "NC", 36.10, -79.94),
    ("KCLT", "Charlotte", "NC", 35.21, -80.94), ("KATL", "Atlanta", "GA", 33.64, -84.43), ("KBNA", "Nashville", "TN", 36.12, -86.68),
    ("KMEM", "Memphis", "TN", 35.06, -89.98), ("KTYS", "Knoxville", "TN", 35.81, -83.99), ("KSDF", "Louisville", "KY", 38.17, -85.74),
    ("KCVG", "Cincinnati", "OH", 39.05, -84.67), ("KCMH", "Columbus", "OH", 39.99, -82.88), ("KCLE", "Cleveland", "OH", 41.41, -81.85),
    ("KPIT", "Pittsburgh", "PA", 40.49, -80.23), ("KMDT", "Harrisburg", "PA", 40.19, -76.76), ("KAVP", "Scranton", "PA", 41.34, -75.73),
    ("KERI", "Erie", "PA", 42.08, -80.18), ("KBUF", "Buffalo", "NY", 42.94, -78.74), ("KROC", "Rochester", "NY", 43.12, -77.68),
    ("KSYR", "Syracuse", "NY", 43.11, -76.10), ("KALB", "Albany", "NY", 42.75, -73.80), ("KBGM", "Binghamton", "NY", 42.21, -75.98),
    ("KBTV", "Burlington", "VT", 44.47, -73.15), ("KCON", "Concord", "NH", 43.20, -71.50), ("KPWM", "Portland", "ME", 43.65, -70.31),
    ("KBGR", "Bangor", "ME", 44.81, -68.83), ("KCAR", "Caribou", "ME", 46.87, -68.02), ("KDTW", "Detroit", "MI", 42.23, -83.33),
    ("KGRR", "Grand Rapids", "MI", 42.88, -85.52), ("KORD", "Chicago", "IL", 41.98, -87.90), ("KMKE", "Milwaukee", "WI", 42.95, -87.90),
    ("KMSN", "Madison", "WI", 43.14, -89.35), ("KGRB", "Green Bay", "WI", 44.48, -88.13), ("KMSP", "Minneapolis", "MN", 44.88, -93.23),
    ("KDLH", "Duluth", "MN", 46.84, -92.19), ("KIND", "Indianapolis", "IN", 39.73, -86.27), ("KSTL", "St. Louis", "MO", 38.75, -90.37),
    ("KMCI", "Kansas City", "MO", 39.30, -94.71), ("KDSM", "Des Moines", "IA", 41.53, -93.66), ("KOMA", "Omaha", "NE", 41.30, -95.89),
    ("KLNK", "Lincoln", "NE", 40.85, -96.76), ("KICT", "Wichita", "KS", 37.65, -97.43), ("KTOP", "Topeka", "KS", 39.07, -95.63),
    ("KOKC", "Oklahoma City", "OK", 35.39, -97.60), ("KTUL", "Tulsa", "OK", 36.20, -95.89), ("KDFW", "Dallas–Fort Worth", "TX", 32.90, -97.04),
    ("KAMA", "Amarillo", "TX", 35.22, -101.71), ("KLBB", "Lubbock", "TX", 33.66, -101.82), ("KLIT", "Little Rock", "AR", 34.73, -92.22),
    ("KJAN", "Jackson", "MS", 32.32, -90.08), ("KBHM", "Birmingham", "AL", 33.57, -86.75), ("KMSY", "New Orleans", "LA", 29.99, -90.25),
    ("KFSD", "Sioux Falls", "SD", 43.58, -96.74), ("KRAP", "Rapid City", "SD", 44.05, -103.05), ("KBIS", "Bismarck", "ND", 46.77, -100.75),
    ("KFAR", "Fargo", "ND", 46.92, -96.81), ("KDEN", "Denver", "CO", 39.85, -104.66), ("KCOS", "Colorado Springs", "CO", 38.81, -104.70),
    ("KCYS", "Cheyenne", "WY", 41.16, -104.81), ("KSLC", "Salt Lake City", "UT", 40.79, -111.97), ("KBOI", "Boise", "ID", 43.57, -116.22),
    ("KABQ", "Albuquerque", "NM", 35.04, -106.62), ("KBIL", "Billings", "MT", 45.81, -108.54), ("KGTF", "Great Falls", "MT", 47.47, -111.38),
    ("KSEA", "Seattle", "WA", 47.44, -122.31), ("KGEG", "Spokane", "WA", 47.62, -117.53), ("KPDX", "Portland", "OR", 45.59, -122.60),
    ("KRNO", "Reno", "NV", 39.50, -119.77), ("KFLG", "Flagstaff", "AZ", 35.14, -111.67),
]

BY_ID = {c[0]: c for c in CITIES}

STATE_NAMES = {
    "MA": "Massachusetts", "RI": "Rhode Island", "CT": "Connecticut", "NY": "New York", "NJ": "New Jersey", "PA": "Pennsylvania",
    "DE": "Delaware", "MD": "Maryland", "DC": "District of Columbia", "VA": "Virginia", "NC": "North Carolina", "GA": "Georgia",
    "TN": "Tennessee", "KY": "Kentucky", "OH": "Ohio", "VT": "Vermont", "NH": "New Hampshire", "ME": "Maine", "MI": "Michigan",
    "IL": "Illinois", "WI": "Wisconsin", "MN": "Minnesota", "IN": "Indiana", "MO": "Missouri", "IA": "Iowa", "NE": "Nebraska",
    "KS": "Kansas", "OK": "Oklahoma", "TX": "Texas", "AR": "Arkansas", "MS": "Mississippi", "AL": "Alabama", "LA": "Louisiana",
    "SD": "South Dakota", "ND": "North Dakota", "CO": "Colorado", "WY": "Wyoming", "UT": "Utah", "ID": "Idaho", "NM": "New Mexico",
    "MT": "Montana", "WA": "Washington", "OR": "Oregon", "NV": "Nevada", "AZ": "Arizona", "WV": "West Virginia", "SC": "South Carolina",
}


def region_name(lat, lon):
    """Plain-English region for a storm centroid."""
    if lon > -80 and lat >= 41:
        return "Northeast"
    if lon > -81 and lat >= 37:
        return "Mid-Atlantic"
    if lon > -88 and lat < 37:
        return "Southeast"
    if lon > -90 and lat >= 40:
        return "Great Lakes"
    if lon > -92:
        return "Ohio and Tennessee Valleys"
    if lon > -103 and lat >= 41:
        return "Northern Plains"
    if lon > -103:
        return "Central and Southern Plains"
    return "West"
