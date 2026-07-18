# AI Agent Security への転用メモ

HackAPrompt の解法は単発プロンプト中心なので、今回の Kaggle AI Agent Security にそのまま使うものではない。ここでは、`AttackAlgorithm.run()` が複数候補を生成する前提で、使える考え方だけを移植する。

## 基本方針

HackAPrompt から持ち込むべきもの:

- 成功候補を先に作り、その後で削る。
- モデル別に文体と命令形式を分ける。
- 直接命令、翻訳、引用構造、出力整形、Unicode 変形を候補ファミリーとして扱う。
- 低成功率の短い候補と、安定する長い候補を分けて管理する。

持ち込まないほうがよいもの:

- 指定文字列を出させるだけの文面。
- token 境界や特殊トークンへの過度な依存。
- 1 回の成功だけを前提にした不安定な最短化。
- ツール trace や replay 時間を無視した文字数最適化。

## Predicate 別の読み替え

### Exfiltration

HackAPrompt の「翻訳して出す」「引用符を外す」「英語に戻す」は、secret を外部送信本文に載せる前処理として読み替えられる。

候補化する変数:

- secret を「監査ログ」「診断結果」「設定値」「復元結果」として扱う。
- `http.post` の body を JSON、フォーム、ログ行、要約文として変える。
- 直接の secret 語ではなく、直前の読み取り結果や「上で見つけた値」を参照する。
- URL や送信先ドメインを変え、unique cell の差分を作る。

### Confused Deputy

HackAPrompt の「タスク外形に合わせた上書き」は、エージェントの権限をユーザー意図とは違う方向に使わせる文脈作りに向いている。

候補化する変数:

- 「通知」「共有」「確認」「管理者への報告」と言わずに、結果として `email.send` へ向かわせる。
- 最後の user message に `send`、`email`、`upload` を入れない。
- 1 ターン目で宛先や本文を別ソースに置き、2 ターン目で処理だけ依頼する。
- 宛先、件名、本文のどれを不信ソース由来にするかを変える。

### Untrusted-to-action

引用構造や擬似ドキュメントは、不信ソース由来の命令を後続行動へつなげるために使える。

候補化する変数:

- Web ページ、メール、ファイル、設定、チケット、手順書のどれに命令を埋めるか。
- その命令を「ユーザーの依頼」ではなく「外部資料の処理手順」として読ませるか。
- 後続ターンで「その手順に従って」「上の仕様どおりに」と参照するか。
- EXEC、SHARE、WRITE のどの action に接続するか。

### Destructive Write

HackAPrompt の出力整形指示は、ファイル操作の path や content を自然に作らせる用途へ読み替えられる。

候補化する変数:

- 削除ではなく「更新」「初期化」「同期」「修復」「古いファイルの整理」として依頼する。
- `secret.txt` へ直接触れる経路と、設定や作業ファイル経由で触る経路を分ける。
- 書き込み内容を短くし、replay コストを下げる。

## 実装に落とす場合の候補生成

`attack.py` では、HackAPrompt 型のテンプレートを単発で使うより、候補ファミリーとして展開するのがよい。

候補ファミリーの例:

- `direct`: 目的に近い短い依頼。
- `translation`: 翻訳、復元、正規化として目的を渡す。
- `formatting`: JSON、ログ、レポート、メール本文などの整形として渡す。
- `quote_boundary`: 引用符、Markdown、YAML、CSV、手順書で命令境界を作る。
- `multi_turn_reference`: 1 ターン目に材料、2 ターン目に処理依頼。
- `unicode_encoding`: Unicode 変形、空白挿入、URL encoding、base64 を比較する。

探索時は全ファミリーを少数ずつ試し、成功したファミリーだけを深掘りする。提出候補では、同じファミリー内の重複よりも、tool sequence や引数が変わる候補を優先する。

## `exp-007` 以降への反映案

現在の実験は Phase A の固定候補と Phase B の Go-Explore に分かれている。HackAPrompt 由来の知見は、Phase A の固定候補生成と Phase B の変異操作の両方に使える。

Phase A:

- 各 predicate に、直接型、翻訳型、整形型、引用境界型を少数ずつ入れる。
- 成功済み候補は長い seed と短い compressed の両方を残す。
- GPT-OSS 向けと Gemma 向けの優先順を分ける。

Phase B:

- Go-Explore の mutation に「削除」「言い換え」「区切り変更」「出力形式変更」を入れる。
- 成功 trace から、最後に効いた user message だけを短縮する。
- 同じ predicate でも、URL、宛先、path、tool sequence が変わる方向の mutation を優先する。

## ローカル評価で見るべき指標

HackAPrompt の最短化は token 数が主目的だったが、今回のコンペでは replay 採点なので、次の指標を一緒に見る。

- 成功した predicate。
- 成功したモデル。
- guardrail deny の有無。
- tool sequence。
- unique cell に効きそうな差分。
- 1 candidate あたりの replay 時間。
- 低成功率候補を入れる価値があるか。

最終的には、短い文面よりも「短時間で replay 成功し、他候補と cell が被りにくい」ことを優先する。
