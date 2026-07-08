# 評価2: 提案手法の5回実行評価

## 評価の要約

提案手法である「センサログを代表状態系列に変換し、状態遷移ネットワークを構築してからLLMに入力する方法」を5回実行し、抽出結果と評価指標の安定性を確認する。LLMの非決定性を考慮し、論文・発表で使う主結果は複数runの集計として扱う。

## RQ

| RQ | 内容 |
|---|---|
| RQ2-1 | 提案手法のLLM出力は5回実行しても安定しているか。 |
| RQ2-2 | 遷移確率ベースライン・頻度ベースラインに対するPrecision / Recall / F1はどの程度か。 |
| RQ2-3 | 5回平均の結果を、提案手法の主結果として再現できるか。 |

## 評価指標

| 指標 | 定義・確認内容 |
|---|---|
| Precision | LLMが出した系列のうち、ベースライン系列と一致した割合。 |
| Recall | ベースライン系列のうち、LLMが抽出できた割合。 |
| F1 | PrecisionとRecallの調和平均。 |
| run間のばらつき | 5回の出力パターン数、Precision / Recall / F1の差を見る。 |
| 出力パターン数 | 各runでLLMが抽出した系列数を見る。 |

現在の比較では、状態系列の完全一致をTPとして扱う。

## 入力と出力

### 入力

| 入力 | 例 | 役割 |
|---|---|---|
| センサログ | `data/aruba.csv` | 代表状態・状態遷移ネットワークの元データ。 |
| 設定 | `configs/default.yaml` | `K`, ハミング距離、LLM run数など。 |
| プロンプト | `prompts/pattern_extraction_prompt.md` | 状態遷移ネットワークから系列パターンを抽出するLLMプロンプト。 |
| APIキー | `.env` | `GEMINI_API_KEY` を設定する。 |
| 状態遷移JSON | `picture/aruba_15_1_154days/state_transition_{mode}.json` | LLMへの入力。 |
| ベースライン | `output/aruba_15_1_154days/prob_threshold_sequences_15_1_154days.json`, `state_sequence_counts_15_1_154days.json` | 評価指標の比較対象。 |

### 出力

| 出力 | 内容 |
|---|---|
| `output/aruba_15_1_154days/llm_sequences_modes_15_1_154days_{run}.json` | 各runのLLM抽出結果。 |
| `output/aruba_15_1_154days/llm_mode_records_run{run}/state_transition_{mode}.json` | 時間帯ごとの成功結果。再開用チェックポイントでもある。 |
| `output/aruba_15_1_154days/llm_mode_records_run{run}/state_transition_{mode}_raw.txt` | LLMの生応答。 |
| `output/aruba_15_1_154days/llm_mode_records_run{run}/state_transition_{mode}_metrics.json` | backend、token使用量、処理時間など。 |
| `output/aruba_15_1_154days/failed_responses/*.txt` | パースできなかったLLM応答。 |
| `output/aruba_15_1_154days/evaluation_report_15_1_154days_{run}.txt` | 各runの評価レポート。 |
| `output/aruba_15_1_154days/llm_eval_runs_15_1_154days.xlsx` | 5回分の評価指標集計。 |

## 結果の読み方

| 順序 | ファイル | 読み方 |
|---|---|---|
| 1 | `output/aruba_15_1_154days/llm_eval_runs_15_1_154days.xlsx` | summaryとして、5回平均、標準偏差、run間のばらつきを見る。 |
| 2 | `llm_sequences_modes_15_1_154days_{run}.json`, `evaluation_report_15_1_154days_{run}.txt` | detailsとして、各runの抽出系列、パターン数、Precision / Recall / F1を確認する。 |
| 3 | `configs/default.yaml`, `docs/paper_parameters.md`, `llm_mode_records_run{run}/*_metrics.json` | 再現条件として、モデル名、temperature、run数、token使用量を確認する。 |

## 実行手順

### 1. 🟨 **条件付き** 状態遷移ネットワークを作成する

`picture/aruba_15_1_154days/state_transition_{mode}.json` がなければ実行する。既に同じ条件のネットワークがある場合はスキップしてよい。

```bash
uv run python scripts/run_build_network.py
```

### 2. 🟨 **条件付き** ベースラインを作成する

`prob_threshold_sequences_*.json` や `state_sequence_counts_*.json` がなければ実行する。評価2でLLM出力だけを確認する場合は省略できる。

```bash
uv run python scripts/run_baselines.py
```

### 3. 🟥 **必須** 提案手法のLLM抽出と評価を5回実行する

評価2の主結果を作るために実行する。`llm_mode_records_run{run}/*.json` が存在する時間帯モードは、スクリプト側でスキップされる。

```bash
uv run python scripts/run_llm_eval_batch.py
```

### 4. 🟩 **スキップ可** 全工程をまとめて実行する

個別Stepではなく、ネットワーク構築から評価までまとめて再実行したい場合だけ使う。

```bash
uv run python scripts/run_all.py
```

## 比較対象

| 比較対象 | 内容 |
|---|---|
| 遷移確率ベースライン | 遷移確率 `0.2` 以上のエッジをたどる系列。 |
| 頻度ベースライン | 代表状態系列上で頻出する状態系列。 |
| 提案手法 | 時間帯別状態遷移ネットワークJSONをLLMへ渡して抽出した系列。 |

## 処理手順の内部仕様

1. `scripts/run_build_network.py` が状態遷移ネットワークJSONを生成する。
2. `scripts/run_baselines.py` が遷移確率・頻度ベースラインを生成する。
3. `scripts/run_llm_eval_batch.py` が `src/behavior_pattern_mining/llm/pattern_extractor.py` を複数回呼び出す。
4. LLM抽出は時間帯モードごとに保存され、成功済みモードは再実行時にスキップされる。
5. `src/behavior_pattern_mining/evaluation/compare_patterns.py` がLLM系列とベースライン系列を比較する。
6. 5回分の評価結果をExcelへ集計する。

## パラメータ

| パラメータ | 値 |
|---|---:|
| データセット | `data/aruba.csv` |
| 代表状態数 `K` | `15` |
| ハミング距離閾値 | `1` |
| 分析期間 | `154`日 |
| LLMモデル | `gemini-2.5-pro` |
| Temperature | `0.2` |
| 実行回数 | `5` |
| 入力形式 | 時間帯別状態遷移ネットワークJSON |
| 系列長 | `2` から `4` |

詳細は `docs/paper_parameters.md` を参照する。

## 注意点

- LLM APIを使うため、ネットワーク接続と `.env` の `GEMINI_API_KEY` が必要。
- 同じrun番号のJSONがある場合、スクリプト側でスキップされることがある。完全に作り直す場合は既存出力を退避してから実行する。
- 評価2の出力は、評価3、評価4、評価5の入力にも使える。
