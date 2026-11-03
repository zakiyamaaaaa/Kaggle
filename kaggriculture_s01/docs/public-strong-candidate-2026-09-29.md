# Kaggriculture 公開強豪候補の再評価と提出（2026-09-29）

## 動機

同じOne More Wheat原版の旧提出はlive rating 2763.4、新提出は1511.9。スコアは相手分布と時点に依存するため、この差をコード差とみなさない。新提出のPublic replayでは同系統の僅差敗戦に加え、大差の敗戦も確認した。終了時のShedと作業員在庫は診断した敗戦で0だったため、終盤清算パッチを優先しなかった。

## 公開コードの取得と検証

公開Notebookを `kaggle kernels list` / `kaggle kernels pull` で取得し、Pythonコードを実行せずに埋め込みソースを抽出した。原本と抽出後のSHA-256を確認し、提出用の`agent()`入口を追加した。cha22の原本はApache-2.0のライセンスと出典をソース内に保持している。提出tarには`LICENSE.txt`と新しい`NOTICE.txt`も含む。

- 原本: `abhinav0370/cha22-agent`
- 原本 `main.py` SHA-256: `127ed3e62988c0474d386db6527ae8ca9de9bb1fe7004128557ddef67126c652`
- 提出 `main.py` SHA-256: `b5cf8719ad7afd37dbe15545f4fb927d3aedb97e657405050365a938f99f5590`
- 提出tar SHA-256: `79375df2b6a2db18a027033a8fd54020cc205a97f68a467927516bdacba76c87`

## ローカル評価

seed 998100–998115、両seat、6相手、候補ごと192試合。scoreは勝1・引分0.5・敗0。全試合完走、エラー0。

| 方策 | 平均score | OMW | Peak | Triad | cha22鏡 | herd-risk | shepherd |
|---|---:|---:|---:|---:|---:|---:|---:|
| OMW原版 | 0.5833 | 2-28-2 | 30-0-2 | 30-0-2 | 2-0-30 | 4-0-28 | 30-0-2 |
| cha22 | **0.8958** | 30-0-2 | 32-0-0 | 32-0-0 | 2-28-2 | 30-0-2 | 32-0-0 |
| herd-risk | 0.7396 | 28-0-4 | 32-0-0 | 32-0-0 | 2-0-30 | 2-28-2 | 32-0-0 |

`W-D-L`は勝-分-敗。cha22対原版のseed単位paired score差は **+0.3125**、bootstrap 95%区間 **[+0.2396, +0.4063]**。結果は [`public-panel-screen.json`](../outputs/final-sprint-2026-09-28/public-panel-screen.json)。これは公開方策を多く含むローカルpanelであり、Public ratingでの改善を保証しない。

## Kaggle提出

`submissions/cha22-public-20260929.tar.gz` を `kaggle competitions submit kaggriculture -f ... -m ...` で提出した。Submission ID **`56654513`**、2026-09-28 23:26:46 UTCにValidation episode `114935420` がCOMPLETEDとなり、submissionもCOMPLETE。Public試合前の表示ratingは600.0。Kaggle CLI 2.2.4で確認した提出枠は送信後2回。Public対戦が増えた後にlive ratingを再確認する。

## Hybrid2965の追加比較（提出判断前）

公開Notebook `haideptry/the-2965-master-hybrid-engine` から埋め込み`main.py`を静的に抽出した。SHA-256は `63dde9e4f73eb6c4c60cd453d085c17f4fec7110a6d52a2946b20e7ddb9f32bc`。公開Notebook `guruprasaathas111/kaggriculture-top-2-master-engine-v4` の`main.py`も同一bytes。`tetsutani/demand-preserving-turn-sale-timing` は空の注文列を扱う二条件のみ異なり、8-seed smokeではhybrid2965と同結果だった。

- 8 seed × 両seat × OMW/cha22/herd-risk: hybrid2965はcha22に16勝0敗、OMWに14勝2敗、herd-riskに12勝4敗。エラー0。
- 別の32 seed × 両seat × cha22/herd-risk/OMW/Peak/Triad: cha22をcontrolとした平均scoreは0.88125 → hybrid2965 0.93125、paired差 **+0.0500**、seed-bootstrap 95%区間 **[+0.00625, +0.08750]**、エラー0。
- 相手別のhybrid2965戦績はcha22 54勝10敗、herd-risk 60勝4敗、OMW 60勝4敗、Peak 62勝2敗、Triad 62勝2敗。cha22 controlはそれぞれ1勝62分1敗、58勝6敗、64勝0敗、64勝0敗、64勝0敗。強いcha22への改善と、OMW/Peak/Triadへの退行が同時にある。
- 結果: [`hybrid-smoke.json`](../outputs/final-sprint-2026-09-28/hybrid-smoke.json)、[`hybrid-screen-32.json`](../outputs/final-sprint-2026-09-28/hybrid-screen-32.json)。提出tarは`submissions/hybrid2965-public-20260929.tar.gz`として作成済み、SHA-256 `9eb58920f9d9c11d5fb967928398d9a3aeed4fe688ab17de2b2a79a520616564`。新規64-seed validationを完了し、cha22に対するpaired score差 **+0.065625**、95%区間 **[+0.0171875, +0.1125]**、全1,280試合でエラー0だった。結果は [`hybrid-validation-64.json`](../outputs/final-sprint-2026-09-28/hybrid-validation-64.json)。2026-09-28 23:42:03 UTCにKaggle CLIで提出し、IDは **`56654813`**、Validation episode `114941854` はCOMPLETEDとなり、submissionもCOMPLETE。Public試合前の初期ratingは600.0。最新2提出はhybrid2965とcha22。

2026-09-28 23:45 UTC付近のCLIスナップショットでは、cha22はPublic 3件・Validation 1件が全てCOMPLETED、live rating 872.0。hybrid2965はValidation 1件COMPLETED、Public 0件、初期rating 600.0。両者ともPrivate scoreは未表示。Public ratingでの優劣判定はまだできない。
