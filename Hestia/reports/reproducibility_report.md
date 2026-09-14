# 再現性・長期実行監査

## 隔離環境

`uv.lock`を使い、既存`.venv`とは別の一時仮想環境を作成した。

- Python: CPython 3.12.2
- `uv sync --frozen`: 成功、25 packages
- scenario: `aruba_single_resident.yaml`
- days: 7
- seed: 42

次の環境差を与えて独立実行した。

| run | PYTHONHASHSEED | TZ | LC_ALL | directory SHA-256 |
|---|---:|---|---|---|
| A | 0 | UTC | C | `5e11e89d2ec0361d82715fa0d51a7714da00d4b17e707bd238fae0a6d2a1f6eb` |
| B | 123 | Asia/Tokyo | ja_JP.UTF-8 | `5e11e89d2ec0361d82715fa0d51a7714da00d4b17e707bd238fae0a6d2a1f6eb` |

`diff -qr`は差分0件だった。シナリオ開始時刻が明示offsetを持ち、コレクションのスケジュール・シリアライズがID順であるため、プロセスTZ、locale、hash seedの差は出力へ入らない。

## 長期実行

測定環境はmacOS、`/usr/bin/time -l`。時間とRSSは単一観測でありベンチマーク保証ではない。

| scenario | days | seed | events | states | 実時間 | max RSS | 出力合計 | 最終イベント日 | hash |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| single | 30 | 42 | 3,837 | 3,820 | 1.01 s | 60.0 MiB | 5.07 MB | 2025-02-04 | `99b36c03638f23a454ac03e4c813fef96836473832a0c4fda88893472cc5330b` |
| single | 220 | 42 | 28,143 | 28,011 | 4.23 s | 125.8 MiB | 37.26 MB | 2025-08-13 | `61b369e5d19f4761d653380ffeb8194a2000aab66df6a5b915957afccebabf2d` |
| two residents | 30 | 123 | 3,630 | 3,599 | 0.88 s | 59.2 MiB | 4.70 MB | 2025-02-04 | `6b3b0704b559713750bc9c9a6efab315b1a80c8b0284dcb8d1315c0dabe8c3a1` |

30日と220日の単身runはそれぞれ同じseedで独立再実行し、上表の全出力ディレクトリhashが一致した。全runで生成後意味論検証が通り、最終暦日まで到達し、未終了活動・利用・開扉・移動中住人はなかった。

## 規模の内訳

220日単身runの主なファイルサイズ:

- `events.csv`: 9.26 MB
- `events_simple.csv`: 7.30 MB
- `state_vectors.csv`: 16.99 MB
- `casas_motion_door.txt`: 1.00 MB
- 合計: 37.26 MB

保持する全イベントと横持ち状態列に比例してメモリ・出力が増える。今回の220日規模では完走したが、年単位・多人数・多数デバイスではストリーミング出力が将来の改善候補である。

## 再現手順

```bash
UV_PROJECT_ENVIRONMENT=<isolated-venv> uv sync --frozen --project .
PYTHONHASHSEED=0 TZ=UTC LC_ALL=C \
  <isolated-venv>/bin/smart-home-sim simulate \
  examples/aruba_single_resident.yaml --days 7 --seed 42 --output <run-a>
PYTHONHASHSEED=123 TZ=Asia/Tokyo LC_ALL=ja_JP.UTF-8 \
  <isolated-venv>/bin/smart-home-sim simulate \
  examples/aruba_single_resident.yaml --days 7 --seed 42 --output <run-b>
diff -qr <run-a> <run-b>
```
