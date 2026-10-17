from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    name: str
    summary: str
    context: str
    aliases: tuple[str, ...] = ()
    detail: str = ""
    examples: tuple[str, ...] = ()
    see_also: tuple[str, ...] = ()


CONTEXT_TITLES = {
    "play": "对弈命令 (game)",
    "view": "打谱命令 (view)",
    "counting": "数子阶段 (counting)",
    "settings": "设置模式 (settings)",
    "cli": "命令行选项 (command line)",
    "topic": "主题说明 (topics)",
}

CONTEXT_ORDER = ["play", "view", "counting", "settings", "cli", "topic"]

CONTEXT_INTRO = {
    "play": "对弈主模式。落子、停手、悔棋、存取棋谱、进出设置模式等。",
    "view": "打谱回放模式（python3 main.py view FILE）。逐手浏览一份棋谱。",
    "counting": (
        "数子阶段：两次 pass 后自动进入。面积法会把未提的死子算错，故需在此手动标记死子，"
        "再结算。输入 help <名称> 查看各命令详情。"
    ),
    "settings": (
        "设置模式（对弈/数子中输入 set 进入）：编辑对局元信息，改动会写入保存的 SGF。"
        "命令：show 列出全部；<字段> <值> 写入；<字段> 查看；komi/size/ko 修改贴目、盘面与劫规则；"
        "del 清除；done 返回。输入 help <名称> 查看详情。"
    ),
    "cli": "启动程序的命令行选项与子命令。",
    "topic": "功能主题说明：坐标、规则、计分、SGF、棋谱目录等。",
}


