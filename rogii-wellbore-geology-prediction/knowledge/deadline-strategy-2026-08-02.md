# ROGII 締切前実験戦略 — 2026-08-02

## 結論

残り期間は、7.474からローカル微修正を積み重ねる方針を停止する。最優先は、ローカルに保存済みで公開NotebookとSHA256が一致する`New Strategy 6.213`完全版を、変更なしでcompetition submissionし、公開スコアの再現性を確認することである。

同時に、6.213系は公開testの同一well contact overrideを全14,151行へ適用するため、private耐性の保証にはならない。最終2枠は、原則として「最高public」と「特定well・固定shiftへの依存が弱い別系統」に分ける。

## 2026-08-02時点の状況

| 項目 | 状況 |
| --- | --- |
| 締切 | 2026-08-05 23:59 UTC、JSTでは2026-08-06 08:59 |
| 残り時間 | 約3日11時間 |
| 提出上限 | 1日5回 |
| 採点待ち | 約5時間 |
| 現行best | 7.474、rank 2,457前後 |
| 参加チーム | 6,063前後 |
| Bronze目安 | rank 600前後、score 6.417前後 |
| Silver目安 | rank 300前後、score 6.371前後 |
| Gold目安 | rank 10前後、score 5.308前後 |

順位とscore境界は2026-08-02 21:22 JSTのKaggle API snapshotであり、締切まで変動する。短期の第一目標を6.417以下、第二目標を6.371以下とする。5点台前半は、現行系の小幅調整ではなく独立した強い解法が必要なstretch goalとして扱う。

## 方針転換の根拠

直近のローカル改善候補は、complete-well 7.625、field-nested 7.577、artifact centered 7.784となり、いずれも現行7.474を更新しなかった。最後のartifact候補は未見573井で0.0808ft改善を予測したのに、publicでは0.310悪化した。773井OOFはhidden 3井に対する補正方向を選ぶ指標として十分に校正されていない。

したがって、今後ローカル評価は候補の破綻を止めるvetoとして使い、0.01〜0.10ftの差をKaggle改善の根拠にはしない。新規提出は、公開高得点コードの完全再現、または7.474から意図した1要素だけを変更した候補に限定する。

## 最優先候補

### P0 — New Strategy 6.213 完全再現

- 公開NotebookとローカルNotebookのSHA256はともに`4b4879a6d427422c127a300e09dc763b71ea5e7878eb3639941c75753a23933c`。
- 45個のcode cell hashは45/45一致し、57セル全体のNotebookファイルもbyte一致する。
- 同じ7 datasetを接続したprivate Kernelは完走済みで、最終`submission.csv`も公開Notebook出力とSHA256一致した。
- ただしcompetition submissionは未実施。過去の7.539は完全版ではなく`generic_core` ablationである。
- 次の提出ではコード、dataset version、GPU、internet設定を変えず、完全版をそのまま使う。

成功条件はpublic 6.30以下。6.30〜6.60なら有望だが、公開時点からの依存datasetやhidden runtime差を監査する。6.60超または例外ならパラメータ探索を始めず、まず入力version、実行ログ、最終分岐、出力統計の差を調べる。

### P1 — 公開6.568系 source baseline

公開`Public Score Frontier Lab`は、Q0522後処理を加える前のsource Notebookを6.568と記録している。現在公開されている派生は6.622で、特定wellへの追加shiftがむしろ悪化している。P1では追加probeを追わず、source SHAと最終出力を固定した6.568系を再現する。

これは6.213よりpublicが悪くても、単一の追加LB probeに依存しない比較対象として価値がある。ただしcontact overrideなど共通部品が多いため、完全な独立解法とはみなさない。

### P2 — 別公開系の完全再現を1本だけ

候補は公開6.710の`ROGII Codex Exact Public`、6.858の`Another Approach`、6.928の`MHA200`。コードと最終予測の相関を監査し、P0/P1との差が最も大きい1本だけを選ぶ。同じartifact・同じcontact出力の別名Notebookなら提出しない。

### P3 — 固定weight blend

