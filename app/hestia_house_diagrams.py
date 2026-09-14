"""Display-only topology metadata for Hestia evaluation 9 houses."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HouseConnection:
    source: str
    target: str
    door_sensor_id: str
    travel_seconds: int


ROOM_LABELS = {
    "bathroom": "浴室",
    "bedroom": "寝室",
    "hallway": "廊下",
    "kitchen": "キッチン",
    "living": "リビング",
    "outside": "屋外",
    "study": "書斎",
}

HOUSE_TITLES = {
    "compact": "compact (5空間)",
    "corridor": "corridor (6空間)",
    "branched": "branched (7空間)",
}

HOUSE_DESCRIPTIONS = {
    "compact": "リビングを中心に各空間へ接続",
    "corridor": "廊下を中心に各空間へ接続",
    "branched": "廊下中心の構成に、リビング経由の書斎を追加",
}

HOUSE_CONNECTIONS = {
    "compact": (
        HouseConnection("living", "bathroom", "D_bathroom", 10),
        HouseConnection("living", "bedroom", "D_bedroom", 10),
        HouseConnection("living", "kitchen", "D_kitchen", 10),
        HouseConnection("living", "outside", "D_outside", 10),
    ),
    "corridor": (
        HouseConnection("hallway", "bathroom", "D_bathroom", 10),
        HouseConnection("hallway", "bedroom", "D_bedroom", 10),
        HouseConnection("hallway", "kitchen", "D_kitchen", 10),
        HouseConnection("hallway", "living", "D_living", 10),
        HouseConnection("hallway", "outside", "D_outside", 10),
    ),
    "branched": (
        HouseConnection("hallway", "bathroom", "D_bathroom", 10),
        HouseConnection("hallway", "bedroom", "D_bedroom", 10),
        HouseConnection("hallway", "kitchen", "D_kitchen", 10),
        HouseConnection("hallway", "living", "D_living", 10),
        HouseConnection("hallway", "outside", "D_outside", 10),
        HouseConnection("living", "study", "D_study", 15),
    ),
}


def house_rooms(house: str) -> tuple[str, ...]:
    connections = HOUSE_CONNECTIONS[house]
    return tuple(sorted({room for item in connections for room in (item.source, item.target)}))


def house_topology_dot(house: str) -> str:
    rooms = house_rooms(house)
    lines = [
        "graph house {",
        '  graph [bgcolor="transparent", pad="0.15", nodesep="0.25", ranksep="0.45"];',
        '  node [shape="box", style="rounded,filled", color="#64748B", '
        'fillcolor="#F8FAFC", fontname="Helvetica", fontsize="10"];',
        '  edge [color="#64748B", fontcolor="#475569", fontname="Helvetica", fontsize="8"];',
    ]
    for room in rooms:
        attributes = []
        if room in {"living", "hallway"}:
            attributes.extend(['fillcolor="#DBEAFE"', 'color="#2563EB"'])
        elif room == "outside":
            attributes.extend(['style="rounded,dashed,filled"', 'fillcolor="#F1F5F9"'])
        suffix = f", {', '.join(attributes)}" if attributes else ""
        lines.append(f'  "{room}" [label="{ROOM_LABELS[room]}\\n{room}"{suffix}];')
    for connection in HOUSE_CONNECTIONS[house]:
        label = f"{connection.door_sensor_id} / {connection.travel_seconds}秒"
        lines.append(f'  "{connection.source}" -- "{connection.target}" [label="{label}"];')
    lines.append("}")
    return "\n".join(lines)
