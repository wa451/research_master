# 論文掲載用パラメータ一覧

この文書は、論文・発表で参照する主要条件をまとめる。評価4〜8に固有の閾値・分母・splitは各評価文書を正本とし、ここでは共通条件を繰り返さない。

## 1. 論文採用条件と共通既定値

| 項目 | 論文採用条件 | `configs/default.yaml` | 注意 |
|---|---:|---:|---|
| データセット | `aruba` | `aruba` | 通常ログは先頭154日 |
| 代表状態数 K | `15` | `15` | 圧縮後の頻度上位K状態 |
| ハミング距離閾値 h | `0` | `1` | 採用条件は完全一致のみ。二重標準は [KI-01](known_issues.md) |
| サンプリング間隔 | `1s` | `1s` | Sample-and-Hold |
| 遅延OFF窓幅 | `5`秒 | `5`秒 | センサーOFFを遅延させる平滑化 |
| 分析期間 | `154`日 | `154`日 | 評価6などはLLM入力14日を別途使用 |

論文条件を示す成果物には `{K}_{h}_{days}days` のsuffixを使う。`h=0` と `h=1` の成果物を同じ評価へ混在させない。

## 2. 状態遷移ネットワーク

| パラメータ | 値 |
|---|---:|
| 可視化する最小遷移確率 | `0.1` |
| 連続自己状態 | 圧縮して除外 |
| 遷移確率の分母 | 同じfrom状態から出る遷移回数 |

時間帯は次の4区分である。

| mode | 時刻範囲 |
|---|---|
| Morning | 06:00–10:00 |
| Daytime | 10:00–18:00 |
| Night | 18:00–24:00 |
| Midnight | 00:00–06:00 |

全期間と4時間帯のnetwork JSONを出力する。遷移図は時間帯ごとのPNG/EPS、timelineは時間帯ごとのPNGだけを出力し、全期間図は生成しない。

## 3. 通常baseline

### 3.1 遷移確率baseline

| パラメータ | 値 |
|---|---:|
| 遷移確率閾値 | `0.2` |
| 系列長 | `2`〜`4` |
| 除外状態 | `その他` |
| 同一状態の再訪 | 不許可 |
| 出力上限 | `0`（上限なし） |

閾値0.2はfrom状態内の相対遷移確率に対するアルゴリズム条件であり、複数日の反復を直接保証しない。過去の根拠表現は [KI-13](known_issues.md) として判断保留である。

### 3.2 頻度baseline

| パラメータ | 値 |
|---|---:|
| 系列長 | `2`〜`4` |
| 出力上限 | 上位`50`件 |
| 連続同一状態 | 圧縮 |

通常baselineは遷移確率と頻度の2種である。評価5のFP-Growth系baselineは評価5内部の比較手法であり、通常pipelineへ含めない。

## 4. LLM抽出

| パラメータ | 値 |
|---|---|
| provider | Google Gemini |
| model | `gemini-2.5-pro` |
| temperature | `0.2` |
| 入力 | 4時間帯の状態遷移network JSON |
| 出力系列長 | `2`〜`4` |
| 通常run数 | `1` |
| batch run数 | `5` |
| 最大retry | runあたり`3` |

提案手法は `prompts/pattern_extraction_prompt.md` を実行時に読み、JSON要素として `パターン名`, `ADL系列ラベル`, `解釈の根拠`, `遷移のパターン` を扱う。同じ遷移系列は統合し、時間帯固有の解釈を `time_band_interpretations` に保持する。prompt、model、temperature、API呼び出し条件は研究条件であり、別作業のついでに変更しない。

5 runは安定性確認のための設定だが、現在のbatch処理ではrun 1のcheckpointを再利用し得る。独立5試行として扱えるかは [KI-02](known_issues.md) を参照する。

## 5. 評価1〜3の共通比較条件

| 項目 | 現在の条件 |
|---|---|
| scope | 時間帯mode結果 |
| 比較対象 | 提案手法 vs 遷移確率baseline、提案手法 vs 頻度baseline |
| 一致 | 完全一致。両方向の包含一致は無効 |
| 指標 | Precision、Recall、F1 |

- Precision = TP / (TP + FP)
- Recall = TP / (TP + FN)
- F1 = 2 × Precision × Recall / (Precision + Recall)

評価2のExcelはrun別値と平均を出すが標準偏差を出さない。評価3の写像・条件伝播・Excel集計にも未解決差があるため、[KI-03](known_issues.md)、[KI-04](known_issues.md)、[KI-05](known_issues.md) を参照する。

## 6. 現行の主要成果物名

| 成果物 | パスパターン |
|---|---|
| 代表状態表 | `state/aruba_{K}_{h}_{days}days.txt` |
| 全期間network | `picture/aruba_{K}_{h}_{days}days/state_transition_all.json` |
| 時間帯network | `picture/aruba_{K}_{h}_{days}days/state_transition_{mode}.json` |
| 遷移図 | `picture/aruba_{K}_{h}_{days}days/state_transition_{mode}.{png,eps}` |
| timeline | `picture/aruba_{K}_{h}_{days}days/timeline_{mode}.png` |
| 遷移確率baseline | `output/aruba_{K}_{h}_{days}days/prob_threshold_sequences_{K}_{h}_{days}days.json` |
| 頻度baseline | `output/aruba_{K}_{h}_{days}days/state_sequence_counts_{K}_{h}_{days}days.json` |
| 提案手法 | `output/aruba_{K}_{h}_{days}days/llm_sequences_modes_{K}_{h}_{days}days_{run}.json` |
| run別比較レポート | `output/aruba_{K}_{h}_{days}days/evaluation_report_{K}_{h}_{days}days_{run}.txt` |
| batch Excel | `output/aruba_{K}_{h}_{days}days/llm_eval_runs_{K}_{h}_{days}days.xlsx` |

Excelのsheet名、列名、後段評価のCSV/JSONは実装と各評価文書を参照し、過去文書の表記を出力契約として推測しない。

## 7. 採用条件の位置付け

- K=15は、30日入力の候補条件を比較し、上位条件を5 runで評価した結果とnetworkの簡潔さを踏まえた採用値である。K=20との差は小さく、統計的に唯一の最適値とは位置付けない。詳細は [evaluation_7_parameter_sensitivity_adl_interpretation.md](evaluation_7_parameter_sensitivity_adl_interpretation.md) を参照する。
- 系列長2〜4は、最小の遷移から短い行動シナリオまでを扱い、長すぎる系列の解釈困難を避ける条件である。
- temperature 0.2は、パターン列挙で出力のばらつきを抑えるための設定である。

評価4〜8の正式条件、指標、分母、出力は次の個別文書に置く。

- [評価4](evaluation_4_labeled_casas_adl.md)
- [評価5](evaluation_5_adl_correspondence.md)
- [評価6](evaluation_6_adl_interpretation_set.md)
- [評価7](evaluation_7_parameter_sensitivity_adl_interpretation.md)
- [評価8](evaluation_8_frequency_stratified_adl_consistency.md)
