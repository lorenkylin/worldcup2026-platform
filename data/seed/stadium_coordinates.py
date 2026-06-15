"""2026 世界杯 16 座球场经纬度.

来源：Google Maps / 维基百科公开坐标，赛前一周核对。
时区基于球场所在城市。
"""

# name_en -> (latitude, longitude, timezone)
STADIUM_COORDS = {
    "Estadio Azteca": (19.3028, -99.1505, "America/Mexico_City"),
    "Estadio Akron": (20.6816, -103.4625, "America/Mexico_City"),
    "Estadio BBVA": (25.6692, -100.2439, "America/Mexico_City"),
    "BMO Field": (43.6332, -79.4186, "America/Toronto"),
    "BC Place": (49.2768, -123.1117, "America/Vancouver"),
    "SoFi Stadium": (33.9534, -118.3387, "America/Los_Angeles"),
    "Levi's Stadium": (37.4032, -121.9696, "America/Los_Angeles"),
    "MetLife Stadium": (40.8136, -74.0744, "America/New_York"),
    "Gillette Stadium": (42.0909, -71.2643, "America/New_York"),
    "NRG Stadium": (29.6847, -95.4107, "America/Chicago"),
    "AT&T Stadium": (32.7473, -97.0945, "America/Chicago"),
    "Lincoln Financial Field": (39.9008, -75.1675, "America/New_York"),
    "Mercedes-Benz Stadium": (33.7553, -84.4006, "America/New_York"),
    "Lumen Field": (47.5952, -122.3316, "America/Los_Angeles"),
    "Hard Rock Stadium": (25.9580, -80.2389, "America/New_York"),
    "GEHA Field at Arrowhead": (39.0489, -94.4839, "America/Chicago"),
    "GEHA Field at Arrowhead Stadium": (39.0489, -94.4839, "America/Chicago"),
}