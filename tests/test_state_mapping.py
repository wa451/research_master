from __future__ import annotations

import unittest

import pandas as pd

from src.behavior_pattern_mining.states.state_mapping import (
    find_nearest_representative_vector,
    map_vector_to_state,
)
from src.behavior_pattern_mining.visualization.state_transition_visualizer import (
    StateTransitionVisualizer,
)


class StateMappingTests(unittest.TestCase):
    def test_nearest_mapping_keeps_representative_order_for_equal_distance(self) -> None:
        representatives = [(1, 0), (0, 1)]

        nearest = find_nearest_representative_vector(
            (1, 1),
            representatives,
            hamming_threshold=1,
        )

        self.assertEqual(nearest, (1, 0))

    def test_hamming_threshold_is_inclusive(self) -> None:
        representatives = [(1, 0, 0)]

        self.assertEqual(
            find_nearest_representative_vector(
                (1, 1, 0),
                representatives,
                hamming_threshold=1,
            ),
            (1, 0, 0),
        )
        self.assertIsNone(
            find_nearest_representative_vector(
                (1, 1, 0),
                representatives,
                hamming_threshold=0,
            )
        )

    def test_exact_match_does_not_depend_on_hamming_threshold(self) -> None:
        mapping = {(1, 0): "状態1"}

        self.assertEqual(
            map_vector_to_state((1, 0), mapping, hamming_threshold=-1),
            "状態1",
        )

    def test_empty_representative_mapping_returns_unknown_state(self) -> None:
        self.assertEqual(
            map_vector_to_state((1, 0), {}, hamming_threshold=1),
            "その他",
        )

    def test_visualizer_reuses_mapping_for_repeated_raw_states(self) -> None:
        visualizer = StateTransitionVisualizer(hamming_threshold=1)
        visualizer.representative_states = [(1, 0), (0, 1)]
        state_vectors = pd.DataFrame(
            [[1, 1], [1, 1], [0, 0]],
            columns=["Kitchen", "Bedroom"],
        )
        mapping_cache: dict[tuple[int, ...], tuple[int, ...] | str] = {}

        mapped_states = visualizer._map_state_vectors(
            state_vectors,
            mapping_cache=mapping_cache,
        )

        self.assertEqual(mapped_states, [(1, 0), (1, 0), (1, 0)])
        self.assertEqual(len(mapping_cache), 2)


if __name__ == "__main__":
    unittest.main()