ENTRIES: list[Entry] = [
    Entry(
        "D4 / Q16",
        "在交叉点落子",
        "play",
        aliases=("move",),
        detail=(
            "输入一个坐标即落子。列用字母 A–T 但跳过 I，行号从棋盘底部向上为 1–19，"
            "大小写均可。非法着（占位、自杀、劫/超级劫）会被拒绝并提示。"
        ),
        examples=("D4", "Q16", "p16"),
    ),
    Entry(
        "pass",
        "停一手；连续两次 pass 进入数子阶段",
        "play",
        aliases=("p",),
        detail="停一手不移除任何棋子。双方连续停手表示对局结束，进入终局数子。",
        examples=("pass", "p"),
    ),
    Entry(
        "undo",
        "悔棋，撤销最后一手（含 pass）",
        "play",
        aliases=("u",),
        detail="撤销最近一手并恢复轮次、提子数与劫争状态。",
    ),
    Entry(
        "resign",
        "认输，对方获胜",
        "play",
        aliases=("r",),
        detail="当前轮次一方认输，对局直接结束（不进入数子）。",
    ),
    Entry(
        "save",
        "保存棋谱（无参数则自动命名）",
        "play",
        aliases=(),
        detail=(
            "把当前对局写成棋谱。无参数时自动命名、默认 .sgf 存入棋谱目录；"
            "文件名不含后缀时自动补 .sgf。文件名不含目录时存入棋谱目录，"
            "含子目录或绝对路径则按原路径。后缀决定格式：.sgf（标准 SGF，可回放）、"
            ".txt（文本棋谱，元信息 + 着法列表，仅可读）。"
        ),
        examples=("save", "save mygame.sgf", "save mygame.txt", "save sub/a.sgf"),
        see_also=("records", "sgf"),
    ),
    Entry(
        "load",
        "载入 SGF 并替换当前对局",
        "play",
        aliases=(),
        detail="读取一份 SGF，重放其主分支作为当前对局，可继续落子。文件名先在棋谱目录查找，再按相对路径查找。",
        examples=("load game.sgf",),
        see_also=("sgf", "records"),
    ),
    Entry(
        "set",
        "进入设置模式（子模式）",
        "play",
        aliases=("settings", "config", "meta", "options", "@"),
        detail=(
            "进入设置模式以编辑对局元信息。设置模式有自己的一套命令与帮助："
            "进入后输入 help 查看全部，help <名称> 查看详情。"
        ),
        examples=("set",),
        see_also=("settings",),
    ),
    Entry(
        "show",
        "重新绘制棋盘",
        "play",
        aliases=("s", "board"),
        detail="清屏无关，仅重新打印当前棋盘、轮次、提子数与最后一手。",
    ),
    Entry(
        "help",
        "显示帮助；`help <命令或主题>` 看详情",
        "play",
        aliases=("h", "?"),
        detail="不带参数列出全部命令的缩略信息；带参数显示某命令或主题的详细信息；`help all` 输出全部。",
        examples=("help", "help scoring", "help save", "help all"),
    ),
    Entry(
        "quit",
        "退出对局（会询问是否保存）",
        "play",
        aliases=("q", "exit"),
        detail="若已有棋子则先询问是否保存棋谱，然后退出；没有棋子则直接退出。",
    ),
    Entry(
        "next",
        "打谱：下一手",
        "view",
        aliases=("n", ">"),
        detail="在回放模式中前进一手。",
    ),
    Entry(
        "prev",
        "打谱：上一手",
        "view",
        aliases=("p", "<"),
        detail="在回放模式中后退一手。",
    ),
    Entry(
        "first",
        "打谱：跳到开局",
        "view",
        aliases=("f", "start"),
    ),
    Entry(
        "last",
        "打谱：跳到末尾",
        "view",
        aliases=("l", "end"),
    ),
    Entry(
        "goto",
        "打谱：跳到第 N 手",
        "view",
        detail="直接输入数字即可，例如输入 42 跳到第 42 手；手数与局面序号一致。",
        examples=("42",),
    ),
    Entry(
        "auto",
        "打谱：从当前自动播放到结束",
        "view",
        aliases=("a",),
        detail="按 --delay 指定的间隔（默认 1 秒）自动播放剩余手数。",
    ),
    Entry(
        "info",
        "打谱：显示 SGF 元数据与手数",
        "view",
        aliases=("i",),
    ),
    Entry(
        "dead",
        "数子：把某点所在的整块棋标记为死子（可切换）",
        "counting",
        aliases=("mark", "d"),
        detail=(
            "对 `<坐标>` 所在的整块棋整体切换死/活：第一次标记为死子，再输入一次取消。"
            "被标记的死子以小写显示（x=死黑，o=死白）。也可直接输入坐标（如 B6）。"
            "结算时会先移除所有被标记的死子，再按面积法数子。"
        ),
        examples=("dead D4", "B6", "dead B6"),
        see_also=("scoring",),
    ),
    Entry(
        "done",
        "数子：移除死子并结算",
        "counting",
        aliases=("count", "finish", "ok"),
        detail=(
            "结束死子标记，移除所有被标记的死子后按面积法计算胜负，随后进入保存询问。"
        ),
        examples=("done",),
    ),
    Entry(
        "undo",
        "数子：退回行棋（撤销最后一次 pass）",
        "counting",
        aliases=("u", "resume"),
        detail="撤销导致终局的最后一次 pass，回到行棋继续下，同时清除死子标记。",
        examples=("undo",),
    ),
    Entry(
        "show",
        "数子：重画当前盘面",
        "counting",
        aliases=("s", "board"),
        detail="重新打印盘面；已标记的死子仍以小写显示。",
        examples=("show",),
    ),
    Entry(
        "set",
        "数子：进入设置模式",
        "counting",
        aliases=("settings", "config", "meta"),
        detail="在数子阶段也可编辑元信息（如补填棋手、赛事）。命令与对弈阶段相同。",
        examples=("set",),
        see_also=("settings",),
    ),
    Entry(
        "help",
        "数子：查看本阶段帮助",
        "counting",
        aliases=("h", "?"),
        detail="`help` 列出数子阶段全部命令；`help <名称>` 查看某命令详情。",
        examples=("help", "help scoring"),
    ),
    Entry(
        "quit",
        "数子：退出（会询问是否保存）",
        "counting",
        aliases=("q", "exit"),
        detail="离开程序；若有棋子会先询问是否保存棋谱。",
        examples=("quit",),
    ),
    Entry(
        "show",
        "设置：列出全部元信息",
        "settings",
        aliases=("list", "ls", "s", "info"),
        detail=(
            "显示棋盘大小、贴目，以及所有可编辑字段的当前值；未设置的字段显示 (unset)。"
        ),
        examples=("show",),
    ),
    Entry(
        "<字段> <值>",
        "设置：写入某字段，如 PB Alice",
        "settings",
        aliases=(
            "set",
            "black",
            "white",
            "rank",
            "date",
            "event",
            "round",
            "place",
            "rules",
            "result",
            "handicap",
            "name",
            "comment",
        ),
        detail=(
            "第一个词是字段、其余是值，例如 `PB Alice`、`event Club Cup`。\n"
            "字段名可用 SGF 属性名或其别名：black→PB、white→PW、black-rank→BR、"
            "white-rank→WR、date→DT、event→EV、round→RO、place→PC、rules→RU、"
            "result→RE、handicap→HA、name→GN、comment→GC。\n"
            "只输入 `<字段>` 则显示该字段当前值（不修改）。"
        ),
        examples=("PB Alice", "white Bob", "event Club Cup", "date 2026-10-06"),
        see_also=("fields",),
    ),
    Entry(
        "fields",
        "设置：可编辑字段一览",
        "settings",
        detail=(
            "元信息字段（SGF 属性名 / 别名）：\n"
            "  PB / black        黑方棋手\n"
            "  PW / white        白方棋手\n"
            "  BR / black-rank   黑方段位\n"
            "  WR / white-rank   白方段位\n"
            "  DT / date         对局日期（YYYY-MM-DD）\n"
            "  EV / event        赛事名称\n"
            "  RO / round        轮次\n"
            "  PC / place        地点\n"
            "  RU / rules        规则\n"
            "  RE / result       结果（通常自动写入）\n"
            "  HA / handicap     让子数\n"
            "  GN / name         棋谱名\n"
            "  GC / comment      备注"
        ),
        examples=("PB Alice", "date 2026-10-06"),
    ),
    Entry(
        "komi",
        "设置：修改贴目",
        "settings",
        aliases=("KM",),
        detail=(
            "设置白方贴目（实数），立即影响数子结果。不带参数时显示当前贴目。"
        ),
        examples=("komi 6.5", "komi"),
    ),
    Entry(
        "size",
        "设置：修改棋盘大小（仅开局前）",
        "settings",
        aliases=("SZ",),
        detail=(
            "设置棋盘大小（2–25 路）。仅在对局尚未落子时允许；一旦有棋子会拒绝。"
            "不带参数时显示当前大小。"
        ),
        examples=("size 13", "size"),
    ),
    Entry(
        "ko",
        "设置：修改劫规则",
        "settings",
        detail=(
            "设置劫争规则，影响后续着手的合法性。可选 chinese（默认，位置超级劫）、"
            "simple（简单劫）、situational（情境超级劫）、japanese（简单劫 + 循环判无胜负）。"
            "不带参数时显示当前规则。"
        ),
        examples=("ko simple", "ko"),
        see_also=("ko-rules",),
    ),
    Entry(
        "del",
        "设置：清除某字段",
        "settings",
        aliases=("clear", "unset", "rm"),
        detail="移除某字段，使其在保存的 SGF 中不再出现。贴目与盘面大小不可清除。",
        examples=("del PB", "del comment"),
    ),
    Entry(
        "done",
        "设置：返回对局",
        "settings",
        aliases=("ok", "return", "exit", "q"),
        detail="退出设置模式回到对局；已做的修改保留，并在保存时写入 SGF。",
        examples=("done",),
    ),
    Entry(
        "help",
        "设置：查看本模式帮助",
        "settings",
        aliases=("h", "?"),
        detail="`help` 列出设置模式全部命令；`help <名称>` 查看某命令详情。",
        examples=("help", "help komi"),
    ),
    Entry(
        "--size N",
        "命令行：棋盘大小（默认 19）",
        "cli",
        examples=("python3 main.py --size 9",),
    ),
    Entry(
        "--komi X",
        "命令行：白方贴目（默认 7.5）",
        "cli",
        examples=("python3 main.py --komi 6.5",),
    ),
    Entry(
        "--ko RULE",
        "命令行：劫规则（默认 chinese）",
        "cli",
        detail="RULE 可选 chinese / simple / situational / japanese。",
        examples=("python3 main.py --ko simple",),
        see_also=("ko-rules",),
    ),
    Entry(
        "--load FILE",
        "命令行：启动即载入 SGF",
        "cli",
    ),
    Entry(
        "--record-dir DIR",
        "命令行：棋谱保存目录",
        "cli",
    ),
    Entry(
        "--black / --white NAME",
        "命令行：棋手名，写入 PB/PW",
        "cli",
        examples=("python3 main.py --black Alice --white Bob",),
    ),
    Entry(
        "--event / --rules / --date",
        "命令行：赛事 / 规则 / 日期（EV/RU/DT）",
        "cli",
    ),
    Entry(
        "view FILE",
        "子命令：打谱回放",
        "cli",
        examples=("python3 main.py view game.sgf --delay 0.5",),
    ),
    Entry(
        "web",
        "子命令：在浏览器打开图形界面",
        "cli",
        detail=(
            "启动本地 HTTP 服务器并在浏览器打开棋盘界面（纯标准库，无第三方依赖）。"
            "点击落子，按钮停一手/悔棋/认输/标记死子/完成数子/新局/存取棋谱/改元信息。"
            "选项：--host/--port/--record-dir/--no-open。"
        ),
        examples=("python3 main.py web", "python3 main.py web --port 9000 --no-open"),
    ),
    Entry(
        "help [topic]",
        "子命令：查看帮助",
        "cli",
        examples=("python3 main.py help", "python3 main.py help scoring"),
    ),
    Entry(
        "coordinates",
        "坐标系统：棋盘显示与 SGF 的差异",
        "topic",
        detail=(
            "本程序显示用字母 A–T 跳过 I、行号自下而上 1–19；SGF 用两个小写字母"
            "（a 为最左/最上，从上往下数），空值 [] 表示 pass。加载/保存时自动转换。"
        ),
    ),
    Entry(
        "rules",
        "规则：合法性与劫争",
        "topic",
        detail=(
            "合法落子需满足：交叉点为空、落子后己方有气（禁入点/自杀非法）、"
            "且满足所选劫争规则。提子先移除对方无气之子，再判己方是否有气。"
            "劫规则默认中国规则（位置超级劫），可选，见 help ko-rules。"
        ),
        see_also=("ko-rules",),
    ),
    Entry(
        "ko-rules",
        "劫争规则：四种可选，默认中国规则",
        "topic",
        aliases=("ko", "superko"),
        detail=(
            "chinese（默认）：位置超级劫，禁止任何整盘局面再现（中国规则全局同形）。\n"
            "simple：简单劫/单劫，只禁止立即回提使局面回到上一手之前。\n"
            "situational：情境超级劫，禁止轮到同一方时重复的局面。\n"
            "japanese：简单劫 + 三劫/长生等循环重复判“无胜负”。\n"
            "用 --ko 或设置模式 ko <规则> 切换。"
        ),
        see_also=("--ko RULE", "ko"),
    ),
    Entry(
        "scoring",
        "计分：面积法（中国规则）与死子处理",
        "topic",
        detail=(
            "采用面积法（等价现代中国规则数子）：得分 = 己方棋子 + 仅被己方围住的空点，"
            "白方加贴目。不是日本规则（地+提子）。未提的死子会被错算，故两次 pass 后"
            "进入数子阶段用 dead 标记死子；这是临时方案，依赖人工判读，后续应改为自动判死活。"
        ),
    ),
    Entry(
        "sgf",
        "SGF：棋谱格式与坐标",
        "topic",
        detail=(
            "支持 SGF FF[4] 的解析与生成：集合、游戏树、分支、转义、属性值（空值=pass）。"
            "保存时写入 GM/FF/CA/AP/SZ/KM 及 PB/PW/EV/RU/DT/RE；死子用 AE 记录。"
        ),
    ),
    Entry(
        "records",
        "棋谱目录与命名",
        "topic",
        detail=(
            "默认目录为项目内 records/，可用 --record-dir 更改。自动命名为"
            "`日期时间_黑方_vs_白方.sgf`（可用后缀选择格式，见 help save）。"
            "裸文件名解析进棋谱目录，含目录则按原路径。"
        ),
    ),
    Entry(
        "limitations",
        "已知限制",
        "topic",
        detail=(
            "无自动死活判定（数子靠人工标记死子）；无日本规则；无 AI；棋盘上限 25 路；"
            "变化图尚未提供交互式进入。"
        ),
    ),
]


