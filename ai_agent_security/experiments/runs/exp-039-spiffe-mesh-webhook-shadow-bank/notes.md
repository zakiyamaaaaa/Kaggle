# exp-039-spiffe-mesh-webhook-shadow-bank

- 名前: spiffe-mesh-webhook-shadow-bank
- Kaggle タグ: `exp-039-spiffe-mesh-webhook-shadow-bank`

## 仮説

`exp-038-hitl-a2a-cache-bank` は HITL / A2A / ツールキャッシュ / allowlist プローブの文脈で exfil を正当化した。クラウドネイティブのゼロトラスト基盤では、SPIFFE ワークロード ID、サービスメッシュの egress 監査、Webhook HMAC 検証、シャドウ／カナリア展開のテレメトリでも秘密の外部送信が SVID ブートストラップ証跡・サイドカー監査・署名付きコールバック・ダークローンミラーに紛れ込みやすい。

今回は exp-038 の bank をベースに、(1) SPIFFE attestation HTTP 候補、(2) service mesh egress HTTP 候補、(3) webhook HMAC HTTP 候補、(4) shadow/canary HTTP 候補、(5) read → SPIFFE 採用 → exfil の 3 ターン、(6) read → mesh 採用 → exfil の 3 ターンを追加する。2000 件上限のため、HITL / A2A / tool-cache / allowlist HTTP 格子と HITL / A2A read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-038 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | SPIFFE / workload identity HTTP 1 ターン候補を追加 |
| A3 | service mesh egress HTTP 1 ターン候補を追加 |
| A4 | webhook HMAC verification HTTP 1 ターン候補を追加 |
| A5 | shadow / canary deployment HTTP 1 ターン候補を追加 |
| A6 | read → SPIFFE 採用 → exfil の 3 ターン SPIFFE チェーンを追加 |
| A7 | read → mesh 採用 → exfil の 3 ターン mesh チェーンを追加 |
| A8 | 2000 件上限対策として HITL / A2A / tool-cache / allowlist HTTP と HITL / A2A read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- SPIFFE 表現で exfil をワークロード参加証跡に見せ、ゼロトラスト ID ブローカーを狙える。
- メッシュ egress 文脈でサイドカー監査ログとして秘密を外部送信させられる。
- Webhook 署名検証で配信コールバックの正当なペイロードに exfil を偽装できる。
- シャドウ／カナリアで本番影響のないテレメトリとして exfil を誘導できる。
- read 後の SPIFFE / mesh テンプレで exfil を自然なインフラ運用タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-039-spiffe-mesh-webhook-shadow-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-039-spiffe-mesh-webhook-shadow-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-039
python3 scripts/build_exp_notebook.py exp-039-spiffe-mesh-webhook-shadow-bank --description "SPIFFE/mesh/webhook-sign/shadow replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-039` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-039-spiffe-mesh-webhook-shadow-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
