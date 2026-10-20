# SOP：nmud 语料风格分析与排版生成器

> 一次可复现的完整流程。目标机是**校机**（`<hostname>`，用户 `<username>`），本机只做编辑和取回。
> 全部产物：校机项目根下的 `tools\`（脚本与包）、`out\`（结果）、`tmp\`（暂存），以及本仓库（源码、语料、拟合参数）。
> 本文里的路径一律是**相对路径**：校机项目根由 `guest\remote.cfg` 的 `remote_root` 决定，仓库内的文件按 `guest\`、`checks\` 这样的目录写。
> 结论报告见 `nmud_corpus_report.md`；本文只讲**怎么跑起来**。
>
> **分工**：本机**不装任何环境**（没有 jieba、没有虚拟环境）。解释器、jieba、语料、拟合参数
> 全在校机，本仓库只留源码；一键流程是"把源码推到校机算，结果拉回来"。

## 0. 一句话

```powershell
# 本机：把包同步到校机 -> 校机跑 -> 拉结果
& ".\guest\run_pkg.ps1" -TimeoutSec 900 `
    -PyArgs @("--in","<校机>\tools\your.txt","--out","<校机>\out\your_styled.txt")
& ".\guest\pull.ps1" -RemoteFile "<校机>\out\your_styled.txt" -LocalFile ".\your_styled.txt"
```

## 1. 环境

| 项 | 值 |
| --- | --- |
| SSH 别名 | `school-guest`（`ProxyCommand` 跳板链）、`school-guest-lan`（直连 `<校机的局域网地址>`） |
| 校机 | `<hostname>`，默认 shell `cmd.exe` |
| 虚拟环境 | 校机项目根下的 `.venv`（Python 3.12.15）——**解释器在校机里，不在本机** |
| 关键包 | jieba 0.42.1(+posseg)、thulac、pkuseg、hanlp 2.1.5、torch 2.14.1+cpu、spacy、stanza |
| 目录布局 | `tools\` 脚本与包／`out\` 结果／`logs\` 日志／`tmp\` 暂存 |
| 生成器包 | `tools\nmud_style\`（本仓库 `nmud_style\` 同步过去的，含 `data\` 里的语料与拟合参数） |
| 语料 | `tools\nmud.txt` 与 `tools\nmud_style\data\nmud.txt`（MD5 `65bb708768ee4d8b5b6f10e0bcd52180`，5087 字节，**按原始字节存，CRLF**） |

本机（Windows 工作站）上**没有** jieba，**也不装**：校机内网连不上 GitHub，`spacy download` 与 `stanza.download` 都会失败，但**不影响本流程**，jieba 已经够用。

## 2. 助手脚本（本仓库 `guest\`）

| 脚本 | 干什么 | 用法 |
| --- | --- | --- |
| `remote.ps1` | 把一个本地 `.ps1` 推到校机执行，抓回 stdout/stderr | `-Script <本地路径> -HostName school-guest` |
| `push2.ps1` | 传文件到校机（分块 base64 + MD5 校验） | `-LocalFile <本地> -RemotePath <校机路径> -HostName school-guest` |
| `pull.ps1` | 从校机取文件 | `-RemoteFile <校机路径> -LocalFile <本地>` |
| `sync_package.ps1` | **把本仓库的 `nmud_style\` 包同步到校机**：先问校机要每个文件的 md5，只推不一样的 | `-HostName school-guest [-Force]` |
| `run_pkg.ps1` | 同步包 → 校机用 venv 的 python 跑 `python -m nmud_style` | `-PyArgs @("--in","x","--out","y") [-SkipSync]` |
| `runpy.ps1` | 推一个平铺 `.py` 到校机跑（分析脚本用），顺带推它 import 的同目录模块 | `-Script <本地 .py> -PyArgs @(...)` |
| `runps.ps1` | 推一个 `.ps1` 到校机、用 PowerShell 跑 | `-Script <本地 .ps1>` |
| `setup-guest.ps1` | **校机侧装环境**：同步包 → 推 `setup_env.ps1` 过去 → 在校机跑检测与安装 | `-TimeoutSec 900` |
| `style-clipboard.ps1` | 一键：剪切板 → 校机 → 剪切板 | `-HostName school-guest` |
| `test_clipboard.ps1` | 一键流程的回归测试（先存剪切板，验完原样恢复） | `-HostName school-guest` |

`nlp_common.ps1` 是它们共用的底座（读配置、提问、找同级脚本），`remote.cfg` 是配置文件。

**所有 SSH 和文件传输都走 `pwsh` 工具**，不要用 `ops_bash`（见 §6 坑 1）。

**校机侧的 `setup_env.ps1` 在校机上跑**（由 `setup-guest.ps1` 推过去）：它查虚拟环境、jieba、包与数据文件，缺什么装什么，最后跑一句自检。


## 2.1 没有绝对路径：配置 + 提问

脚本里一个绝对路径都没有写死。两处各有一份"路径从哪来"：

**校机上的 Python 工具**（`nlp_paths.py`）——按"离脚本最近"找文件，找不到就问：

| 要找的东西 | 找法 |
| --- | --- |
| 语料 `nmud.txt` | 脚本同级 → 同级 `tools\` → 上一级 → 上一级 `tools\` |
| 结果 json | 同级 `out\` → 上一级 `out\` |
| hanlp 模型 | 同级 `hanlp_models\` → 上一级 `tools\hanlp_models\` |

命令行参数最大：`--corpus` / `--out` / `--cache` / `--in` / `--report` 都覆盖自动查找。`nmud_style.py` **裸跑**（不给任何参数）会问"要排版的中文文件"和"结果写到哪里"；给了任意参数就不问。stdin 是 EOF（SSH 远程执行、非交互管道）时，打印 `(no console input)` 并跳过这一问，不挂死。

验证交互本身：

```
printf 'my answer\nC:/path/to/nmud.txt\n' | python -X utf8 test_nlp_paths.py
python -X utf8 test_nlp_paths.py < /dev/null      # EOF 分支
```

**本机的 PowerShell 助手**——`remote.cfg` 存两行：

```
host=school-guest
remote_root=<校机上的项目根>      # `guest\remote.cfg` 是本机文件，仓库只带 `guest\remote.cfg.example`；
                                   # 第一次跑会问一次，问完就写回 remote.cfg
