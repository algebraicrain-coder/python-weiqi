# 项目日志（本地围棋程序）

## 1. 项目目标

在本地实现一个可以下围棋的程序。分阶段推进：先把规则内核和基础对弈界面做扎实、
可复用，之后再挂 AI 和图形界面。

## 2. 环境调研

- 开发环境：macOS + Python 3.14.2，使用 `python3`。
- 零第三方依赖；命令行界面不需要 Tkinter。
- 无 GNU Go / KataGo 等外部引擎（AI 留待后续）。

## 3. 方案选择记录

讨论过三种界面形态：

| 方案 | 内容 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| A. 命令行 | ASCII 棋盘 + 文本命令 | 代码少、复用性最高、便于测试和脚本化 | 观感朴素 | **先实现** |
| B. 桌面 GUI | Tkinter / PySide 窗口 | 单机体验好 | 本机缺 Tkinter，需额外安装 | 暂缓 |
| C. 浏览器 Web | Python 后端 + 网页棋盘 | 跨平台稳定、易分享 | 代码量最大 | 暂缓 |

AI 方案（后续阶段）：随机走子 → 蒙特卡洛（MC）→ MCTS/UCT →（可选）外部引擎 GTP。

**最终决策**：先做 A 方案（命令行），实现完整规则内核 + 双人对弈；AI 与图形界面后续再加。
棋盘默认 **19 路标准盘**；允许按需 `pip` 安装第三方库（当前阶段实际零依赖）。

## 4. 开发阶段与完成情况

- [x] 阶段 0：规则内核 + 命令行界面（完成）
- [x] 阶段 1：棋谱与管理 MVP（SGF 读写、元数据、保存/加载、单主线打谱回放）（完成）
- [x] 阶段 2：劫规则可选（四种，默认中国）（完成）
- [x] 阶段 3：浏览器图形界面（本次完成）
- [ ] 阶段 4：AI 对手（随机 → MC → MCTS）
- [ ] 阶段 5：棋谱进阶（变化图、注释、棋盘标记、棋谱库检索）
- [ ] 阶段 6：GTP 对接、日本规则数目法

### 图形界面阶段的取舍

- 本机 Homebrew Python 未编译 Tkinter，桌面 GUI 需额外安装，故选择**浏览器 Web 界面**。
- 为保持项目"零第三方依赖"原则，HTTP 服务用标准库 `http.server.ThreadingHTTPServer`，
  前端为内嵌单页 HTML/JS（Canvas 绘制），通过 JSON API 复用同一套 `Board`/`Game`/`GameRecord`，
  不引入 FastAPI/Flask。本地单浏览器对局无需 WebSocket/轮询，纯请求-响应即可。

### 界面美术（本次）

- 目标：在不引入任何前端依赖的前提下，把 Web 界面从"能用"提升到"好看、好用"。
- 棋盘：木纹渐变 + 细纹理 + 暗木外框；四周坐标（字母 A–T 跳过 I、行号自下而上）；
  星位随棋盘尺寸；高 DPI 下按 `devicePixelRatio`（上限 2）放大 canvas 内部分辨率。
- 棋子：径向渐变的立体黑/白子、投影与高光；最后一手红点；死子半透明 + 打叉；
  空交叉点悬停显示当前行棋方的半透明预落子。
- 布局：标题栏 + 状态卡（行棋方小圆点，终局显示半黑半白）+ 棋盘 + 卡片式控制面板；
  响应式（窄屏单列），按钮/输入框统一圆角、悬停与焦点态。
- 取舍：仍是单页内嵌 HTML/CSS/JS，`PAGE` 保持原始字符串；未引入字体/图标/前端框架。

### 棋谱阶段的范围取舍

就"棋谱与管理"讨论后确定的 MVP 范围：

- 存储格式：**SGF 为默认**（围棋事实标准，互通性最好），另支持**文本棋谱 `.txt`**
  （只读快照）；后缀决定格式，缺后缀补默认 `.sgf`。加载仅支持 SGF。
