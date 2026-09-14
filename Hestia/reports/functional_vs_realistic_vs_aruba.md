# functional / realistic_calibrated / Aruba 集計比較

## 条件

- 比較期間: 7日
- 研究前処理: K=15、h=0、1秒Sample-and-Hold、5秒遅延OFF
- Arubaは生系列のコピーではなく、集計統計と正式成果物だけを比較に使用した。

## 主要指標

| 指標 | functional | realistic_calibrated | Aruba | realistic/functional |
|---|---:|---:|---:|---:|
| raw_full_events_per_day | 134.714286 | 301.285714 | - | 2.23647932 |
| events_per_day | 78.8571429 | 230.857143 | 6924.42857 | 2.92753623 |
| other_duration_ratio | 0.727254886 | 0.261185731 | 0.0205917078 | 0.35913919 |
| adl_internal_state_changes | 136 | 334 | 14795 | 2.45588235 |
| representative_state_count | 15 | 15 | 15 | 1 |
| observed_mapped_representative_states | 7 | 12 | 15 | 1.71428571 |
| state_transitions | 212 | 422 | 34169 | 1.99056604 |
| daily_cv | 0.175116608 | 0.154132612 | 0.21993273 | 0.880171295 |

## Arubaとの距離

| 指標 | functional | realistic_calibrated | 改善 |
|---|---:|---:|---:|
| hourly_js_bits | 0.312937 | 0.114702 | 0.198235 |
| room_rank_js_bits | 0.144642 | 0.0653658 | 0.0792757 |
| inter_event_gap_wasserstein_sec | 990.636 | 305.624 | 685.012 |
| adl_duration_wasserstein_min | 91.6903 | 62.3382 | 29.3521 |
| transition_probability_rank_l1 | 6.262 | 5.519 | 0.743 |

## 解釈

`realistic_calibrated`はゾーン移動と因果的なマイクロ行動により、functionalより状態変化と遷移を増やす。イベント数そのものへの一致は目的関数にしていない。Arubaには短時間の再発火が非常に多く、合成側は意味的な移動単位を維持するため、密度差は残る。

Other率は時間加重で計算した。Arubaの部屋真値はないため、合成の在室時間とArubaのセンサー発火割合を同一概念として扱っていない。詳細な時間帯・部屋・ADL内訳はCSVを参照する。