def _matches(entry: Entry, key: str) -> bool:
    return key == entry.name.lower() or key in (alias.lower() for alias in entry.aliases)


def find(name: str, context: str | None = None) -> Entry | None:
    key = name.strip().lstrip("-").lower()
    if not key:
        return None
    if context:
        for entry in ENTRIES:
            if entry.context == context and _matches(entry, key):
                return entry
    for entry in ENTRIES:
        if _matches(entry, key):
            return entry
    return None


def summary_text(context: str) -> str:
    title = CONTEXT_TITLES.get(context, context)
    lines = [f"{title}  —  'help <名称>' 查看详细信息，'help all' 查看全部"]
    intro = CONTEXT_INTRO.get(context)
    if intro:
        lines.append(intro)
    for entry in ENTRIES:
        if entry.context != context:
            continue
        alias = f" ({', '.join(entry.aliases)})" if entry.aliases else ""
        lines.append(f"  {entry.name}{alias}: {entry.summary}")
    return "\n".join(lines)


def detail_text(entry: Entry) -> str:
    lines = [f"{entry.name} — {entry.summary}"]
    if entry.aliases:
        lines.append(f"别名: {', '.join(entry.aliases)}")
    if entry.detail:
        lines.append(entry.detail)
    if entry.examples:
        lines.append("示例:")
        lines.extend(f"  {example}" for example in entry.examples)
    if entry.see_also:
        lines.append(f"参见: {', '.join(f'help {name}' for name in entry.see_also)}")
    return "\n".join(lines)


def overview_text() -> str:
    blocks = [summary_text(context) for context in CONTEXT_ORDER]
    return "\n\n".join(blocks)


def full_text() -> str:
    blocks = [overview_text()]
    for context in CONTEXT_ORDER:
        for entry in ENTRIES:
            if entry.context == context:
                blocks.append(detail_text(entry))
    return "\n\n".join(blocks)


def resolve(topic: str | None, context: str | None = None) -> str:
    if topic is None or topic.strip() == "":
        if context:
            return summary_text(context)
        return overview_text()
    key = topic.strip().lower()
    if key in ("all", "full", "everything"):
        return full_text()
    if key in CONTEXT_TITLES:
        return summary_text(key)
    entry = find(topic, context)
    if entry is not None:
        return detail_text(entry)
    return f"没有关于 {topic!r} 的帮助；试试 'help' 或 'help all'。"