- 数据模型：新增 **树模型 `SGFNode`/`GameRecord`**，`Game` 保持线性用于实时对弈，
  两者可互转；为将来的变化图预留树结构。
- 本期不做：变化图的分支交互、注释/标记编辑、棋谱库索引、多格式导入。

## 5. 模块设计

| 模块 | 职责 | 关键接口 |
|---|---|---|
| `goban/board.py` | 规则内核：棋盘状态、气与棋组、提子、禁入点、可选劫规则、数子 | `Board.is_legal`、`Board.play`、`Board.play_unchecked`、`Board.pass_move`、`Board.undo`、`Board.score`、`Board._legal_ko`、`Board._record_position`、`KO_RULES`、`KO_RULE_LABELS`、`parse_vertex`、`format_vertex` |
| `goban/game.py` | 对局管理：落子历史、连续 pass 判定终局、认输、结果文本 | `Game.play`、`Game.pass_move`、`Game.undo`、`Game.resign`、`Game.result`、`Game.result_text` |
| `goban/player.py` | 玩家抽象：统一 `choose_move(game)` 接口，为 AI 预留 | `Player`、`HumanPlayer`、`Command`、常量 `RESIGN` |
| `goban/sgf.py` | SGF 词法/语法解析、序列化、坐标转换 | `SGFNode`、`parse_sgf`、`serialize_sgf`、`sgf_to_index`、`index_to_sgf` |
| `goban/record.py` | 棋谱模型：元数据、与 `Game` 互转、文件存取、回放步快照 | `GameRecord`（`from_game`/`to_game`/`save`/`load`/`steps`/`metadata`） |
| `goban/help.py` | 帮助注册表：命令与主题的缩略/详细信息，按阶段分组 | `Entry`、`resolve`、`summary_text`、`detail_text`、`overview_text`、`full_text`、`find` |
| `goban/web.py` | 浏览器图形界面：内置 HTTP 服务、单页前端（Canvas）、JSON API | `WebGame`（`dispatch`/`to_state`/`_do_*`）、`make_handler`、`run`、`main` |
| `goban/cli.py` | 命令行界面：对弈主循环、渲染、保存/加载、`view` 打谱 | `render_position`、`play_game`、`view_main`、`play_main`、`main` |
| `main.py` / `goban/__main__.py` | 程序入口 | `main()` |

## 6. 关键设计选择

- **棋盘表示**：一维 `list[int]`，`EMPTY=0, BLACK=1, WHITE=2`；坐标换算集中在
  `index`/`coord`，便于以后替换为更快的位棋盘（bitboard）而不影响上层。
- **行棋合法性顺序**：先落子并提掉无气的对方棋组，再检查己方是否无气（禁入点），
  最后检查是否重复历史局面（超级劫）。这一顺序与 Tromp-Taylor 规则一致。
- **劫争（后改为可选）**：最初固定为**位置超级劫**。后按用户需求改为**可选四种劫规则，
  默认中国规则**（位置超级劫，全局同形）：
  - `chinese`（默认）：位置超级劫，禁止任何整盘局面再现（维护 `_positions_grid`）。
  - `simple`：简单劫/单劫，只禁止立即回提（比较与上一手之前的局面）。
  - `situational`：情境超级劫，禁止轮到同一方时重复的局面（维护 `_positions_turn`）。
  - `japanese`：简单劫 + 循环重复（同局面同行棋方再现）判"无胜负"
    （`Board.no_result`），终局结算与 SGF `RE=Void`。
  - 判定集中在 `Board._legal_ko` 与 `Board._record_position`；`undo` 时按历史重建两组集合。
  - 选择入口：`--ko {chinese,simple,situational,japanese}`（默认 chinese）、设置模式
    `ko <规则>`；保存棋谱时把规则写为 `RU`（`KO_RULE_LABELS`）。
- **数子**：面积法（stones + 仅由单方围住的空点）+ 贴目。程序实现最直接，避免
  日本规则中死活判定带来的歧义；日本规则留待后续。