```

缺哪行就问哪行，答完写回 `remote.cfg`。`-HostName` 参数优先于配置。

```
### the guest paths
school machine: ssh alias or host name     [school-guest]
project folder on the school machine (holds tools\ and out\)  [<校机上的项目根>]
```

改机器只要改这个文件，脚本不用动。


## 3. 完整流程

### 3.1 语料分析（产出 §1–§4 的数字）

```powershell
& ".\guest\runpy.ps1" -Script ".\checks\nmud_rules.py" -TimeoutSec 900 `
    -PyArgs @("--out","<校机>\out\nmud_rules.json")
& ".\guest\pull.ps1" -RemoteFile "<校机>\out\nmud_rules.json" -LocalFile ".\checks\nmud_rules.json"
```

### 3.2 模型拟合与评分（产出 §5–§6 的数字）

```powershell
# --refit 会重跑网格搜索，约 4 分钟，放后台
& ".\guest\run_pkg.ps1" -TimeoutSec 3000 -PyArgs @("--refit","--report","<校机>\out\nmud_style.json")
```

不带 `--refit` 就用缓存的 `data\nmud_style_params.json`（秒级）。拟合权重：网格搜索 → **段落级两折留出**（1–32 段 / 33–64 段互训互测）→ 胜出的折进最终模型。

### 3.3 生成排版结果

```powershell
# 任意中文文件 -> nmud 排版（包会先同步到校机）
& ".\guest\run_pkg.ps1" -TimeoutSec 900 `
    -PyArgs @("--in","<校机>\tools\demo_plain.txt","--out","<校机>\out\demo_styled.txt")
