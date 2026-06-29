"""Groundedness checks for generated behavior sequences."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def load_markov_edges(path: Path) -> Dict[Tuple[str, str], float]:
    if not path.exists():
        raise FileNotFoundError(f"Markov graph not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    edges = payload.get("edges", [])
    edge_probs: Dict[Tuple[str, str], float] = {}
    for edge in edges:
        from_state = edge.get("from")
        to_state = edge.get("to")
        prob = edge.get("probability")
        if isinstance(from_state, str) and isinstance(to_state, str) and isinstance(prob, (int, float)):
            edge_probs[(from_state, to_state)] = float(prob)
    return edge_probs


def load_patterns(path: Path) -> List[Tuple[str, List[str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Invalid pattern format (list expected): {path}")

    patterns: List[Tuple[str, List[str]]] = []
    for item in payload:
        if isinstance(item, dict):
            seq = item.get("遷移のシーケンス") or item.get("sequence")
            name = item.get("パターン名") or ""
            if isinstance(seq, list) and all(isinstance(s, str) for s in seq):
                patterns.append((str(name), seq))
            continue
        if isinstance(item, list) and all(isinstance(s, str) for s in item):
            patterns.append(("", item))
            continue
        raise ValueError(f"Invalid pattern item: {item}")
    return patterns


def iter_pattern_files(root: Path, pattern: str) -> Iterable[Path]:
    return root.glob(pattern)


def check_sequence(
    sequence: List[str],
    edge_probs: Dict[Tuple[str, str], float],
    probability_threshold: float,
    min_len: int,
    max_len: int,
) -> Tuple[bool, dict]:
    length_ok = min_len <= len(sequence) <= max_len
    self_loops: List[str] = []
    missing_edges: List[str] = []
    low_prob_edges: List[str] = []

    for i in range(len(sequence) - 1):
        src = sequence[i]
        dst = sequence[i + 1]
        if src == dst:
            self_loops.append(f"{src}->{dst}")
        prob = edge_probs.get((src, dst))
        if prob is None:
            missing_edges.append(f"{src}->{dst}")
        elif prob < probability_threshold:
            low_prob_edges.append(f"{src}->{dst}({prob:.3f})")

    ok = length_ok and not self_loops and not missing_edges and not low_prob_edges
    details = {
        "length_ok": length_ok,
        "self_loops": self_loops,
        "missing_edges": missing_edges,
        "low_prob_edges": low_prob_edges,
    }
    return ok, details