- **玩家接口**：`HumanPlayer` 通过回调 `move_source` 读取输入；将来 `AIPlayer`
  实现同一接口即可，CLI 与内核无需改动。
- **坐标系统**：标准围棋记谱，列字母 A–T 跳过 I，行号自下而上 1–19。
- **SGF 解析**：手写递归下降解析器，处理集合、游戏树、序列、节点、属性与转义
  （`\]`、`\\`）；序列化为标准括号/分号结构。支持一个文件内的多棵棋谱树
  （collection）。属性值允许空（`B[]` 表示停一手）。
- **坐标转换**：SGF 用 `a`–`z` 表示行列、从上往下数，本程序 `y` 从下往上数，
  转换集中在 `sgf_to_index`/`index_to_sgf` 两处，避免散落。
- **保存格式（后缀选择）**：`SAVE_FORMATS = ("sgf", "txt")`，`DEFAULT_FORMAT = "sgf"`。
  文件名后缀决定序列化方式（`record_format` → `GameRecord.serialize`），同目录
  `GameRecord.save(path)` 自洽；新增格式只需加一个后缀→序列化分支。CLI/Web 共用同一
  套 `resolve_write_path`/`save`，保证两端行为一致。
- **树模型 + 线性 Game**：`SGFNode` 是真正的棋谱树（可含变化），`Game` 仍只维护
  线性落子用于实时对弈；`GameRecord` 负责双向转换。线性 `Game` 不引入分支复杂度。
- **健壮回放**：为避免少数棋谱与位置超级劫判定冲突而中断，新增
  `Board.play_unchecked`，回放时跳过合法性检查但仍正确结算提子。
- **摆子支持**：`GameRecord` 识别根节点及后续节点的 `AB`/`AW`/`AE`/`PL`，
  支持让子局与死活题的基本加载。
- **死子处理（临时方案，已记录为不佳）**：面积法直接数盘面棋子，未提的死子会被
  错算成其己方的地。用户实测一份棋谱：死子留在盘上时"白胜 16.5"，移除死白子后
  变为"黑胜 1.5"，足以逆转胜负。当前采用**终局手动标记**：两次 pass 后进入
  counting phase，`dead <坐标>` 切换整块死活，`done` 后先移除死子再面积法数子，
  保存时用 `AE[...]` 记录。
  - **缺点（务必记住）**：依赖人工判读，易错；不适合 AI/自动对局。
  - **更优方向**：自动死活判定（Benson 无条件活、搜索或神经网络），或强制提净
    死子后结算。后续应替换本临时方案。
- **设置模式（用户需求）**：对弈与数子阶段可用特殊键 `set`（别名
  `settings`/`config`/`meta`/`@`）进入设置子模式，编辑对局元信息。字段用 SGF 属性名
  加常见别名（`black`→`PB` 等）；`komi`/`size` 特殊处理——`size` 仅在对局未开始时
  可改（有子后拒绝），`komi` 改动直接影响数子。改动写入 `metadata` 字典，保存时进入
  SGF。该子模式可复用同一 `reader/writer` 回调，便于测试与非交互驱动。
- **帮助系统（用户需求，含一次返工）**：说明原先分散，新增 `goban/help.py`
  结构化注册表，每条 `Entry` 含名称、别名、缩略摘要、详细说明、示例与"参见"。按阶段
  分组（play/view/counting/settings/cli/topic）。**首次尝试**把子模式命令整段塞进
  主模式的 `set` 条目，用户反馈效果不好。**改为分离**：主模式 `help set` 只简短指向
  子模式；设置模式/数子阶段各自拥有独立、详细的帮助条目（命令、字段、示例），
  进入子模式后 `help` 与 `help <名称>` 展示对应内容。上下文优先匹配同名命令
  （如 `done`/`show` 在多阶段含义不同）。`python3 main.py help [topic]` 同样可用。