# 内置示例（不碰文件）
& ".\guest\run_pkg.ps1" -TimeoutSec 900 -PyArgs @("--demo")
```

**在一台自己跑生成器的机器上**（装了 `pip install .` 之后）：

```powershell
nmud-style --in a.txt --out b.txt
python -m nmud_style --demo
```

输入约定：**空行分段，段内的换行也是边界**（换行当空格处理，所以上一行末尾不会和下一行开头粘成一个词）。行内已有的空格被当作"作者选好的边界"照单全收。

**标点按作者自己的用法处理**（语料实测：作者只留 `…？！""` 四种，句号逗号顿号分号冒号括号全是 0 次，而且**标点从不独立成单元**）：

- 工具默认把作者从不用的句读（`，。、；：（）` 之类）**换成空格**——那个位置本来就是写者选定的边界，跟输入里已有的空白一个待遇；删掉而不是换空格，会把两边的词焊成 `生词没有`。
- 其余标点在切分之前就**归位到词上**：开引号贴短语首（`“象语`），闭引号贴短语尾（`语”`），省略号贴词（段首 `…刚刚`、词尾 `又有点…`），问号感叹号贴词尾（`坏事？`）。**标点不占一格。**
- `--keep-punct` 保留全部标点，仍然贴在词上。

默认输出与"人工按清单去掉标点再跑"的结果**逐字节相同**（`demo3_styled.txt` == `demo4_styled.txt`），这一条在 `check_report.py` 里有断言。

### 3.3.1 一键：剪切板 → nmud 语 → 剪切板

```
双击  仓库根目录的 `nmud-style.bat`
```

流程：`Get-Clipboard` 取文本 → 推到校机 `tmp\clip_in_<时间戳>.txt` → 校机跑 `python -m nmud_style --in/--out` → 拉回 `tmp\clip_out_<时间戳>.txt` → `Set-Clipboard` 写回。约 10 秒。

**本机不装环境**，算在校机：跑之前 `sync_package.ps1` 先问校机要每个文件的 md5，只推不一样的（没改过源码就一个字节都不传）。

空剪切板不动；校机还没装好就先跑一次 `setup-guest.bat`（见 §3.6）。

回归测试（先存剪切板，验完原样恢复）：

```powershell
& ".\guest\test_clipboard.ps1"
```

### 3.6 把校机装好（环境检测 + 安装）

```
双击  仓库根目录的 `setup-guest.bat`
```

它做三件事：

1. `sync_package.ps1`：把 `nmud_style\` 包推到校机（只推 md5 不一样的）。
2. 把 `guest\setup_env.ps1` 推到校机 `tmp\`，在校机那边执行：查虚拟环境 → 查 jieba（缺就 `pip install`）→ 查包与数据文件 → 跑一句自检。
3. 把自检产出的文本拉回本机显示（**不让中文走 ssh 回显**：ssh 的转录会按本机代码页解码，中文会变乱码，所以中文一律用文件带回来）。

**在一台自己跑生成器的机器上**用另一个入口（检测 + 装进本仓库的 `.venv` + 自检）：

```powershell
python -X utf8 ".\setup_env.py"          # 任何平台
python -X utf8 ".\setup_env.py" --check  # 只检测
python -X utf8 ".\setup_env.py" --proxy 127.0.0.1:7897
```

`setup_env.py` 依次试 PyPI、清华源、阿里源和本机代理；虚拟环境建不起来（沙箱、锁死的 python）就退回当前解释器装。`nmud-style --check-env` 只报告不装。

### 3.4 验收（102 项检查）

```powershell
python -X utf8 ".\checks\check_report.py"
```

路径按脚本自身的位置算，在哪个目录跑都行。

- 前 60 项：报告里每个数字都跟 `nmud_rules.json` / `nmud_style.json` 对一遍（**从 JSON 复算，不抄报告**）。**报告里必须写着这个数，而且这个数必须与 JSON 一致**——重拟合之后数字变了而报告没跟上，检查会当场 FAIL。
- 后 42 项：嗓音层的标点普查、连接词段首数、段尾唯一性、句长统计，四个 demo 输出里"汉字与西文不相邻"和"`90.8%` 不被拆开"，以及标点规则：语料里句号逗号顿号分号冒号括号全为 0、省略号 6、问号 1、感叹号 1、引号 4 对、**没有一个单元只由标点组成**；生成的 demo 里也没有标点自成一格；默认输出与人工去标点版逐字节相同。

期望读数：`PASS 102` / `FAIL 0`。**任何一项 FAIL 都不要发报告**——上次"66 处还是 65 处"的错就是这类问题。

### 3.5 回归：改了脚本之后确认输出没变

```powershell
& ".\guest\regress.ps1"
```

它把 5 个工具各跑一遍，输出写到校机 `tmp\regress_*.json`，再在校机上跟 `out\` 里现有的 json 比 md5，**同 md5 = 只改了路径没改行为**。比对也在校机做，文件不回本机。约 10 分钟。

扫脚本里还剩哪些绝对路径：

```powershell
python -X utf8 ".\checks\scan_paths.py"
```

现在只剩 `remote.cfg`（配置本身）和 `test_nlp_paths.py` 的文档字符串示例两处。

## 4. 验收读数（2026-10-20 现行）

| 指标 | 值 |
| --- | --- |
| 留出 F1（两折合并） | **0.8095**（P 0.7992 / R 0.8200） |
| A 折测试 F1 / B 折测试 F1 | 0.8133 / 0.8061 |
| 往返（删掉作者空格再切） | **367/500 = 73.4%** |
| 基线（每词都切）F1 | 0.5065 |
| 权重 | `w_open=2.0 w_close=1.0 w_posstart=0.0 w_posend=0.0 w_de_next=0.0 w_de_prev=0.5`，长度带 [2,4] |
| 折行 | 软宽 18 列，每行 ≤4 单元 |

## 5. 复现的配方（四层）

1. **切分**：DP + 5 个特征，长度带 [2,4]。标点在切分之前归位到词上（不占一格）。
2. **空格**：一个单元里不能同时有汉字和拉丁/数字——**切完之后**再把跨中西交界的单元一分为二。作者从不用的句读换成空格，其余标点贴在词上。
3. **折行**：每行 2–4 单元，软宽 18 列。
4. **篇章**：空行分段，段长 1–4 行。

嗓音层（人工照抄清单，语料实测）：句号 0、逗号 0、顿号 0、分号 0、冒号 0、问号 1、感叹号 1、省略号 6、引号 4 对；**标点从不独立成单元**；`nmud` 46 次替"我"；19 个疑问段 0 个问号；64 段 64 种收尾。

## 6. 踩过的坑

1. **`ops_bash` 跑不了子进程**：`python subprocess` 和管道捕获都被沙箱挡（`PermissionError [WinError 5]` / EPERM）。**SSH、文件传输一律走 `pwsh` 工具**。
2. **`scp` / `sftp` 不可用**：会挂死。文件只能走 `push2.ps1` / `pull.ps1` 的分块 base64。
3. **校机 PowerShell 读 `.ps1` 当 ANSI**：`.ps1` 里的中文 here-string 到校机会变乱码。**中文一律用 `\uXXXX` 转义**，或把 `.py` 当二进制 base64 推。
4. **`.bat` 必须是 CRLF**：仓库 `core.autocrlf=input` 会把 `.bat` 写成 LF，cmd.exe 对纯 LF 批处理不稳。
5. **"单元不混排"不能当 DP 硬约束**：写进转移条件会跟长度带打架，留出 F1 0.7948→0.7641、往返 73.0%→65.4%、1 字单元 6→61。**正确的位置是切完之后再切一刀。**
6. **ASCII 标点要归 WEST**：否则 `90.8%` 会被切成 `90.8 %`；而 jieba 把 `%` 单独标成非语素 `x`，要主动并回它前面的西文词。
7. **HanLP 的命中率是假的**：输出不拼回去就是 64%，`integrity.py` 逐字还原校验后真值是 0.9801。
8. **断言要在脚本里写死**：`nmud_rules.py` 用 `assert` 强制"单元必须无缝平铺 STREAM"，否则单元数会在 299/492/500 之间摇摆。
9. **远端路径不能走 `Join-Path`**：它会校验盘符，而校机的 `D:` 在本机不存在 → "Cannot find drive"。远端路径一律用 `nlp_common.ps1` 的 `Join-NlpRemote` 拼字符串。
10. **共享模块要跟着推**：`nlp_paths.py` 被 5 个工具 import，光推主脚本校机会 `ModuleNotFoundError`。`runpy.ps1` 现在会自动扫主脚本的 import 语句，把同目录的兄弟模块一起推上去。
11. **远程执行没有 stdin**：SSH 会话的 stdin 没人写，脚本里的 `input()` 会一直挂着（实测挂到 600 s 超时）。`remote.ps1` / `pull.ps1` 现在把 stdin 接一个**空文件**——客机端立刻拿到 EOF，`nlp_paths.ask` 打印 `(no console input)` 并跳过这一步。校机上想手动交互问答，要在那台机器的终端里直接跑脚本，别走 SSH。
12. **PowerShell 的 `Join-Path` 会校验盘符**：本机没有 `D:`，拼远端路径会报 "Cannot find drive"。远端路径一律用 `nlp_common.ps1` 的 `Join-NlpRemote` 拼字符串。
13. **段内换行不能直接拼**：`"".join(段内各行)` 会把上一行末尾和下一行开头焊成一个词（`shake` + `6月26日…` → `shake6月26日…`）。改成 `" ".join(...)`，换行就成了一个保留的边界。语料那条路径（`para_units`）不动——它拼的就是作者自己的单元序列。
14. **Windows PowerShell 5.1 与 7 不一样**（`.bat` 里 `powershell` 走的是 5.1）：
    - **模块自动加载会整个失效**：环境里若同时装着 PowerShell 7，7.x 的模块目录也在 `PSModulePath` 上，5.1 会去加载那一份、然后一个 cmdlet 都找不到（`Get-FileHash is not recognized`）。`nlp_common.ps1` 开头在 5.1 下把 `PSModulePath` 收窄回 5.1 的三个目录。
    - **`Set-Content -Encoding UTF8` 会写 BOM**（5.1），7 不会。空 stdin 文件必须用 `"" | Out-File -Encoding ascii -NoNewline`，否则校机读到的不是 EOF 而是 BOM。
15. **`Write-Host` 走信息流**：`$x = & helper.ps1 2>&1` 抓不到 `Write-Host` 的内容（它不进成功流）。要看日志得用 `*>&1`。曾经因此把"校机明明写成功了"判成失败。
16. **旧文件不能当新结果发布**：校机 `tmp\` 里上一轮的 `clip_out.txt` 还在时，一次失败的运行照样能把它拉回来，于是剪切板里出现的是上一次的结果。每次运行用带时间戳的唯一文件名，并且核对日志里校机自己打的 `wrote <路径>` 和 `=== exit code: 0 ===` 两行，两行缺一就当失败、绝不改剪切板。
17. **DP 返回的 span 是字符偏移，不是词下标**：`dp_segment` 给的是 `[a, b)` 的**字符位置**，单元文本按 `text[a:b]` 取。把它当词下标用（写成 `"".join(ws[a:b])`）会让输出全乱：双空格、汉字和西文粘在一起、标点跑到行首。**词层做任何"增删"（合并标点、丢掉标点）都会让字符偏移失效**——所以标点的增删必须发生在**切分之前的整段文本层面**，词层只做"不改长度的归位"（把标点并进相邻的词，文本长度不变）。
18. **标点要从文本里"换"成空格，不是删**：删掉会把两边的词焊成一个（`生词没有`）；换成空格就跟输入里已有的空白一个待遇，也保住了写者选定的边界。改完之后默认输出与人工去标点版**逐字节相同**，这是最好用的验收。
19. **标点归位是"切分之前"的一步，不是"切分之后"的一刀**：放在切分之后，标点会占掉一个单元（`，` 独占一格），长度带 [2,4] 也会被它带偏；放在切分之前，标点就成了词的一部分，模型还能从语料里学到 `“` 开头、`”` 收尾的单元（F1 0.7948 → 0.8095，往返 73.0% → 73.4%）。
20. **`.ps1` 里不能有中文**（本机和校机都一样）：Windows PowerShell 按 ANSI 读脚本，UTF-8 的中文会被读成乱码，**乱码里偶尔带引号或反引号就直接语法错**（`Unexpected token '}'`）。中文走 base64：脚本里 `[Convert]::FromBase64String(...)` 再用 UTF-8 解码。
21. **ssh 回显里的中文会花**：ssh 的转录由本机按代码页解码（GBK），校机吐的 UTF-8 中文会变成 `浠婂ぉ涔颁簡`。**中文不要走回显，用文件带回来**（写文件、pull 回来、按 UTF-8 读）。
22. **包要按目录同步，不能按单文件推**：`python -m nmud_style` 需要整个包目录连同 `data\`（语料与拟合参数）都在。`sync_package.ps1` 先问校机要每个文件的 md5，只推不一样的——源码没改就一个字节都不传。
23. **`sys.exit(字典)` 会把字典打到 stderr 并返回 1**：引擎的 `main()` 返回的是指标字典，入口必须把它转成整数（`return result if isinstance(result, int) else 0`），否则自检会误判成失败。
24. **`__pycache__` 不要推**：那是解释器的字节码缓存，每次运行都变；`sync_package.ps1` 直接跳过 `.pyc` 和 `__pycache__\`。
25. **沙箱里建不出虚拟环境**：`python -m venv` 的 ensurepip 子进程会被沙箱挡（`WinError 5`），`pip install --target` 也一样。**本机这条流水线不需要虚拟环境**——解释器在校机；`setup_env.py` 只是给"自己跑生成器"的设备用的，它有退回当前解释器的降级路径。

## 7. 文件清单

**校机项目根的 `tools\`**：`nmud.txt`、`nlp_paths.py`、`nmud_rules.py`、`generative_model.py`、`integrity.py`、`style_gen.py`、`demo*_plain.txt`，以及 **`nmud_style\` 包**（`__init__.py`、`__main__.py`、`cli.py`、`engine.py`、`envcheck.py`、`data\nmud.txt`、`data\nmud_style_params.json`）——本仓库 `nmud_style\` 同步过去的。

**校机项目根的 `out\`**：`nmud_rules.json`、`generative_model.json`、`nmud_style.json`、`style_gen.json`、`demo*_styled.txt`

**本仓库**（独立 git 仓库，不进主库历史）：

| 路径 | 说明 |
| --- | --- |
| `README.md` | 是什么、怎么装、怎么一键 |
| `SOP-nmud-style.md` | 本文 |
| `nmud_corpus_report.md` | 结论报告（§0–§7） |
| `nmud_style/` | 可安装的包：`engine.py`（引擎）、`cli.py`（命令行与剪切板）、`envcheck.py`（环境检测）、`data/`（语料与拟合参数） |
| `nmud-style.bat` | Windows 一键：剪切板 → 校机排版 → 写回剪切板 |
| `nmud-style.sh` | mac / Linux 一键（本机跑，pyperclip） |
| `setup-guest.bat` | 把校机装好：同步包 → 校机侧检测与安装 → 自检 |
| `setup_env.py` / `setup.sh` / `setup.bat` | 给自己跑生成器的设备：检测 + 装进 `.venv` + 自检 |
| `guest/` | 校机那套 SSH 流程（见 §2） |
| `checks/` | `check_report.py`（102 项校验，数字全部从 JSON 复算并与报告对账）、分析工具 `nmud_rules.py` / `generative_model.py` / `integrity.py` / `style_gen.py`、复算脚本 `voice_*.py` / `thin_space_*.py`、`nlp_paths.py`、`test_nlp_paths.py`、`scan_paths.py`、`debug_punct.py`，以及分析产出的 json |
| `examples/` | 四组示例输入输出 + `demo3_keep.txt`（`--keep-punct` 的输出） |
| `pyproject.toml` / `requirements.txt` | 打包（`pip install .` 得到 `nmud-style` 命令）与依赖 |

**校机项目根的 `tmp\`**：只放运行时临时件（`clip_in_*.txt` / `clip_out_*.txt` / `setup_env.ps1` / `_selftest_*.txt`），每次跑完自动删。

