# HackAPrompt 2023 上位解法メモ

このフォルダは、現在取り組んでいる Kaggle AI Agent Security の実験メモとは分けて、過去コンペ HackAPrompt 2023 の上位解法から参考になりそうな観点を整理したものです。

参照元:

- Repository: https://github.com/gstaff/hackaprompt-solutions
- README: https://raw.githubusercontent.com/gstaff/hackaprompt-solutions/main/README.md
- Main submissions: https://github.com/gstaff/hackaprompt-solutions/tree/main/main_submissions
- Flan-only submissions: https://github.com/gstaff/hackaprompt-solutions/tree/main/flan_only_submissions

## 何が参考になるか

HackAPrompt は、各レベルの固定タスクに対して短いプロンプトを提出する形式だった。一方、このリポジトリの Kaggle AI Agent Security は、`attack.py` が環境と対話して replay 可能な `AttackCandidate` を返すアルゴリズム型コンペである。

そのため、HackAPrompt の文面をそのまま移植するのではなく、次の観点を取り出して使う。

- 成功条件から逆算して、余計な説明を削る。
- モデル別に効きやすい命令形式を分ける。
- 不安定な成功を許容し、複数回試行できる候補群として扱う。
- 文字数・トークン数を継続的に圧縮する。
- 文字種、引用符、区切り、翻訳、反復などの小さい表現差を探索対象にする。

## ファイル構成

- `solution-patterns.md`: 提出 JSON に見られるプロンプト攻撃パターンの分類。
- `optimization-notes.md`: v1 から最終版までの圧縮・探索プロセスの読み取り。
- `adaptation-to-ai-agent-security.md`: 現在の multi-step tool attack コンペへ転用する際の具体的な読み替え。

## 注意

HackAPrompt のゴールは「指定フレーズを出させる」ことであり、今回のコンペのゴールは「ツール利用エージェントに security predicate を発火させる」こと。したがって、参考にする中心は最終文字列ではなく、探索設計・候補生成・圧縮・モデル差分の扱いである。