- **图形界面（用户需求）**：新增 `goban/web.py` 浏览器界面。`WebGame` 用一把锁保护
  单一在内存对局，`dispatch(action, payload)` 统一处理 new/move/pass/undo/resign/
  dead/finish/settings/save/load，`to_state()` 输出前端所需的完整局面（含计数阶段、
  面积分、死子、元信息、消息）。`make_handler` 复用 `http.server` 提供 `/`（HTML）与
  `/api/*`（JSON）；命令/数子/设置共享 `merge_record_metadata` 等逻辑（已迁入
  `goban/record.py` 供 CLI 与 Web 复用）。启动入口 `python3 main.py web`。
  与 CLI 一样复用规则内核，界面层不含规则逻辑。

## 7. 测试

测试使用标准库 `unittest`，共 102 个用例，分七个文件：

`tests/test_board.py`（14 个）：

- 坐标解析与格式化（含跳过 I、越界报错）；
- 单子提取、活棋不误提、自杀非法；
- 劫：提子触发劫、回提非法、悔棋还原；
- 面积法数子（含贴目）、空盘数子；
- 对局：连续两 pass 终局、悔棋回退落子与 pass、认输结果。

`tests/test_sgf.py`（32 个）：

- SGF 解析：基本属性、空值表示 pass、转义、collection、未闭合值报错；
- 坐标转换：左上角、往返、pass 往返、越界报错；
- 序列化：结构往返、分支序列化、转义往返；
- 棋谱：`Game → SGF → Game` 手数/棋盘一致、含提子与 pass、元数据与结果、
  摆子 AB/PL、文件保存与加载；
- 回归：保存的 `RE` 与死子标记一致、含 `AE` 的棋谱不产生重复手数；
- 保存策略：裸文件名落入棋谱目录、子目录名保持、默认文件名、退出不误建文件、
  终局 `q` 不建文件、终局 `y` 保存默认文件；
- 保存格式：缺后缀补默认 `.sgf`、按格式补后缀、`record_format` 读后缀（含大写）、
  `default_filename` 尊重格式、`.txt` 文本棋谱内容、`serialize` 默认 SGF、未知后缀报错。

`tests/test_counting.py`（8 个）：

- `Board.score(dead=...)` 排除死子后黑白分变化正确；
- `Game.toggle_dead` 整块标记、再次切换复原、空点无效；
- 标记阶段：`dead B2`+`done` 生效、`undo` 回到行棋、裸坐标可切换；
- `Game.result` 反映死子移除后的分数变化。

`tests/test_ko.py`（11 个）：

- 四种规则均禁止立即回提；位置超级劫禁止任何重复局面而简单劫不查旧局面；
  情境超级劫只在同行棋方时禁止；日本规则检测循环并置 `no_result`、终局结算；
  默认 chinese、设置模式可切换、保存写入 `RU`。

`tests/test_settings.py`（11 个）：

- 设置字段与别名、`show`、`komi`、开局前改 `size`、有子后拒绝改尺寸、`del` 清字段、
  未知字段忽略；
- `set`/`@` 触发 settings 命令；
- 集成：设置模式写入的元信息最终出现在保存的 SGF（`PB[Alice]PW[Bob]`）；
- `merge_record_metadata` 保留已有字段、导入元信息、跳过 `SZ/KM/AP/RE`。

`tests/test_web.py`（12 个）：

- `WebGame.dispatch`：新局默认、落子换手、非法着给消息、两次 pass 进入数子、
  死子切换影响面积分、设置/保存/载入往返；
- HTTP：GET `/` 返回含 canvas 的 HTML、POST 新局/落子/非法坐标的消息；
- 保存格式：`format=txt` 与缺省名后缀、无后缀按格式补、未知后缀报错；
- 页面回归：内嵌 JS 的单引号按行配平（防 `\n` 被转义破坏字符串）；
  动作请求一律 POST、初始局面走 GET `/api/state`。

`tests/test_help.py`（14 个）：

- 缩略/详细查询：`resolve(None,"play")` 列出命令、`resolve("save","play")` 出详情、
  主题 `scoring`、上下文 `view`、同上下文优先匹配、未知主题提示、总览、全量详情；
