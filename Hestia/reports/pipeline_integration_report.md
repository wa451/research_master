# master-researchパイプライン統合検証

## 結論

新しい`motion-door` CASASプリセットは、`master-research`の実CLIに変更なしで入力できる。1日・7日の双方で、変換、状態ベクトル化、平滑化、代表状態、写像、遷移ネットワーク、時間帯分割、ADL区間、状態系列まで完走した。7日データでは診断用の非LLMパターン評価も完走した。外部LLM APIは呼び出していない。

## 条件

- Hestia scenario: `examples/aruba_single_resident.yaml`
- days: 1 / 7
- seed: 42
- CASAS preset: `motion-door`、ADL境界あり
- 研究側: K=15、h=0、1秒Sample-and-Hold、5秒遅延OFF
- 時間帯: Morning / Daytime / Night / Midnight

## 実行段階と結果

| 段階 | 1日 | 7日 |
|---|---:|---:|
| Hestia raw events | 153 | 943 |
| CASASセンサーイベント（研究変換後CSV） | 87 | 551 |
| 代表状態テーブル | 15状態+Other | 15状態+Other |
| 圧縮状態区間 | 29 | 213 |
| ADL真値区間 | 11 | 76 |
| ADL共通カテゴリ | 8 | 8 |
| 全期間遷移JSON | 成功 | 成功 |
| 有効な時間帯JSON | Morning/Daytime | 4時間帯すべて |
| API入力メッセージ構築 | 未実行 | 4時間帯で成功 |
| 外部API | 未呼出 | 未呼出 |

1日データでNight/Midnightの遷移JSONがないのは、そのseedの当該窓に有効な遷移が不足するためで、パイプライン失敗ではない。タイムライン出力は生成される。

## 研究CLIの実行契約

ネットワーク作成には次の実CLIを使用した。

```bash
python scripts/run_build_network_from_labeled_casas.py \
  --labeled-casas <casas_motion_door.txt> \
  --sensor-map <casas_sensor_map.json> \
  --keep-converted-csv <converted.csv> \
  --days 7 --n-states 15 --hamming-threshold 0 --smoothing-window-sec 5
```

状態系列は`evaluate_adl_labels.py`の`--state-series-only`と`network-equivalent`前処理で再構築した。これにより、ネットワークとADL評価で1秒/5秒条件が一致することを確認した。

## 診断的ADL評価

LLM出力を捏造せず、状態系列から手作業で選んだ5つの診断パターンだけを使った。

- パターン: 5
- 検出出現: 47
- merge前予測: 47
- merge後予測: 31
- IoU 0.3 micro F1: 0.374
- IoU 0.5 micro F1: 0.318

これはAPI互換性と評価コード到達性のsmoke testであり、HESTIAや提案LLM手法の性能値ではない。パターン選択が訓練・評価で同じ7日を見ているため、論文結果として利用してはならない。

## 外部API直前の入力

研究側の`find_mode_json_files`、`mode_label_from_path`、`build_user_message`を実際に呼び、4時間帯のAPI入力文字列を構築した。

| mode JSON | 文字数 | SHA-256 |
|---|---:|---|
| Morning | 7,527 | `2c03d2d1196e2411c30efc8dd2b76c74b7e6d8dd0800402f8a826d23e6c022f0` |
| Daytime | 6,847 | `016b319972745ad2ee1183b67699a2b13b130627ae6eded87ecc31c889927688` |
| Night | 6,817 | `d080b248b9de8c17925745fb01475c8184c0f8d74838c456a63194de6ded012b` |
| Midnight | 4,070 | `699e79c51abfda5ab0cd9a2a6d0ca83e2345272fe763f25b27cc17ac54f65cfb` |

## 互換性上の注意

- 研究converterが受けるセンサー状態はON/OFF/OPEN/CLOSE/PRESENT/ABSENT。Hestia presetは前4種だけを出す。
- センサー行は4フィールド、ADL境界は`... LABEL begin/end`の6フィールドである。
- legacy `aruba.txt`は後方互換用で、研究ADL真値には使わない。
- 多人数の同名ADL重複は研究parserがresidentをキーにしないため、真値評価には単身データを使う。
- 実行成果物は再生成可能なため追跡せず、レポートだけを保存する。
