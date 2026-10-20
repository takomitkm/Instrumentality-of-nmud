# nmud-style

把中文文本排成 **nmud 论坛那套写法**：词被切成短单元，单元之间一个空格，一行放两到四个单元。

不是"随机断行"，也不是"每行固定字数"——是把**语料里那位作者的切分习惯**学出来再套上去：切点跟着语义块走，标点按他本人的用法处理（只留 `…？！""`，句号逗号一律不出现，标点贴在词上不占一格）。

```text
输入：今天买了个新玩具，蓝色的，会发光，匀速的shake shake。
输出：今天买了 个新玩具
      蓝色的 会发光
      匀速的 shake shake
```

## 一键：剪切板进，nmud 语出，再写回剪切板

| 平台 | 双击 / 执行 | 在哪台机器上算 |
| --- | --- | --- |
| Windows（本机） | `nmud-style.bat` | **校机**：源码推过去算，结果拉回来 |
| macOS / Linux | `./nmud-style.sh` | 本机（先 `./setup.sh`） |

复制一段中文 → 双击 → 剪切板里已经是排好版的 nmud 语。就这一步。

**这台 Windows 机器上不装任何环境**：解释器、jieba、语料、拟合参数全在校机（`school-guest`），本仓库只留源码。

## 第一次：把校机装好

```powershell
setup-guest.bat
```

它会：把 `nmud_style/` 包同步到校机 → 在**校机那边**检测缺什么（虚拟环境、jieba、包里的语料与拟合参数）→ 缺什么装什么 → 跑一句自检证明真的能用。

```text
=== nmud-style environment check ===
machine : <hostname>
root    : <校机>
need    : the virtual environment  ok
need    : jieba  ok
need    : the corpus  ok
need    : the fitted params  ok
result  : ready, the guest can restyle text
```

**在一台自己跑生成器的机器上**（比如 mac、Linux，或者哪台 Windows 想本地跑）用另一个入口：

```powershell
python setup_env.py      # 任何平台：检测 + 装进本仓库的 .venv + 自检
./setup.sh               # mac / Linux 的包装
```

只检测不安装：`python setup_env.py --check`。国内网络连不上 PyPI 时：`python setup_env.py --proxy 127.0.0.1:7897`（脚本依次试 PyPI、清华源、阿里源和本机代理）。

## 命令行

```powershell
nmud-style --clip                 # 剪切板 -> nmud -> 剪切板
nmud-style --in a.txt --out b.txt # 文件
nmud-style --demo                 # 内置例子
nmud-style --check-env            # 当前设备缺什么
nmud-style --refit --report       # 重新拟合模型并写出指标 json
```

装成命令（任何平台）：

```powershell
pip install .
```

没装成命令时，在仓库根目录 `python -m nmud_style --clip` 一样能用。

## 这个仓库里有什么

| 路径 | 内容 |
| --- | --- |
| `nmud_style/` | 可安装的包：引擎、命令行、语料与拟合参数（`data/`） |
| `SOP-nmud-style.md` | 完整可复现的流程：分析、拟合、生成、验收、踩过的坑 |
| `nmud_corpus_report.md` | 语料分析报告（§0–§7）：规律是怎么测出来的 |
| `examples/` | 四组示例输入输出，外加一份 `--keep-punct` 的输出 |
| `checks/` | 复算报告数字的脚本（`check_report.py` 102 项校验）和分析工具 |
| `guest/` | 校机那套 SSH 流程：同步包、跑包、校机侧的环境检测与安装 |

## 效果有多准

| 指标 | 值 |
| --- | --- |
| 留出 F1（两折合并） | 0.8095（P 0.7992 / R 0.8200） |
| 往返（删掉作者空格再切，逐字一致） | 367/500 = 73.4% |
| 基线（每个词都切）F1 | 0.5065 |

细节和读数来源见 [报告](nmud_corpus_report.md)；复现步骤见 [SOP](SOP-nmud-style.md)。

## 注意

- 这些比率描述的是**一位作者**的写法（单个 5 KB 文档）。语料也可能是多人论坛帖（xyn、清蒸协会、反跨），不是纯一人语料。
- jieba 不认识互联网词汇（`nmud`、`yyds` 之类），会切错；切分靠词边界对齐，词切错边界就跟着错。
- 排版学得到，**内容学不了**：这是排版器，不是写作助手。
- 语料文件按原始字节保存（CRLF，5087 字节）：报告里引用的字节数与行尾数是它的证据。