- 分离验证：主模式 `help set` 只指向子模式；设置子模式有独立详细帮助
  （`resolve(None,"settings")` 含 komi/del，`resolve("komi","settings")` 出详情）；
  数子子模式同理；
- `help scoring` 触发带参数的 help 命令；
- `python3 main.py help [topic]` 子命令输出。

运行方式：

```bash
cd weiqi
python3 -m unittest discover -s tests -v
```

结果：`Ran 102 tests ... OK`。

## 8. 开发中修复的问题

1. **目录与包同名冲突**：项目根目录名为 `weiqi/`，内层 Python 包最初也叫 `weiqi`，
   导致从不同目录运行时 `import weiqi` 解析到不同对象，出现
   `No module named weiqi.__main__`。已将内层包改名为 `goban`，更新 `main.py`
   与测试导入。
2. **误用 `python`**：本机无 `python` 命令，统一说明改用 `python3`。
3. **直接改棋盘绕过超级劫追踪**：测试中直接写入 `board.grid` 会绕过 `_positions`，
   已在测试里显式重置 `_positions`；实际对局经 `play()` 不受影响；棋谱回放用
   `play_unchecked` 规避导入棋谱与超级劫的冲突。
4. **分支序列化预期修正**：`test_structure_roundtrip` 最初把 `len(children)==3`
   的期望挂错节点，实际分支点在 `;W[dd]` 上，修正断言后通过。
5. **命令参数大小写**：CLI 命令解析只对动词小写化，保留 `save/load` 的文件名原样，
   避免大小写敏感的文件名被破坏。
6. **退出时误建文件（用户反馈）**：终局后的保存提示把任何输入都当成文件名，
   用户输入 `q` 想退出时会在当前目录生成一个名为 `q` 的文件。改为显式询问
   `Save the game? [y/N]`，`n`/回车/`q` 均不保存；并支持输入 `y` 后用默认文件名。
7. **棋谱保存位置分散**：原先默认存到当前工作目录。现统一到 `weiqi/records/`，
   裸文件名解析进该目录，支持 `--record-dir` 覆盖，并自动创建目录。
8. **未提死子被误算（用户反馈）**：用户提供棋谱终局有未提的死白子，面积法把死子
   算作其己方地，实测可把"黑胜 1.5"错判为"白胜 16.5"。新增终局标记死子阶段
   （`dead`/`done`/`undo`）与 `Board.score(dead=...)`，保存时以 `AE` 记录。

### 代码复查（自查发现并修复）

9. **保存的 `RE` 忽略死子**：`record._result_code` 用 `game.board.score()` 而非
   `game.score()`，导致标记死子后"显示结果"与"存入 SGF 的 `RE`"不一致
   （实测显示黑胜 24.5，存成 B+2.5）。改为 `game.score()`。
10. **载入棋谱丢失元信息**：`load` / `--load` 只导入着法，未导入元信息，重新保存会丢
    `PB/PW/EV/DT` 等。新增 `merge_record_metadata`，载入时并入（跳过由盘面决定的
    `SZ/KM`、生成器 `AP`、以及应由终局重算的 `RE`），且不覆盖命令行已给的字段。
11. **打谱出现重复手数**：含 `AE` 的棋谱在 `steps()` 里多出一个同手数的局面。改为把
   纯摆子节点（如 `AE`）并回上一步，不再产生重复序号。
12. **帮助查找遗漏**：`set` 的别名 `options` 在命令里可用但帮助里缺失；字段名
   （`event`/`date`/`rules` 等）无法直接 `help`。已补上别名字段。
13. **清理**：移除 `player.py` 中未使用的 `PASS` 导入。

### 图形界面上线后（用户反馈）

