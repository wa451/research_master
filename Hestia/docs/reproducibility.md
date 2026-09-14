# 再現性

## 保証範囲

同じシナリオ内容、CLI日数、seed、このパッケージバージョン、依存関係ロックを使うと、生成ディレクトリ内の全ファイルはバイト単位で一致します。出力先パスはファイル内容に書かれないため、別ディレクトリ間でも比較できます。

保証の仕組みは次のとおりです。

- Pythonの`random.Random`は`RandomManager`だけが所有する
- 住人、部屋、デバイス、接続、出力列はIDで明示ソートする
- SimPyプロセスは住人ID順で登録する
- 同時刻イベントは単調増加する内部連番で固定する
- 複合値と在室情報はJSONキーをソートする
- 共有デバイスの同優先度は住人ID辞書順で決める
- `run_id`はシナリオID、日数、seedだけから作る
- 分布、重み付きテンプレート、任意step、センサー不完全性も`RandomManager`だけを使う
- ゾーン・故障profile・テンプレートなど確率選択対象はIDで安定順序化する

## ハッシュ確認

`SimulationResult.content_hash`は出力ファイル名と内容をファイル名順にSHA-256へ入力した値です。手動では次のようにイベントCSVを比較できます。

```bash
shasum -a 256 outputs/aruba_seed42/events.csv
shasum -a 256 outputs/aruba_seed42_repeat/events.csv
cmp outputs/aruba_seed42/events.csv outputs/aruba_seed42_repeat/events.csv
```

完全ディレクトリ比較は、ファイル名順に各ファイルのハッシュを取って比較してください。テスト`test_same_seed_hash_matches_and_different_seed_changes`は同一seed一致と異なるseed相違を自動検証します。

## 乱数消費順

活動時間の抽選は各住人の活動開始時、テンプレート・任意step・反復・副次活動は実行順、
観測不完全性は真値シミュレーション完了後の時刻・内部連番順に行います。設定へ確率項目を追加すると
以後の乱数消費順は変わります。

従来の文字列routine、ゾーンなし、旧副次活動だけのシナリオは追加抽選を行わない専用分岐を
通ります。`examples/aruba_single_resident.yaml`の7日seed 42は改善前後とも完全ディレクトリ
SHA-256が`5e11e89d2ec0361d82715fa0d51a7714da00d4b17e707bd238fae0a6d2a1f6eb`
で一致しました。

改善後の全7/30/220日行列も同seed二重実行で完全一致し、realistic 7日seed 42と43は異なる
ハッシュでした。実測値は[長期実行レポート](../reports/long_run_after_improvement.md)にあります。

## 依存関係

`uv.lock`を保存し、`uv sync --frozen`を利用すると依存関係解決も固定できます。Pythonや依存ライブラリのメジャーバージョンを変更する場合は、同一seedの期待ハッシュを再検証してください。

既存の`PYTHONHASHSEED`、TZ、locale隔離監査は
[再現性レポート](../reports/reproducibility_report.md)、改善後の7/30/220日は
[長期実行レポート](../reports/long_run_after_improvement.md)に記録しています。
