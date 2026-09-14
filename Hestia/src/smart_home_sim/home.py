"""Weighted home topology and deterministic shortest paths."""

from __future__ import annotations

from itertools import pairwise

import networkx as nx

from smart_home_sim.schema import ConnectionConfig, Scenario


class HomeGraph:
    def __init__(self, scenario: Scenario) -> None:
        self._graph = nx.Graph()
        self._graph.add_nodes_from(sorted(room.id for room in scenario.rooms))
        self._connections: dict[tuple[str, str], ConnectionConfig] = {}
        for connection in sorted(
            scenario.connections,
            key=lambda item: (min(item.source, item.target), max(item.source, item.target)),
        ):
            self._graph.add_edge(
                connection.source,
                connection.target,
                weight=connection.travel_seconds,
            )
            self._connections[self._key(connection.source, connection.target)] = connection

    def shortest_path(self, source: str, target: str) -> list[str]:
        # 同距離経路でも頂点ID順で一意になるよう、全最短経路から選択する。
        paths = nx.all_shortest_paths(self._graph, source, target, weight="weight")
        return min((list(path) for path in paths), key=lambda path: tuple(path))

    def connection(self, source: str, target: str) -> ConnectionConfig:
        return self._connections[self._key(source, target)]

    def travel_seconds(self, source: str, target: str) -> float:
        path = self.shortest_path(source, target)
        return sum(
            self.connection(current, following).travel_seconds
            for current, following in pairwise(path)
        )

    @staticmethod
    def _key(source: str, target: str) -> tuple[str, str]:
        return (source, target) if source <= target else (target, source)
