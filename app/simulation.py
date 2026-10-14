"""Appliance catalogue and portable built-in daily load scenarios."""

from typing import Any

APPLIANCES: list[dict[str, Any]] = [
    {"id": "fan", "name": "Ceiling fan", "watts": 75, "category": "Comfort", "hint": "Leave it on through the night."},
    {"id": "tube", "name": "LED tube light", "watts": 20, "category": "Lighting", "hint": "Main room lighting."},
    {"id": "lamp", "name": "Study lamp", "watts": 9, "category": "Lighting", "hint": "Desk light for study sessions."},
    {"id": "laptop", "name": "Laptop", "watts": 65, "category": "Study", "hint": "Classes, notes, and calls."},
    {"id": "phone", "name": "Phone charger", "watts": 18, "category": "Essentials", "hint": "A short charging session."},
    {"id": "router", "name": "Wi-Fi router", "watts": 12, "category": "Always on", "hint": "Low draw, all day."},
    {"id": "cooler", "name": "Air cooler", "watts": 180, "category": "Comfort", "hint": "Warm afternoons and evenings."},
    {"id": "kettle", "name": "Electric kettle", "watts": 1500, "category": "Kitchen", "hint": "Short but high-power bursts."},
    {"id": "iron", "name": "Clothes iron", "watts": 1000, "category": "Laundry", "hint": "High-power, limited duration."},
    {"id": "speaker", "name": "Bluetooth speaker", "watts": 15, "category": "Leisure", "hint": "Music while relaxing."},
]
APPLIANCE_BY_ID = {item["id"]: item for item in APPLIANCES}


def block(label: str, start: int, end: int, appliance_ids: list[str]) -> dict[str, Any]:
    return {"label": label, "start_min": start, "end_min": end, "appliance_ids": appliance_ids}


BUILTIN_SCENARIOS: list[dict[str, Any]] = [
    {
        "slug": "resident-weekday", "name": "Standard weekday", "audience": "RESIDENT",
        "description": "A typical class or work day with a quiet daytime baseline and evening study.",
        "blocks": [
            block("Night rest", 0, 360, ["fan", "router"]),
            block("Morning rush", 360, 510, ["fan", "tube", "laptop", "phone", "router"]),
            block("Away at class", 510, 1020, ["router"]),
            block("Evening study", 1020, 1380, ["fan", "tube", "laptop", "lamp", "phone", "router"]),
            block("Lights out", 1380, 1440, ["fan", "router"]),
        ],
    },
    {
        "slug": "resident-exam", "name": "Exam preparation", "audience": "RESIDENT",
        "description": "More laptop and study-lamp hours, with the kettle used briefly.",
        "blocks": [
            block("Late-night revision", 0, 120, ["fan", "laptop", "lamp", "router"]),
            block("Sleep", 120, 480, ["fan", "router"]),
            block("Morning kettle", 480, 495, ["tube", "kettle", "phone", "router"]),
            block("Day study", 495, 1080, ["fan", "laptop", "lamp", "tube", "router"]),
            block("Dinner break", 1080, 1095, ["fan", "tube", "kettle", "router"]),
            block("Night revision", 1095, 1440, ["fan", "tube", "laptop", "lamp", "phone", "router"]),
        ],
    },
    {
        "slug": "resident-light", "name": "Light stay", "audience": "RESIDENT",
        "description": "A low-consumption day with just the router, evening light, and fan.",
        "blocks": [
            block("Router baseline", 0, 1140, ["router"]),
            block("Evening at home", 1140, 1320, ["fan", "tube", "router"]),
            block("Late night", 1320, 1440, ["fan", "router"]),
        ],
    },
    {
        "slug": "admin-hostel-weekday", "name": "Hostel weekday", "audience": "ADMIN",
        "description": "A typical resident day, suitable for previewing or applying to a selected room.",
        "blocks": [
            block("Night rest", 0, 360, ["fan", "router"]),
            block("Morning rush", 360, 510, ["fan", "tube", "kettle", "phone", "router"]),
            block("Class hours", 510, 1020, ["router"]),
            block("After class", 1020, 1140, ["fan", "tube", "laptop", "router"]),
            block("Evening kettle", 1140, 1155, ["fan", "tube", "kettle", "router"]),
            block("Study time", 1155, 1380, ["fan", "tube", "laptop", "lamp", "router"]),
            block("Sleep", 1380, 1440, ["fan", "router"]),
        ],
    },
    {
        "slug": "admin-heatwave", "name": "Summer heatwave", "audience": "ADMIN",
        "description": "A high-load day with the air cooler used through the hottest hours.",
        "blocks": [
            block("Warm night", 0, 420, ["fan", "router"]),
            block("Morning rush", 420, 435, ["fan", "tube", "kettle", "phone", "router"]),
            block("Class hours", 435, 660, ["router"]),
            block("Cooler during peak heat", 660, 1140, ["cooler", "fan", "router"]),
            block("Dinner break", 1140, 1155, ["fan", "tube", "kettle", "router"]),
            block("Evening study", 1155, 1410, ["fan", "tube", "laptop", "lamp", "router"]),
            block("Sleep", 1410, 1440, ["fan", "router"]),
        ],
    },
    {
        "slug": "admin-minimal", "name": "Vacant room baseline", "audience": "ADMIN",
        "description": "Router-only standby load for a room with no tenant present.",
        "blocks": [block("Standby", 0, 1440, ["router"])],
    },
]
