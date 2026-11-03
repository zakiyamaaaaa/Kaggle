# Discussion調査

対象: 2026-09-17 00:00 JST 〜 2026-09-20 CLI取得時点。親投稿14件を対象に、各スレッドのコメントを `kaggle competitions topics show` / `topic-messages` で確認した。

## 実装・評価に有用

### 741743 — Finally reached the silver medal zone with Reinforcement Learning

https://www.kaggle.com/competitions/kaggriculture/discussion/741743

- 投稿者の回答では **macro-level** のPPO。
- 約30万 games。BCでwarm-upしてからRLへ切り替えた。
- BCデータは公式top-match replay、またはtop teamのreplayをローカル収集。
- rewardは初期はbank difference、後半は最終WIN/LOSSも加え、補助rewardで安定化。
- checkpointはローカルleaderboardで比較し、ときどき実Kaggle ladderで確認。live feedbackが遅いため、replayだけで最終候補を決めない。

**判断:** RLを全720 stepのlow-level actionへ直接適用するより、現在の計画選択・phase切替にmacro PPOを使う方向が妥当。ただし実装詳細は非公開なので、そのまま再現できる情報ではない。

### 741722 — Evaluation of agent generalization and prevent overfitting?

https://www.kaggle.com/competitions/kaggriculture/discussion/741722

- rule-basedでも同じseed・同じ相手に繰り返し調整すれば過学習する。
- development setは固定して探索に使う。
- candidateを凍結した後、別seedと異なる戦略ファミリーのheld-out opponentで評価する。
- 同じseed・相手・seatで旧版とcandidateをpaired比較し、全体平均だけでなくwin rate、final money、opponent別結果を見る。
- held-out結果を見て再調整し続けると、それはもうdevelopment setになる。

**判断:** このプロジェクトのPopulation Arena方針を支持する。今後の新候補では、同系統のSalem派生だけでなく、V47/V52系・作物中心・家畜中心・市場順序系を別familyとして固定する。

### 742025 — How do you decide which crops to plant?

https://www.kaggle.com/competitions/kaggriculture/discussion/742025

提案された作物評価軸は、単純な売価ではなく次の組み合わせ。

- realistic yield × expected sale price − seed/fertilizer/worker cost
- profit per occupied tile-day
- profit per worker action（労働がボトルネックの場合）
- market demand、両者の供給、売却予定時点
- cash buffer、残り日数、収穫・売却がseason内に間に合うか

**判断:** `independent_agent.py` のpriorityに「tile-day」「worker action」「売却までの残りstep」を明示的に加える仮説として有用。一般論なので、採用はpaired simulationで確認する。

### 742005 — Use of Gurobi or other optimization algorithms in the submission

https://www.kaggle.com/competitions/kaggriculture/discussion/742005

- HiGHSを試したが遅すぎたため、deterministic initializer＋daily heuristicへ移行したという報告。
- 他のコメントも、相手の行動に依存するため完全最適化は難しいという見方。

**判断:** 現在のsubmission環境と毎step制約を考えると、solverをruntimeに置くより、offlineで候補planを生成し、onlineは軽量なheuristic/plan selectorにする方針が安全。

### 742083 — Disproportionate Rating Drop After a Close Defeat

https://www.kaggle.com/competitions/kaggriculture/discussion/742083

- コメントでは、勝敗は3値 WIN/DRAW/LOSSで、少なくとも1ドル差でWIN。
- score margin自体を直接ratingに入れるのではなく、実際のprofitによる勝敗がrating更新の入力になるという説明。
- 市場価格は日ごとに変化する。

**判断:** local評価の第一指標をmarginではなくpaired win pointsに置き、marginは診断値として保存する現在の方針を継続する。

## 注意喚起として有用

### 742035 — Scam alert: fake “Kaggle Staff” account

https://www.kaggle.com/competitions/kaggriculture/discussion/742035

偽のKaggle Staffアカウントがsource codeを要求していた。報告後に偽アカウントは削除されたが、同名・同画像の別アカウントも報告されている。Source codeやtokenをDiscussionの依頼者へ渡さない。

## 参考にはなるが、今回の実装材料としては弱い

- 741730 `RL Progress update : self play`: animals、fertilizer、cropの学習が崩れやすいという経験談。問題設定の難しさは示すが、再現可能な改善策は少ない。
- 742111 `I let a fruit fly's brain play Kaggriculture`: connectome的な実験紹介。アイデアとして面白いが、現行候補へ直接使える検証値はない。
- 742063、742078、742120、742158、742165: 取得時点で、実装判断に使えるコメントなし。
- 742130: gold medal数への雑談で、方策改善の情報なし。
