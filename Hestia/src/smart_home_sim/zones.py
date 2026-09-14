"""Deterministic weighted paths inside configured physical rooms."""

from __future__ import annotations

import networkx as nx

from smart_home_sim.schema import RoomConfig, Scenario, ZoneConnectionConfig


class ZoneGraph:
    def __init__(self, scenario: Scenario) -> None:
        self._graphs: dict[str, nx.Graph] = {}
        self._connections: dict[tuple[str, str], ZoneConnectionConfig] = {}
        self._room_by_zone: dict[str, str] = {}
        for room in sorted(scenario.rooms, key=lambda item: item.id):
            if not room.zones:
                continue
            graph = nx.Graph()
            graph.add_nodes_from(sorted(zone.id for zone in room.zones))
            for zone in sorted(room.zones, key=lambda item: item.id):
                self._room_by_zone[zone.id] = room.id
            for connection in sorted(
                room.zone_connections,
                key=lambda item: (min(item.source, item.target), max(item.source, item.target)),
            ):
                graph.add_edge(
                    connection.source,
                    connection.target,
                    weight=connection.travel_seconds,
                )
                self._connections[self._key(connection.source, connection.target)] = connection
            self._graphs[room.id] = graph

    def shortest_path(self, room_id: str, source: str, target: str) -> list[str]:
        graph = self._graphs[room_id]
        paths = nx.all_shortest_paths(graph, source, target, weight="weight")
        return min((list(path) for path in paths), key=lambda path: tuple(path))

    def travel_seconds(self, room_id: str, source: str, target: str) -> float:
        graph = self._graphs[room_id]
        return float(nx.shortest_path_length(graph, source, target, weight="weight"))

    def connection(self, source: str, target: str) -> ZoneConnectionConfig:
        return self._connections[self._key(source, target)]

    def room_for(self, zone_id: str) -> str:
        return self._room_by_zone[zone_id]

    @staticmethod
    def destination_zone(room: RoomConfig, requested_zone_id: str | None) -> str | None:
        if not room.zones:
            return None
        return requested_zone_id or room.default_zone_id

    @staticmethod
    def _key(source: str, target: str) -> tuple[str, str]:
        return (source, target) if source <= target else (target, source)
