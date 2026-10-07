# Genesis｜Excel・VBA静的解析／業務設計支援／販売管理閲覧デモ

業務依頼を整理するGenesis、Excel静的解析、Access販売管理の閲覧をまとめたローカル実行用デモです。販売データはすべて架空です。

**Accessの構造・SQL・VBAを調べる「Genesis Access解析」は別製品で、この公開版には含まれていません。** この公開版のAccess接続は、販売管理データの読取り用です。

## 機能と確認範囲

| 画面 | 機能 | 今回の確認 |
|---|---|---|
| `/` | 依頼保存・質問・詳細設計・承認待ち | API送信なしのリハーサルで画面操作を確認 |
| `/sales` | 見積・受注・納品・売上・請求・入金・消込・追跡の閲覧 | 架空Accessデータの読取りと請求残6,000円を確認 |
| `/excel` | Excel構造・VBAソースの静的解析と結果出力 | 合成教材の解析・出力・破損入力の拒否を確認 |

2026-10-07、公開用コピーで自動試験 **57件成功・0件失敗**。VBA実行、伝票登録、実印刷、実AI接続、実運用は今回の確認に含みません。

## 必要環境

- Windows 64bit、Python 3.12以降、Windows PowerShell 5.1、Webブラウザー。
- `DAO.DBEngine.120` が利用できるAccessデータベースエンジン。PowerShellとエンジンのビット数を合わせます。
- Java / javac（確認環境はJDK 24）。両方をPATHから呼び出せる状態にします。
- Python依存は `requirements.txt`、Java依存は `demo/java-dependencies.json` に固定しています。

別PCへの新規インストール、他のOffice構成、他OSは未確認です。

## 起動方法

リポジトリのルートで実行します。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\setup_java.py
powershell -NoProfile -ExecutionPolicy Bypass -File tools\setup_sales_demo.ps1
.\.venv\Scripts\python.exe run.py --port 8773
```

`http://127.0.0.1:8773/sales` を開きます。Genesisは `/`、Excel解析は `/excel` です。終了は端末でCtrl+Cです。

JavaセットアップはMaven Centralから依存を取得し、SHA-256を照合してコンパイルします。販売セットアップは新しいDBに架空データだけを投入します。既存DBがある場合は上書きしません。画面のwork・testはどちらも架空データです。

GenesisではAPI送信なしのリハーサルを選択してください。APIキーは同梱していません。実AI実行には別途設定・送信確認が必要です。ローカルホストで使用します。

## 構成

| フォルダ・ファイル | 内容 |
|---|---|
| app/ | Genesis・Excel解析・販売閲覧コード、画面、設定例 |
| app/java/ | VBA読取り用Javaソース |
| demo/ | DB構造定義、Java依存とハッシュ |
| tools/ | 架空DB生成、依存セットアップ、試験 |
| 標準テストExcel/ | 架空の静的解析教材 |
| docs/ | 試験結果、公開判断、公開ファイル一覧 |
| run.py | 起動入口 |

販売画面は `sales_server → v07_server → excel_server → server` とGenesisの既存処理を直接利用します。本体の重複配布を避けるため一つのリポジトリにしています。元のAccess・Excel製品本体は同梱していません。

## 試験と制限

```powershell
.\.venv\Scripts\python.exe tools\smoke_test.py
```

- 販売データは確認用に直接投入しています。見積から入金までの登録処理の成功を証明するものではありません。
- `.xlsb` 教材は静的解析用の最小コンテナーです。教材のExcel編集・マクロ実行は未確認です。corrupt.xlsmとencrypted.xlsは異常系用です。
- Genesisの業務解析レポートのExcel出力は `@oai/artifact-tool` に依存し、一般環境での取得を確認できないため利用確認対象外です。Excel静的解析の結果出力とは別機能です。
- 既存資産一覧は開発時の記録です。他製品の同梱・接続済みを意味しません。
- 画面画像、元の業務ファイル、過去ログ、未確認の登録処理は公開から除外しています。

[試験結果](docs/test-results.json)・[公開確認報告](docs/RELEASE_REVIEW.md)・[公開ファイル一覧](docs/public-files.csv)を参照してください。実行後のDB・ログ・解析結果はGit管理対象外です。
