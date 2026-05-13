"""
状態遷移グラフのベースライン系列抽出スクリプト。（mode）

主な設定項目:
    - INPUT_JSON_DIR: モード別JSONが格納されたディレクトリ
    - MODE_NAMES: 対象モード名の一覧
    - THRESHOLD: 遷移確率の閾値
    - MIN_SEQUENCE_LENGTH / MAX_SEQUENCE_LENGTH: 探索する系列長（ノード数）
    - EXCLUDED_STATES: 除外する状態ID（例: "その他"）
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from experiment_config import DATASET_NAME, DAYS, HAMMING_THRESHOLD, N_STATES, ROOT_DIR


# =============================
# ユーザー設定（必要に応じて変更）
# =============================
INPUT_JSON_DIR = ROOT_DIR / "picture" / f"{DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
MODE_NAMES = ["Morning", "Daytime", "Night", "Midnight"]
THRESHOLD = 0.2 # 遷移確率の閾値（これ以上のものを選択）
MIN_SEQUENCE_LENGTH = 2 # 最小系列長（ノード数）
MAX_SEQUENCE_LENGTH = 4 # 最大系列長（ノード数）
EXCLUDED_STATES = ["その他"]
ALLOW_REVISIT = False
TOP_N = 0  # 0 の場合は全件表示
OUTPUT_DIR = (
    ROOT_DIR
    / "output"
    / f"{DATASET_NAME}_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
)
OUTPUT_FILE_PREFIX = (
    f"prob_threshold_sequences_{N_STATES}_{HAMMING_THRESHOLD}_{DAYS}days"
)


@dataclass(frozen=True)
class Edge:
    """Directed edge with transition probability."""

    src: str
    dst: str
    probability: float


@dataclass(frozen=True)
class SequenceResult:
    """A discovered path and its probability details."""

    states: Tuple[str, ...]
    step_probabilities: Tuple[float, ...]
    joint_probability: float


def build_mode_json_paths(input_dir: Path, mode_names: Sequence[str]) -> List[Tuple[str, Path]]:
    """指定したモード名に対応するJSONパスを順序付きで返す。"""
    mode_paths: List[Tuple[str, Path]] = []
    for mode_name in mode_names:
        path = input_dir / f"state_transition_{mode_name}.json"
        mode_paths.append((mode_name, path))
    return mode_paths


def load_graph(json_path: Path) -> Tuple[Dict[str, dict], List[Edge]]:
    with json_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    nodes = {
        node["state_id"]: node
        for node in payload.get("nodes", [])
        if isinstance(node, dict) and "state_id" in node
    }

    edges: List[Edge] = []
    for raw in payload.get("edges", []):
        if not isinstance(raw, dict):
            continue
        src = raw.get("from")
        dst = raw.get("to")
        prob = raw.get("probability")
        if not isinstance(src, str) or not isinstance(dst, str):
            continue
        try:
            prob_value = float(prob)
        except (TypeError, ValueError):
            continue
        edges.append(Edge(src=src, dst=dst, probability=prob_value))

    return nodes, edges


def filter_edges(
    edges: Sequence[Edge],
    threshold: float,
    excluded_states: Sequence[str],
) -> List[Edge]:
    excluded = set(excluded_states)
    filtered = [
        edge
        for edge in edges
        if edge.probability >= threshold
        and edge.src not in excluded
        and edge.dst not in excluded
    ]
    return filtered


def build_adjacency(edges: Sequence[Edge]) -> Dict[str, List[Tuple[str, float]]]:
    adjacency: Dict[str, List[Tuple[str, float]]] = {}
    for edge in edges:
        adjacency.setdefault(edge.src, []).append((edge.dst, edge.probability))

    for src in adjacency:
        adjacency[src].sort(key=lambda x: x[1], reverse=True)

    return adjacency


def discover_sequences(
    adjacency: Dict[str, List[Tuple[str, float]]],
    min_length: int,
    max_length: int,
    allow_revisit: bool,
) -> List[SequenceResult]:
    results: List[SequenceResult] = []

    def dfs(path_states: List[str], probs: List[float]) -> None:
        node_count = len(path_states)

        if min_length <= node_count <= max_length:
            joint = 1.0
            for p in probs:
                joint *= p
            results.append(
                SequenceResult(
                    states=tuple(path_states),
                    step_probabilities=tuple(probs),
                    joint_probability=joint,
                )
            )

        if node_count >= max_length:
            return

        current = path_states[-1]
        for next_state, transition_prob in adjacency.get(current, []):
            if not allow_revisit and next_state in path_states:
                continue
            path_states.append(next_state)
            probs.append(transition_prob)
            dfs(path_states, probs)
            probs.pop()
            path_states.pop()

    for start in adjacency.keys():
        dfs([start], [])

    results.sort(
        key=lambda r: (r.joint_probability, len(r.states), r.states),
        reverse=True,
    )
    return results


def format_probability_product(step_probs: Sequence[float]) -> str:
    if not step_probs:
        return "1.000000"
    return " * ".join(f"{p:.3f}" for p in step_probs)


def save_sequences_to_file(
    sequences: Sequence[SequenceResult],
    output_dir: Path,
    output_file_prefix: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"{output_file_prefix}.json"
    json_payload = [list(seq.states) for seq in sequences]
    json_path.write_text(
        json.dumps(json_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return json_path


def main() -> None:
    if MIN_SEQUENCE_LENGTH < 2:
        raise ValueError("MIN_SEQUENCE_LENGTH は 2 以上にしてください。")
    if MAX_SEQUENCE_LENGTH < MIN_SEQUENCE_LENGTH:
        raise ValueError("MAX_SEQUENCE_LENGTH は MIN_SEQUENCE_LENGTH 以上にしてください。")
    if not (0.0 <= THRESHOLD <= 1.0):
        raise ValueError("THRESHOLD は 0.0 以上 1.0 以下にしてください。")

    if not INPUT_JSON_DIR.exists() or not INPUT_JSON_DIR.is_dir():
        raise FileNotFoundError(f"入力ディレクトリが見つかりません: {INPUT_JSON_DIR}")

    # 4モードそれぞれに対応するJSONファイルパスを組み立てる
    mode_json_paths = build_mode_json_paths(INPUT_JSON_DIR, MODE_NAMES)
    # 必須のモード別JSONが欠けていないかを事前に検証する
    missing_paths = [str(path) for _, path in mode_json_paths if not path.is_file()]
    if missing_paths:
        missing_str = "\n".join(missing_paths)
        raise FileNotFoundError(
            "以下のモード別JSONが見つかりませんでした:\n" + missing_str
        )

    # 全モードで見つかった系列を states（状態列）単位でユニーク化して保持する
    unique_sequences: Dict[Tuple[str, ...], SequenceResult] = {}
    # ログ表示用に、モードごとの集計情報（nodes, edges, sequences）を蓄積する
    mode_summaries: List[Tuple[str, int, int, int]] = []

    # 各モードJSONを個別に解析して系列を抽出する
    for mode_name, json_path in mode_json_paths:
        # JSONからノード・エッジを読み込む
        nodes, edges = load_graph(json_path)
        # 閾値・除外状態に基づき、探索対象の遷移だけに絞る
        filtered_edges = filter_edges(edges, THRESHOLD, EXCLUDED_STATES)
        # DFS探索用に隣接リストへ変換する
        adjacency = build_adjacency(filtered_edges)
        # モード単体で系列を列挙する
        sequences = discover_sequences(
            adjacency=adjacency,
            min_length=MIN_SEQUENCE_LENGTH,
            max_length=MAX_SEQUENCE_LENGTH,
            allow_revisit=ALLOW_REVISIT,
        )

        # モード別の規模・抽出結果を後で表示するために保存
        mode_summaries.append((mode_name, len(nodes), len(edges), len(sequences)))

        # 同じ states の系列は1件に統合し、系列確率が高い方を採用する
        for seq in sequences:
            existing = unique_sequences.get(seq.states)
            if existing is None or seq.joint_probability > existing.joint_probability:
                unique_sequences[seq.states] = seq

    # モード統合後のユニーク系列を、確率降順（同率時は長さ・辞書順）で整列する
    sequences = sorted(
        unique_sequences.values(),
        key=lambda r: (r.joint_probability, len(r.states), r.states),
        reverse=True,
    )

    if TOP_N > 0:
        sequences = sequences[:TOP_N]

    print("=" * 80)
    print("ベースライン系列抽出（モード別JSON統合）")
    print("=" * 80)
    print(f"入力ディレクトリ          : {INPUT_JSON_DIR}")
    print(f"対象モード                : {MODE_NAMES}")
    print(f"対象モードJSON数          : {len(mode_json_paths)}")
    print(f"閾値                      : {THRESHOLD:.3f}")
    print(f"除外状態                  : {EXCLUDED_STATES if EXCLUDED_STATES else 'なし'}")
    print(f"系列長（ノード数）        : {MIN_SEQUENCE_LENGTH} 〜 {MAX_SEQUENCE_LENGTH}")
    print(f"ユニーク系列数            : {len(sequences)}")
    print("=" * 80)

    for mode_name, node_count, edge_count, sequence_count in mode_summaries:
        print(
            f"  - {mode_name:<12} nodes={node_count:<4} edges={edge_count:<4} "
            f"sequences={sequence_count}"
        )

    if not sequences:
        print("現在の設定では系列が見つかりませんでした。")
        return

    for i, seq in enumerate(sequences, start=1):
        state_path = " -> ".join(seq.states)
        prob_formula = format_probability_product(seq.step_probabilities)
        step_probs = ", ".join(f"{p:.3f}" for p in seq.step_probabilities)

        # print(f"[{i:03d}] {state_path}")
        # print(f"      各遷移確率         : [{step_probs}]")
        # print(f"      積（系列全体確率） : {prob_formula} = {seq.joint_probability:.6f}")

    output_path = save_sequences_to_file(
        sequences=sequences,
        output_dir=OUTPUT_DIR,
        output_file_prefix=OUTPUT_FILE_PREFIX,
    )

    print(f"保存先（JSON）            : {output_path}")


if __name__ == "__main__":
    main()