14. **界面卡在「加载中…」、棋盘空白**：用户截图显示棋盘只画出背景木色、状态一直
    停在「加载中…」且「标记死子/完成数子」按钮未隐藏。用无头 Chrome
    (`--headless=new --dump-dom`) 复现并抓控制台，得到
    `Uncaught SyntaxError: Invalid or unexpected token`（页面第 171 行）——整段
    `<script>` 解析失败，因此 `render()` 从未执行（按钮的隐藏逻辑也在 `render()` 里）。
    根因：`PAGE` 是**非原始**三引号字符串，内嵌 JS 里 `'\n'` 被 Python 先转成**真实换行**，
    于是变成跨行的单引号字符串（`'局面循环：无胜负<换行>'`）。
    修复：把 `PAGE` 改为原始字符串 `r"""…"""`，保留 JS 的 `\n` 转义。
    新增回归测试 `test_page_js_strings_are_not_split_by_newlines`（按行检查单引号配平），
    在修复前会失败、修复后通过。教训：`curl` 只验证了 HTML/JSON 可达，
    无法发现 JS 语法错误，Web 改动需真机/无头浏览器渲染自检。
15. **点「停一手/悔棋/认输」报错（用户反馈）**：落子正常，但这三个按钮（以及
    「完成数子」）无参数调用 `api('/api/pass')`，而 `api()` 在无 `payload` 时发的是
    **GET**；这些动作端点只处理 POST，于是返回 404 JSON，`render()` 随即抛错、界面不动。
    落子因带 `{vertex}` 走 POST 所以正常。修复：`api(path, payload = {})` **一律 POST**，
    初始局面改用独立的 `loadState()` 走 GET `/api/state`。已用 Node 复跑页面脚本、
    真实点击三个按钮验证：pass 换手、undo 回退、resign 判负，且动作端点无 GET。
    新增回归测试 `test_page_actions_use_post_and_state_uses_get`。
16. **保存棋谱默认补后缀、后缀可选（用户需求）**：原先裸文件名 `save game` 会存成
    无扩展名的文件。现**缺后缀自动补 `.sgf`**，并用后缀**选择格式**：`.sgf`（标准，
    可回放）、`.txt`（文本棋谱，元信息 + 着法列表，仅可读）。实现：`record.py` 新增
    `SAVE_FORMATS`/`DEFAULT_FORMAT`、`record_format`、`GameRecord.to_text/serialize`，
    `resolve_write_path`/`default_filename` 支持 `default_format`；`save()` 按路径后缀
    推断格式，未知后缀抛 `ValueError`。CLI 的 `save`/退出保存沿用后缀选择并捕获该错误；
    Web「棋谱」栏加后缀下拉框，`/api/save` 收 `format`。加载仍仅支持 SGF。
17. **网页棋盘上下颠倒（美术阶段发现）**：`drawStones` 把 `y=0` 画在顶部，而
    `parse_vertex`/CLI 约定 `y=0` 是第 1 行（底部），导致同一坐标在网页与命令行
    位置相反、坐标标签也会错。新增 `toScreen()` 统一 `sy = size-1-y`，点击反算
    `y = size-1-sy`；用 Node 驱动真实页面验证：点左下角发送 `A1`、点右上角发送 `J9`。
18. **README 截图改用公有领域棋谱（用户反馈）**：原先截图用的是临时自拟布局，观感
    不像真实对局，也无法说明来源。现改用 1846 年「耳赤之局」（本因坊秀策 vs 井上
    幻庵因硕）前 25 手的大斜定式；历史棋谱属公有领域。截图同时写入黑/白方、赛事、
    日期与贴目 0；开局存为 `docs/ear-reddening-opening.sgf` 便于复现，README 注明
    Wikipedia 来源。GitHub 对同 URL 图片有缓存，故把截图改名为
    `docs/screenshot-ear-reddening.png` 以强制使用新的图片 URL。
