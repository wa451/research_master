# 校正方法

## 原則

校正はArubaの生イベント列や個別生活系列をコピーせず、既存研究リポジトリが生成した集計統計と
正式成果物だけを参照します。最適化の優先順は、意味的妥当性、ADL内状態変化、Other率、
時間帯・部屋・ADL分布、日変動、イベント密度、統計距離です。イベント数だけへの適合は行いません。

正式な研究前処理条件は全試行で固定しました。

```text
代表状態数 K = 15
Hamming threshold h = 0
Sample-and-Hold = 1秒
遅延OFF = 5秒
期間 = 7日
seed = 42
```

## 自動反復

`scripts/calibrate_realistic.py`は最大3試行に制限し、各試行で次を実行します。

1. 基準YAMLを一時ディレクトリへ展開
2. マイクロ行動の任意ステップ確率と副次活動確率を設定値として調整
3. 7日シミュレーションと意味検証
4. `scripts/run_research_pipeline.py`でCASAS変換、状態系列、代表状態、ネットワーク、ADL評価を実行
5. 指標と警告を収集し、基準・Aruba集計と比較
6. 有限候補から総合スコア最大の設定を選択

コードを試行ごとに書き換えず、設定値だけを変更します。全試行の設定、seed、件数、Other率、
遷移、ADL内変化、警告、スコアは`reports/calibration_runs.csv`に保存しました。

## 実行した3試行

| 試行 | 設定 | raw events/日 | state-series Other | 状態遷移 | ADL内状態変化 | score |
|---:|---|---:|---:|---:|---:|---:|
| 1 | sparse candidate | 236.71 | 10.954% | 365 | 242 | 518.107 |
| 2 | balanced candidate | 249.00 | 15.667% | 361 | 237 | 461.976 |
| 3 | final | 301.29 | 16.589% | 422 | 334 | 610.756 |

試行3は複雑性の総合スコアが最大で、意味検証と研究パイプラインを警告なしで通過したため採用
しました。スコアは研究精度ではなく、状態変化と遷移を正に、Aruba集計Other率との差を負に扱う
校正用の診断値です。

## 3者比較

`scripts/analyze_realism.py`はfunctional、realistic_calibrated、Arubaについて、件数、センサー、
部屋、時間帯、ADL、継続時間、再反応間隔、遷移、状態占有、Other、日・曜日変動を集計します。
概念が対応する範囲では、次の距離も算出します。

- 時間帯分布と部屋発火順位のJensen–Shannon divergence
- イベント間隔とADL継続時間のWasserstein distance
- 日別件数の変動係数
- 遷移確率順位のL1距離

実測結果は`reports/functional_vs_realistic_vs_aruba.csv`と同名Markdownに保存しています。
formal network JSONとADL evaluatorの再構築state-seriesではOther率の集計境界が異なるため、
両方を記録し、改善前72.7%との比較には同じnetwork JSON定義を使います。

## 再実行

```bash
uv run python scripts/calibrate_realistic.py --help
uv run python scripts/run_research_pipeline.py --help
uv run python scripts/analyze_realism.py --help
```

Aruba入力は`master-research`側を読み取り専用で参照し、生成物は指定した作業ディレクトリへ出します。
外部LLMは使いません。反復校正の詳細と最終値は`reports/calibration_history.md`を参照してください。
