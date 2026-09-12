# Kaggriculture S01

Kaggleの **Kaggriculture** 用エージェント開発プロジェクトです。農場シミュレーションの観測値を読み、毎ターンの移動・作業・市場取引を決めるエージェントを作成します。

## 目的

空の農場からスタートし、作物・家畜・土地・市場を管理して、シーズン終了時の資金を他のエージェントより多くすることが目的です。勝敗は収益額そのものではなく、他エージェントとの対戦結果をもとにしたランキングで決まります。

このコンペは、LLMを必須とするものではありません。まずはルールベース・探索・最適化を土台にし、必要に応じてLLMを計画・説明・方策改善に使える構成にしています。

Kaggle概要ではPoints & Medals対象です。現在の公式タイムライン上の最終提出締切は **2026年9月30日 23:59 UTC（日本時間10月1日 08:59）** です。締切やルールは変更される可能性があるため、提出前に公式ページを確認してください。

## セットアップ

```bash
cd /Users/shoichiyamazaki/Kaggle/kaggriculture_s01
uv sync --dev
```

`uv` がPython 3.12環境と依存パッケージをプロジェクト内の `.venv` に用意します。

## ローカル対戦テスト

```bash
uv run python scripts/run_local.py
```

現在の雛形エージェントをKaggriculture環境で実行し、エピソード終了時の報酬を表示します。依存環境のバージョンは、競技環境とのずれを避けるため `kaggle-environments==1.32.7` に固定しています。

## エージェントの場所

- `src/kaggriculture_agent/agent.py`: Kaggle提出用の `agent(obs)`
- `main.py`: 依存なしで単体提出できる初期ベースライン
- `scripts/run_local.py`: ローカル実行・対戦確認
- `tests/`: 最低限のスキーマ・動作テスト
- `notebooks/`: Kaggle Notebookへ移植する際の作業場所

Kaggle提出時は、提出ファイルのルートに `agent(obs)` を置くか、Kaggle Notebookからこの関数を呼び出します。

## 公式ページ

- [Kaggriculture（Kaggle）](https://www.kaggle.com/competitions/kaggriculture/)
- [Kaggle Environments](https://github.com/Kaggle/kaggle-environments)

公式ページの締切・ルール・現在の環境仕様を最終確認してから提出してください。
