# HESTIA生成データと実Arubaデータの品質比較

## 比較条件

- 実データ: `/Users/wataru/Desktop/master-research/data/aruba.csv` の先頭7暦日 (2010-11-04〜2010-11-10)
- 生成データ: `/private/tmp/hestia_audit_runs/seven_days/casas_motion_door.txt` (7日、固定seed)
- 共通ネットワーク条件: 1秒Sample-and-Hold、5秒遅延OFF、K=15、h=0
- LLM由来の品質指標ではなく、イベント・ADL・代表状態遷移の記述統計である。

## 主要イベント統計

| 指標 | 実Aruba | 生成 | 生成/実 | 単位 |
|---|---:|---:|---:|---|
| events | 48471 | 552 | 0.0113883 | count |
| events_per_day | 6924.43 | 78.8571 | 0.0113883 | events/day |
| daily_cv | 0.219933 | 0.175117 | 0.796228 | ratio |
| sensor_count | 10 | 16 | 1.6 | count |
| sensor_concentration | 0.250727 | 0.219203 | 0.874268 | ratio |
| sensor_cv | 0.742252 | 0.819257 | 1.10374 | ratio |
| active_ratio | 0.500031 | 0.487319 | 0.974577 | ratio |
| duplicate_state_ratio | 0.230385 | 0 | 0 | ratio |
| activation_duration_median_sec | 2.89257 | 3 | 1.03714 | seconds |
| activation_duration_p95_sec | 8.78161 | 18097 | 2060.78 | seconds |
| inter_event_gap_median_sec | 1.4756 | 0 | 0 | seconds |
| inter_event_gap_p95_sec | 15.7192 | 5934.25 | 377.516 | seconds |

## 遷移ネットワーク統計

| 指標 | 実Aruba | 生成 | 生成/実 |
|---|---:|---:|---:|
| nodes | 16 | 16 | 1 |
| edges | 125 | 38 | 0.304 |
| density | 0.520833 | 0.158333 | 0.304 |
| self_edge_ratio | 0 | 0 | - |
| reversible_edge_ratio | 0.928 | 1 | 1.07759 |
| mean_outgoing_entropy_bits | 1.69618 | 0.875817 | 0.516347 |
| other_duration_ratio | 0.0206425 | 0.727255 | 35.2309 |

## 生成データの時間加重在室分布

- `bathroom`: 3.124%
- `bedroom`: 29.928%
- `dining_room`: 2.072%
- `entrance`: 0.700%
- `hallway`: 0.000%
- `kitchen`: 2.764%
- `living_room`: 40.511%
- `outside`: 20.901%

## 結論

生成ログは78.9イベント/日で、実Arubaの6924.4イベント/日より大幅に疎である。これは、生成側が完全な在室変化と扉通過を低チャタリングで記録する一方、実データには高頻度なモーション再発火が含まれるためである。
時間帯分布のJensen–Shannon divergenceは0.313 bitsで、日課の時刻が固定的な生成データと実生活の分散には明瞭な差がある。
代表状態の`Other/その他`滞在比率は実2.06%、生成72.73%である。h=0では、生成側の長時間状態の多くが上位Kに入らない構成差が品質上の主要な制約になる。
よって、生成ログはパイプライン機能・再現性・既知シナリオの教師データ検証には利用できるが、実Arubaの点過程を忠実に代替するデータとは扱えない。

## 解釈上の制約

- 実データの在室真値はないため、生成側の在室分布と実側のセンサー発火分布を同一概念として直接比較していない。
- 7日窓は曜日を一巡するが季節差を表さず、推測統計の独立標本としては短い。
- 実ArubaはセンサーIDを部屋カテゴリへ集約済み、生成側は個別センサーIDである。
- 詳細な時間帯・ADL別数値は同時生成したCSVを参照する。
