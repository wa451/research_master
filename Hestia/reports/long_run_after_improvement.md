# 改善後長期実行検証

| 実行 | 日数 | events | states | 秒 | 最大RSS | 出力 | 同seed一致 |
|---|---:|---:|---:|---:|---:|---:|---|
| functional_single_7d | 7 | 943 | 939 | 0.510 | 51904512 | 1245088 | True |
| realistic_single_7d | 7 | 2109 | 2100 | 0.780 | 59424768 | 3629146 | True |
| realistic_single_30d | 30 | 9185 | 9149 | 1.900 | 96649216 | 15849366 | True |
| realistic_single_220d | 220 | 64927 | 64662 | 11.150 | 313475072 | 112143299 | True |
| realistic_two_30d | 30 | 12446 | 12396 | 2.480 | 108986368 | 21904833 | True |
| stress_single_7d | 7 | 3143 | 3127 | 0.940 | 65847296 | 5462471 | True |
| stress_two_noise_7d | 7 | 2928 | 2835 | 1.260 | 72892416 | 11185270 | True |

`stress_two_noise_7d`の`events`は真値、`states`は観測ログから再構成した値である。観測イベントは
2,846件だった。

## 完全ディレクトリハッシュ

| 実行 | SHA-256 |
|---|---|
| functional_single_7d | `5e11e89d2ec0361d82715fa0d51a7714da00d4b17e707bd238fae0a6d2a1f6eb` |
| realistic_single_7d | `84de17a7142a92a0216fba661564a42a93e067e84c807e09e831fe5eec697214` |
| realistic_single_30d | `af4dea07928d0ad66a05ed8396d40ad5dc192c1ab44ee249dcd9ad0a96528fdc` |
| realistic_single_220d | `49beb4e3f37f6e13a0ae3152628dd489857ffb8c50da68b53237bb757c1694fc` |
| realistic_two_30d | `8127ab165590f97bf7f36f0865b1870976eb2d1a4a0255517737d4d560f5b396` |
| stress_single_7d | `29209317d76db4a6da5090180ccadb8b481881d269fca8e6505f45741acea4c0` |
| stress_two_noise_7d | `8a656cf922a89df1dbe854c492dc9d6ca99744a0ab3ed72f3e738b85d5acf8de` |

各行は同じseedで独立に2回生成し、ファイル名と全バイトを含むディレクトリハッシュが一致した。
realistic_single_7dをseed 43で実行したハッシュは
`1d51cc5fbd5bb55bdd975c74557041ff0d26d2d1910e043b7233cefc8a27ac8e`で、seed 42と異なった。

## 結論

- 全意味検証成功: `True`
- 全出力非空: `True`
- 同seed完全ディレクトリハッシュ一致: `True`
- realistic 7日で別seedハッシュ変化: `True`
- 最大の220日実行は11.15秒、最大RSS 313,475,072 bytes、出力112,143,299 bytesで完走した。
- 最大RSSと出力サイズは各行の実測値。生成物は`/private/tmp`に置き、Git管理対象にしていない。
