# exp-049-eventstore-memory-provenance-vault-bank

- 名前: eventstore-memory-provenance-vault-bank
- Kaggle タグ: `exp-049-eventstore-memory-provenance-vault-bank`

## 仮説

`exp-048-workflow-dag-taskqueue-checkpoint-idempotency-bank` はワークフロー DAG / タスクキュー / チェックポイント再開 / 冪等性キーの文脈で exfil をエージェントワークフロー基盤の運用証跡に見せた。AI エージェントの監査・記憶・ツール追跡・秘密管理基盤では、イベントソーシング（event store）、コンテキストウィンドウ圧縮（memory compaction）、ツール呼び出し由来追跡（tool provenance）、シークレットボルト（secrets vault / KMS）でも、秘密情報の外部送信が正当な不変監査ログ・メモリ要約ペイロード・呼び出し系譜記録・鍵管理監査証跡に紛れ込みやすい。

今回は exp-048 の bank をベースに、(1) event store HTTP 候補、(2) memory compaction HTTP 候補、(3) tool provenance HTTP 候補、(4) secrets vault HTTP 候補、(5) read → event store 採用 → exfil の 3 ターン、(6) read → secrets vault 採用 → exfil の 3 ターンを追加する。2000 件上限のため、workflow DAG / task queue / checkpoint resume / idempotency key HTTP 格子と workflow DAG / checkpoint resume read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-048 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | event store / immutable audit log HTTP 1 ターン候補を追加 |
| A3 | memory compaction / context window merge HTTP 1 ターン候補を追加 |
| A4 | tool provenance / invocation lineage HTTP 1 ターン候補を追加 |
| A5 | secrets vault / KMS broker HTTP 1 ターン候補を追加 |
| A6 | read → event store 採用 → exfil の 3 ターン event store チェーンを追加 |
| A7 | read → secrets vault 採用 → exfil の 3 ターン secrets vault チェーンを追加 |
| A8 | 2000 件上限対策として workflow DAG / task queue / checkpoint resume / idempotency key HTTP と workflow DAG / checkpoint resume read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- イベントソーシング表現で exfil を不変監査ログに見せ、エージェント行動追跡境界を狙える。
- メモリ圧縮文脈で context window 要約ペイロードとして秘密を外部送信させられる。
- ツール由来追跡で invocation lineage 記録として exfil を正当化できる。
- シークレットボルトで KMS 監査証跡として exfil を誘導できる。
- read 後の event store / secrets vault テンプレで exfil を自然なエージェント監査・鍵管理タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-049-eventstore-memory-provenance-vault-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-049-eventstore-memory-provenance-vault-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-049
python3 scripts/build_exp_notebook.py exp-049-eventstore-memory-provenance-vault-bank --description "Event store/memory compaction/tool provenance/secrets vault replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-049` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-049-eventstore-memory-provenance-vault-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
