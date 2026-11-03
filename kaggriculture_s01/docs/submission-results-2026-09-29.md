# Kaggriculture 提出結果の履歴

- 確認時刻: **2026-09-28 23:09:30 UTC（2026-09-29 08:09:30 JST）**
- 確認方法: Kaggle CLI 2.2.4 の `kaggle competitions submissions kaggriculture --format json --page-size 5` と `kaggle competitions episodes <submission_id> --format json`
- 対象: 2026-09-28 11:59 UTCに提出した2件。以下は当時のスナップショットであり、現在の最新2件は末尾の追記を参照。

| 提出物 | Submission ID | 提出時刻 UTC | 状態 | Public rating | Public episodes | Validation episodes | Episode状態 |
|---|---:|---|---|---:|---:|---:|---|
| `one-more-wheat-v1.tar.gz` | `56639976` | 2026-09-28 11:59:21 | COMPLETE | 1511.9 | 79 | 1 | 全80件COMPLETED |
| `omw-observed-value-front-run-v2.tar.gz` | `56639982` | 2026-09-28 11:59:36 | COMPLETE | 1493.7 | 76 | 1 | 全77件COMPLETED |

両提出ともエラー状態のepisodeは0。この確認時点ではこの2件が最新だった。Public ratingは継続対戦で変動し、両者の試合数と対戦相手も同一ではないため、18.2点の差を固定評価の方策差として扱わない。Private scoreは現時点で表示されていない。

提出前に照合したローカルアーカイブSHA-256は、原版が `4fd9470dbaff31a4fdc5f6c29fb2c9878f05772e6e4b7eb3029a7a0d033fcec0`、観測価値版が `630e368cc5a9602f6666634f3e2c854bd3d69fa76984528cb9a301a6e9b1b874`。CLIの提出履歴はサーバー側アーカイブのSHA-256を返さない。

## 追記: 2026-09-28 23:45 UTC付近の最新2提出

公開強豪をローカルで比較し、cha22とhybrid2965を追加提出した。Kaggle側の操作は公式CLIのみ。詳細な対戦表、出典、アーカイブhashは [公開強豪候補の再評価](public-strong-candidate-2026-09-29.md) を参照。

| 提出物 | Submission ID | 状態 | Public rating | Public episodes | Validation episodes | Episode状態 |
|---|---:|---|---:|---:|---:|---|
| `cha22-public-20260929.tar.gz` | `56654513` | COMPLETE | 872.0 | 3 | 1 | 全4件COMPLETED |
| `hybrid2965-public-20260929.tar.gz` | `56654813` | COMPLETE | 600.0 | 0 | 1 | 1件COMPLETED |

現在の最新2提出はこの2件。hybrid2965の600.0はPublic対戦前の初期値であり、両者のPublic ratingを比較して採否を判断できる段階ではない。Private scoreは未表示。

## 追記: 2026-09-30 13:05 UTC（22:05 JST）の再確認

`kaggle competitions submissions kaggriculture --format json --page-size 5` と `kaggle competitions episodes <submission_id> --format json` で確認した時点のスナップショット。Public rating は対戦の進行に伴い変動する。

| 提出物 | Submission ID | 状態 | Public rating | Public完走 | Publicエラー | Validation完走 | Private score |
|---|---:|---|---:|---:|---:|---:|---|
| `hybrid2965-public-20260929.tar.gz` | `56654813` | COMPLETE | **1739.4** | 232 | 20 | 1 | 未表示 |
| `cha22-public-20260929.tar.gz` | `56654513` | COMPLETE | **1540.2** | 170 | 21 | 1 | 未表示 |

`kaggle competitions list --search kaggriculture --format json` が返すアカウント順位は **1423位 / 10204チーム**。上位200位の最下位スコアは2395.4で、現在のhybridとの差は656.0。公式のメダル境界や最終順位は、この情報だけでは確定できない。

エラーの発生は両提出とも2026-09-29 04:14–06:59 UTCに集中し、その後の取得分は完走している。hybridのエラー対戦 `115067988` のログをCLIで取得しようとしたところHTTP 400となり、原因は未特定。エラーをエージェントの不具合またはKaggle側の問題と断定しない。