19. **接入可选 KataGo AI（用户需求）**：核心保持零依赖，新增 `goban/ai/`：
    `AIConfig` 按 CLI > 环境变量 > `ai.json` > PATH/Homebrew 的顺序发现；
    `KataGoGTP` 用子进程说 GTP，处理空行响应、stderr 排空、超时杀进程，
    每手用 `clear_board` + 重放着法同步局面；`Position` 快照让网页可在锁外调用引擎，
    回来再校验局面是否被改动。CLI 增加 `--ai/--ai-color/--ai-visits` 等，
    网页增加 `/api/ai` 与「AI 落子」按钮；找不到引擎/模型时降级提示。
    规则映射：`chinese`→`chinese-ogs`、`simple`→`chinese`、`situational`→`aga`、
    `japanese`→`japanese`。带 SGF 摆子（AB/AW）时改用 `set_position` 还原盘面
    （会丢手顺/劫，属于回退方案）。新增 20 个测试（`test_ai` 11、`test_web_ai` 9），
    全部用 fake GTP 脚本，CI 不需要安装 KataGo；总计 122 个测试。
    README 增加安装/配置/强度/体积/许可证说明，`ai.json` 与 `models/` 忽略。
20. **KataGo 真机验证（用户要求）**：`brew install katago` 安装 1.18.2_2
    （Metal 后端，368.8 MB，含 b18/b20/b40 三个网络）；自动发现
    `/opt/homebrew/bin/katago`、b18 模型与 `gtp_example.cfg`。19 路空盘 300 visits
    首手为 Q16，单步约 2–3 秒；CLI `--ai` 实测正常。随后与 KataGo 下了一局 19 路
    （我执黑、简单人类策略，白方 300 visits），第 60 手黑棋认输，结果 W+R；棋谱保存在
    `records/19x19-vs-katago.sgf`（`records/` 已忽略，不进入仓库）。
21. **实时分析（用户需求）**：新增 `goban/ai/analysis.py`，用 `katago analysis` 的 JSON
    流实现实时分析：`Analysis`/`MoveEval` 数据模型、`KataGoAnalysis` 解析
    `moveInfos/rootInfo/ownership`，`reportDuringSearchEvery=0.2` 持续推送中间结果；
    `AnalysisService` 在后台线程按局面 key 分析，走子时取消旧查询。网页增加
    `GET /api/analysis`、`analysis` 动作和「AI 分析」卡片：黑方胜率、目差、前 6 候选点
    与棋盘 ownership 叠加，前端每 250ms 拉取快照。分析进程与落子引擎分离。
    新增 8 个测试（`test_analysis.py`），总计 130 个；测试全部用 fake analyzer。
    修复 `Analysis.key`（SHA1）与网页 `current_key`（原为 tuple）类型不一致的问题，
    避免旧分析结果画到新棋盘。实测 19 路空盘约 2 秒出中间结果、5 秒左右完成 300 visits。

## 计分规则（用户提问澄清）

- 当前实现是**面积法**，等价于现代**中国规则**数子：得分 = 己方棋子 + 仅被己方
  围住的空点；白方加贴目。
- 不是日本规则（地 + 提子）；两者多数局面结果相同，边界（劫/双活）有别。
- 未实现"还棋头"。
- **劫规则可选**：默认中国规则（位置超级劫），另含简单劫、情境超级劫、日本规则；
  见第 6 节"劫争（后改为可选）"与 `goban/board.py` 的 `KO_RULES`。
- 死活处理：当前用**终局手动标记**（临时方案，见第 6 节，已注明并不理想），
  仍未做自动死活判定。

## 9. 运行环境备忘

- 对弈入口：`python3 main.py`（默认 19 路、贴目 7.5），或 `python3 -m goban`。
- 劫规则：`--ko {chinese,simple,situational,japanese}`（默认 chinese），或设置模式 `ko`。
- 打谱入口：`python3 main.py view <file.sgf>`。
- 图形界面入口：`python3 main.py web [--port N --no-open]`。
- 棋谱默认目录：`weiqi/records/`，可用 `--record-dir` 更改。
- 依赖：仅标准库，无需 venv、无需安装。
- 已完成：KataGo GTP 可选 AI（第 19 条）与实时分析（第 21 条）；棋谱侧仍可做变化图、
  注释/标记与棋谱库检索。
- 下一步：整局复盘（analysis `analyzeTurns`）与胜率曲线、human SL 强度档位、
  首次运行下载脚本；核心 MCTS 仍可作为无外部依赖的轻量后备。
