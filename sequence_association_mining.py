"""
時系列データ向け アソシエーション分析 + シーケンスパターン抽出

- Apriori / FP-Growth による頻出アイテム集合・ルール抽出
- 時系列の順序を使った遷移ルール (A -> B) 抽出
- n-gram（連続パターン）抽出

使い方例:
python sequence_association_mining.py \
  --input data/aruba.csv \
  --timestamp-col timestamp \
  --item-col sensor_id \
  --value-col binary_value \
  --positive-value 1 \
  --window 30min \
  --min-support 0.05 \
  --min-confidence 0.3 \
  --top-k 30 \
  --output-dir state/association_output
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from dataclasses import dataclass
from typing import List, Set, Tuple, Optional

import pandas as pd


try:
    from mlxtend.preprocessing import TransactionEncoder
    from mlxtend.frequent_patterns import apriori, fpgrowth, association_rules
except ImportError as exc:
    raise ImportError(
        "mlxtend が必要です。`uv add mlxtend` または `pip install mlxtend` を実行してください。"
    ) from exc


# デフォルト実行設定（`uv run sequence_association_mining.py` 用）
DEFAULT_INPUT_PATH = "data/aruba.csv"
DEFAULT_TIMESTAMP_COL = "timestamp"
DEFAULT_ITEM_COL = "sensor_id"
DEFAULT_VALUE_COL = "value"
DEFAULT_POSITIVE_VALUE = "ON"
DEFAULT_WINDOW = "30min"
DEFAULT_MIN_SUPPORT = 0.05
DEFAULT_MIN_CONFIDENCE = 0.3
DEFAULT_NGRAM_SIZE = 3
DEFAULT_TOP_K = 30
DEFAULT_OUTPUT_DIR = "state/association_output"


@dataclass
class MiningConfig:
    min_support: float = 0.05
    min_confidence: float = 0.3
    top_k: int = 30
    ngram_size: int = 3


class TimeSeriesAssociationMiner:
    def __init__(self, config: MiningConfig):
        self.config = config

    def load_events(
        self,
        csv_path: str,
        timestamp_col: str,
        item_col: str,
        value_col: Optional[str] = None,
        positive_value: Optional[str] = None,
    ) -> pd.DataFrame:
        """CSV からイベントを読み込み、時系列順の標準形式（timestamp, item）に整形する。"""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"入力ファイルが見つかりません: {csv_path}")

        # 1) ヘッダあり汎用CSVとして読む
        # 2) 指定列が見つからない場合は、ヘッダなしイベントログ形式（3/4列）として自動判定する
        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            raise ValueError(f"CSV読み込みに失敗しました: {exc}") from exc

        use_event_log_fallback = (timestamp_col not in df.columns) or (item_col not in df.columns)

        if use_event_log_fallback:
            df_std = self._load_event_log_no_header(csv_path)
        else:
            cols = [timestamp_col, item_col]
            if value_col and value_col in df.columns:
                cols.append(value_col)

            df_std = df[cols].copy()
            rename_map = {
                timestamp_col: "timestamp",
                item_col: "item",
            }
            if value_col and value_col in df_std.columns:
                rename_map[value_col] = "value"
            df_std = df_std.rename(columns=rename_map)

            df_std["timestamp"] = pd.to_datetime(df_std["timestamp"], errors="coerce")

        df_std = df_std.dropna(subset=["timestamp", "item"]).copy()

        # value 列がある場合のみ、ON相当を抽出
        if "value" in df_std.columns:
            if positive_value is None:
                df_std = df_std[df_std["value"].astype(str).isin(["1", "ON", "True", "true"])].copy()
            else:
                df_std = df_std[df_std["value"].astype(str) == str(positive_value)].copy()

        df_std = df_std.sort_values("timestamp").reset_index(drop=True)
        return df_std[["timestamp", "item"]]

    def _load_event_log_no_header(self, csv_path: str) -> pd.DataFrame:
        """ヘッダなしイベントログ（3列/4列）を標準形式に変換する。"""
        df = pd.read_csv(csv_path, header=None)

        if len(df.columns) == 4:
            df.columns = ["date", "time", "sensor_id", "value"]
            timestamp = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str), format="mixed", errors="coerce")
            out = pd.DataFrame(
                {
                    "timestamp": timestamp,
                    "item": df["sensor_id"].astype(str),
                    "value": df["value"].astype(str),
                }
            )
            return out

        if len(df.columns) == 3:
            df.columns = ["timestamp", "sensor_id", "value"]
            df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", errors="coerce")
            out = pd.DataFrame(
                {
                    "timestamp": df["timestamp"],
                    "item": df["sensor_id"].astype(str),
                    "value": df["value"].astype(str),
                }
            )
            return out

        raise ValueError(
            "入力CSVの形式を判定できませんでした。"
            "ヘッダ付きで timestamp/item 列を指定するか、3列/4列のイベントログ形式を使用してください。"
        )

    def build_window_transactions(
        self,
        events: pd.DataFrame,
        timestamp_col: str,
        item_col: str,
        window: str = "30min",
    ) -> Tuple[List[Set[str]], pd.DataFrame]:
        """時系列イベントを時間窓ごとのトランザクション（集合）に変換する。"""
        work = events.copy()
        work["window_start"] = work[timestamp_col].dt.floor(window)

        grouped = (
            work.groupby("window_start")[item_col]
            .apply(lambda s: sorted(set(map(str, s.tolist()))))
            .reset_index(name="items")
        )

        grouped = grouped[grouped["items"].map(len) > 0].copy()
        transactions = [set(items) for items in grouped["items"]]
        return transactions, grouped

    def _mine_frequent_itemsets(self, transactions: List[Set[str]], method: str) -> pd.DataFrame:
        """Apriori または FP-Growth で頻出アイテム集合を抽出する。"""
        if len(transactions) == 0:
            return pd.DataFrame(columns=["support", "itemsets"])

        te = TransactionEncoder()
        matrix = te.fit(transactions).transform(transactions)
        basket = pd.DataFrame(matrix, columns=te.columns_)

        if method == "apriori":
            itemsets = apriori(basket, min_support=self.config.min_support, use_colnames=True)
        elif method == "fpgrowth":
            itemsets = fpgrowth(basket, min_support=self.config.min_support, use_colnames=True)
        else:
            raise ValueError("method は 'apriori' または 'fpgrowth' を指定してください。")

        if itemsets.empty:
            return itemsets

        itemsets["length"] = itemsets["itemsets"].apply(len)
        itemsets = itemsets.sort_values(["support", "length"], ascending=[False, False]).reset_index(drop=True)
        return itemsets

    def _mine_rules(self, itemsets: pd.DataFrame) -> pd.DataFrame:
        """頻出アイテム集合からアソシエーションルールを抽出する。"""
        if itemsets.empty:
            return pd.DataFrame(
                columns=[
                    "antecedents", "consequents", "support", "confidence", "lift",
                    "leverage", "conviction"
                ]
            )

        rules = association_rules(itemsets, metric="confidence", min_threshold=self.config.min_confidence)
        if rules.empty:
            return rules

        keep_cols = [
            "antecedents", "consequents", "support", "confidence", "lift", "leverage", "conviction"
        ]
        rules = rules[keep_cols].copy()

        rules["antecedents"] = rules["antecedents"].apply(lambda x: sorted(list(x)))
        rules["consequents"] = rules["consequents"].apply(lambda x: sorted(list(x)))

        rules = rules.sort_values(["confidence", "lift", "support"], ascending=[False, False, False]).reset_index(drop=True)
        return rules

    def mine_association(self, transactions: List[Set[str]]) -> dict:
        """Apriori と FP-Growth をまとめて実行する。"""
        apriori_itemsets = self._mine_frequent_itemsets(transactions, method="apriori")
        apriori_rules = self._mine_rules(apriori_itemsets)

        fp_itemsets = self._mine_frequent_itemsets(transactions, method="fpgrowth")
        fp_rules = self._mine_rules(fp_itemsets)

        return {
            "apriori_itemsets": apriori_itemsets,
            "apriori_rules": apriori_rules,
            "fpgrowth_itemsets": fp_itemsets,
            "fpgrowth_rules": fp_rules,
        }

    def mine_transition_rules(self, events: pd.DataFrame, item_col: str) -> pd.DataFrame:
        """連続イベントから遷移ルール A -> B を抽出する。"""
        sequence = events[item_col].astype(str).tolist()
        if len(sequence) < 2:
            return pd.DataFrame(columns=["from", "to", "support", "confidence", "count"])

        transition_count = Counter()
        from_count = Counter()

        for a, b in zip(sequence[:-1], sequence[1:]):
            transition_count[(a, b)] += 1
            from_count[a] += 1

        total_transitions = sum(transition_count.values())
        records = []
        for (a, b), cnt in transition_count.items():
            support = cnt / total_transitions
            confidence = cnt / from_count[a]
            records.append({
                "from": a,
                "to": b,
                "count": cnt,
                "support": support,
                "confidence": confidence,
            })

        rules = pd.DataFrame(records)
        rules = rules[rules["confidence"] >= self.config.min_confidence]
        rules = rules.sort_values(["confidence", "support", "count"], ascending=[False, False, False]).reset_index(drop=True)
        return rules

    def mine_ngrams(self, events: pd.DataFrame, item_col: str, n: Optional[int] = None) -> pd.DataFrame:
        """時系列アイテム列から n-gram パターンを抽出する。"""
        n = n or self.config.ngram_size
        seq = events[item_col].astype(str).tolist()

        if len(seq) < n:
            return pd.DataFrame(columns=["pattern", "count", "support"])

        grams = Counter(tuple(seq[i:i + n]) for i in range(len(seq) - n + 1))
        total = sum(grams.values())

        patterns = pd.DataFrame(
            [
                {
                    "pattern": " -> ".join(g),
                    "count": c,
                    "support": c / total,
                }
                for g, c in grams.items()
            ]
        ).sort_values(["count", "support"], ascending=[False, False]).reset_index(drop=True)

        return patterns


def save_results(results: dict, out_dir: str, top_k: int) -> None:
    os.makedirs(out_dir, exist_ok=True)

    for name, df in results.items():
        path = os.path.join(out_dir, f"{name}.csv")
        if df.empty:
            df.to_csv(path, index=False)
        else:
            df.head(top_k).to_csv(path, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="時系列アソシエーション分析 + シーケンスパターン抽出")

    parser.add_argument("--input", default=DEFAULT_INPUT_PATH, help="入力CSVファイル")
    parser.add_argument("--timestamp-col", default=DEFAULT_TIMESTAMP_COL, help="タイムスタンプ列名")
    parser.add_argument("--item-col", default=DEFAULT_ITEM_COL, help="イベント/アイテム列名")
    parser.add_argument("--value-col", default=DEFAULT_VALUE_COL, help="ON/OFF 等の値列名（任意）")
    parser.add_argument("--positive-value", default=DEFAULT_POSITIVE_VALUE, help="採用する値（例: 1, ON）")

    parser.add_argument("--window", default=DEFAULT_WINDOW, help="トランザクション化の時間窓（例: 15min, 1H）")
    parser.add_argument("--min-support", type=float, default=DEFAULT_MIN_SUPPORT, help="最小支持度")
    parser.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE, help="最小確信度")
    parser.add_argument("--ngram-size", type=int, default=DEFAULT_NGRAM_SIZE, help="n-gram の n")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="保存件数上限")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="出力ディレクトリ")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = MiningConfig(
        min_support=args.min_support,
        min_confidence=args.min_confidence,
        top_k=args.top_k,
        ngram_size=args.ngram_size,
    )

    miner = TimeSeriesAssociationMiner(config)

    events = miner.load_events(
        csv_path=args.input,
        timestamp_col=args.timestamp_col,
        item_col=args.item_col,
        value_col=args.value_col,
        positive_value=args.positive_value,
    )

    transactions, transaction_df = miner.build_window_transactions(
        events=events,
        timestamp_col="timestamp",
        item_col="item",
        window=args.window,
    )

    association_results = miner.mine_association(transactions)
    transition_rules = miner.mine_transition_rules(events, item_col="item")
    ngrams = miner.mine_ngrams(events, item_col="item")

    results = {
        "window_transactions": transaction_df,
        **association_results,
        "transition_rules": transition_rules,
        "ngram_patterns": ngrams,
    }

    save_results(results, args.output_dir, args.top_k)

    print("=" * 70)
    print("分析完了")
    print(f"入力イベント数: {len(events)}")
    print(f"トランザクション数: {len(transactions)}")
    print(f"出力先: {args.output_dir}")
    print("- apriori_itemsets.csv")
    print("- apriori_rules.csv")
    print("- fpgrowth_itemsets.csv")
    print("- fpgrowth_rules.csv")
    print("- transition_rules.csv")
    print("- ngram_patterns.csv")
    print("=" * 70)


if __name__ == "__main__":
    main()