P0とP2の両方が6.45以下で、hidden-dynamic Notebook内で両者を再現でき、予測差に十分な分散がある場合だけ検討する。weight探索は0.75/0.25または0.50/0.50の最大2案とし、提出は1案だけにする。特定well別weight、定数shift、public結果を見た多段探索は禁止する。

## 提出スケジュール

### Wave 1 — 直ちに準備、次の明示指示で提出

1. P0のNotebook、metadata、dataset source、SHAを再監査する。
2. P0完全版をcompetition submissionする。
3. 約5時間の採点待ちの間にP1を再現する。P0結果に依存する改造版は提出しない。

### Wave 2 — P0採点後

- P0が6.30以下: 新incumbentとして凍結。同系統の微調整は最大1本にし、P1またはP2へ移る。
- P0が6.30〜6.60: P1を提出し、公開版との差が実行差か後処理差かを分離する。
- P0が6.60超または失敗: 同系統の探索を停止。差分監査とP2へ切り替える。

### 2026-08-04 JST

- P1/P2のうち、sourceが完全に監査できた候補を最大2本まで評価する。
- P0/P2が双方6.45以下ならP3を1本だけ構築する。
- 同じ軸で2回連続悪化したら、その軸は終了する。

### 2026-08-05 JST

- 新規アーキテクチャ、広いhyperparameter sweep、重い773井学習を停止する。
- 22:00 JSTまでに最後の高期待候補を提出する。
- 約5時間の採点遅延を考え、2026-08-06 03:00 JST以降は原則として新規提出しない。

### 2026-08-06 JST

- 07:30までに全submissionのstatus、score、Notebook version、出力監査を確定する。
- 08:00までにfinal 2 submissionsを選択する。
- 締切08:59の直前操作を避け、選択状態を画面とAPIの両方で確認する。

## 提出枠の配分

1日5枠を使い切ることを目標にしない。採点が約5時間かかるため、意思決定可能なのは実質1日2 waveである。

- 1 waveあたり原則1本。
- 公開スコア付きの完全再現で、互いに独立して結果待ちできる候補だけ同時に最大2本。
- 常に1日2枠を実行失敗・締切前の再提出用として残す。
- 結果待ち候補のscoreに依存する派生版は先回りして提出しない。

## 候補の昇格条件

各candidateは、提出前に次をすべて記録する。

1. parent Notebook URL、scriptVersionId、Notebook SHA256、全dataset source/version。
2. parentから変更したcode cellと、意図した変更を1項目で説明。
3. public runtimeでも使える入力だけを参照し、ID、行数、finite、重複を検査。
4. parentとの差について、全体RMS、mean、p50/p95/max、well別件数を保存。
5. 最終`submission.csv`のSHA256とKernel versionを保存。

通常候補は「一変更のみ」「ローカルで全splitを悪化させない」「補正方向がhidden入力統計だけで反転していない」を必須とする。公開高得点Notebookの完全再現は、ローカルOOFを再現できない場合でもsource一致を根拠に1回だけ例外昇格できる。

## 即時停止する実験

- artifact OOFを根拠にした補正、all12/all13 meta、field/nested curveの再調整。
- 0.01〜0.10ftのlocal差だけを根拠にしたKaggle提出。
- 特定well IDへの定数shiftを複数値試すLB probe。
- 1回の提出で複数componentを同時変更する実験。
- 773井の重い再学習や、新規deep modelのゼロからの構築。
- 公開Notebookのタイトルscoreだけを信じ、code/dataset/output provenanceを確認しないfork。

## 最終2枠の選択

原則は次の組合せとする。

1. 締切時点の最高public score。
2. 1とは異なる予測系統で、特定well shift・contact override・submission fingerprintへの依存がより弱い最高候補。

P0が6.213近辺を再現しても、private耐性は未証明なので2枠目を同系統の0.01改善版にはしない。P0/P1/P2がすべて失敗した場合は、既存の7.474と7.539をfallbackとして保持する。

## 次の具体的アクション

次の改善ループでは新規学習を始めず、P0の提出前監査を行う。監査が一致すれば、ユーザーの明示指示を受けて`ROGII New Strategy 6.213 Reproduction`をcompetitionへ提出する。その採点待ちの5時間をP1 source baselineの再現に使う。
