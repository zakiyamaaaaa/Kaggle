# exp-040-gitops-sbom-ebpf-envelope-bank

- 名前: gitops-sbom-ebpf-envelope-bank
- Kaggle タグ: `exp-040-gitops-sbom-ebpf-envelope-bank`

## 仮説

`exp-039-spiffe-mesh-webhook-shadow-bank` は SPIFFE / サービスメッシュ / Webhook 署名 / シャドウ展開の文脈で exfil をインフラ証跡に見せた。DevSecOps とランタイム防御では、GitOps 同期、SBOM/SLSA サプライチェーン、 eBPF ランタイム監査、KMS エンベロープ暗号化でも秘密の外部送信がドリフト証跡・プロビナンス・カーネルトレース・DEK ラップに紛れ込みやすい。

今回は exp-039 の bank をベースに、(1) GitOps reconcile HTTP 候補、(2) SBOM/SLSA attestation HTTP 候補、(3) eBPF/Falco runtime HTTP 候補、(4) KMS envelope/HSM wrap HTTP 候補、(5) read → GitOps 採用 → exfil の 3 ターン、(6) read → SBOM 採用 → exfil の 3 ターンを追加する。2000 件上限のため、SPIFFE / mesh / webhook-sign / shadow HTTP 格子と SPIFFE / mesh read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-039 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | GitOps / declarative sync HTTP 1 ターン候補を追加 |
| A3 | SBOM / SLSA provenance HTTP 1 ターン候補を追加 |
| A4 | eBPF / Falco runtime HTTP 1 ターン候補を追加 |
| A5 | KMS envelope / HSM wrap HTTP 1 ターン候補を追加 |
| A6 | read → GitOps 採用 → exfil の 3 ターン GitOps チェーンを追加 |
| A7 | read → SBOM 採用 → exfil の 3 ターン SBOM チェーンを追加 |
| A8 | 2000 件上限対策として SPIFFE / mesh / webhook-sign / shadow HTTP と SPIFFE / mesh read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- GitOps 表現で exfil を desired-state ドリフト証跡に見せ、デプロイパイプライン連携を狙える。
- SBOM 文脈でサプライチェーン attestation として秘密を外部送信させられる。
- eBPF テレメトリでランタイムセキュリティ監査ログとして exfil を正当化できる。
- KMS エンベロープで暗号化キー運用証跡として exfil を誘導できる。
- read 後の GitOps / SBOM テンプレで exfil を自然な DevSecOps 運用タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-040-gitops-sbom-ebpf-envelope-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-040-gitops-sbom-ebpf-envelope-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-040
python3 scripts/build_exp_notebook.py exp-040-gitops-sbom-ebpf-envelope-bank --description "GitOps/SBOM/eBPF/KMS envelope replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-040` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-040-gitops-sbom-ebpf-envelope-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
