from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import help as helpmod
from .ai import (
    EngineError,
    EnginePlayer,
    KataGoGTP,
    add_cli_arguments,
    discover_config,
    overrides_from_args,
)
from .board import (
    BLACK,
    COLUMNS,
    EMPTY,
    KO_CHINESE,
    KO_RULES,
    PASS,
    WHITE,
    Board,
    IllegalMove,
    color_name,
    format_vertex,
    parse_vertex,
)
from .game import Game
from .player import RESIGN, Command, HumanPlayer
from .record import (
    META_KEYS,
    GameRecord,
    default_filename,
    default_record_dir,
    merge_record_metadata,
    resolve_read_path,
    resolve_write_path,
)
from .sgf import SGFError

FIELD_ALIASES = {
    "pb": "PB",
    "black": "PB",
    "b": "PB",
    "pw": "PW",
    "white": "PW",
    "w": "PW",
    "br": "BR",
    "black-rank": "BR",
    "wr": "WR",
    "white-rank": "WR",
    "dt": "DT",
    "date": "DT",
    "ev": "EV",
    "event": "EV",
    "ro": "RO",
    "round": "RO",
    "pc": "PC",
    "place": "PC",
    "location": "PC",
    "ru": "RU",
    "rules": "RU",
    "re": "RE",
    "result": "RE",
    "ha": "HA",
    "handicap": "HA",
    "gn": "GN",
    "name": "GN",
    "game": "GN",
    "gc": "GC",
    "comment": "GC",
    "km": "KM",
    "komi": "KM",
    "sz": "SZ",
    "size": "SZ",
}

SETTING_FIELDS = [key for key in META_KEYS if key not in ("KM", "SZ", "AP")]


def format_settings(game: Game, metadata: dict) -> str:
    lines = [f"SZ (size): {game.board.size}", f"KM (komi): {game.board.komi}"]
    for key in SETTING_FIELDS:
        lines.append(f"{key}: {metadata.get(key, '(unset)')}")
    return "\n".join(lines)


def settings_phase(game: Game, metadata: dict, reader=input, writer=print) -> None:
    writer("Settings mode. 'show' to list, '<field> <value>' to set, 'done' to return.")
    while True:
        try:
            raw = reader("settings > ").strip()
        except EOFError:
            return
        if not raw:
            continue
        parts = raw.split(maxsplit=1)
        verb = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else None
        if verb in ("done", "ok", "return", "exit", "q", "quit"):
            return
        if verb in ("help", "h", "?"):
            writer(helpmod.resolve(arg, "settings"))
            continue
        if verb in ("show", "list", "ls", "s", "info"):
            writer(format_settings(game, metadata))
            continue
        if verb in ("del", "clear", "unset", "rm"):
            if not arg:
                writer("usage: del <field>")
                continue
            key = FIELD_ALIASES.get(arg.lower(), arg.upper())
            if key in ("KM", "SZ"):
                writer(f"{key} cannot be cleared")
                continue
            metadata.pop(key, None)
            writer(f"cleared {key}")
            continue
        key = FIELD_ALIASES.get(verb, verb.upper())
        if key == "KM":
            if arg is None:
                writer(f"KM (komi): {game.board.komi}")
                continue
            try:
                value = float(arg)
            except ValueError:
                writer("komi must be a number")
                continue
            game.board.komi = value
            writer(f"KM (komi): {value}")
            continue
        if key == "SZ":
            if arg is None:
                writer(f"SZ (size): {game.board.size}")
                continue
            if game.moves:
                writer("cannot change board size after the game has started")
                continue
            try:
                size = int(arg)
            except ValueError:
                writer("size must be an integer")
                continue
            try:
                game.board = Board(size, game.board.komi, game.board.ko_rule)
            except ValueError as error:
                writer(error)
                continue
            metadata["SZ"] = str(size)
            writer(f"SZ (size): {size}")
            continue
        if key == "KO":
            if arg is None:
                writer(f"KO (rule): {game.board.ko_rule}")
                continue
            if arg not in KO_RULES:
                writer(f"unknown ko rule: {arg} (options: {', '.join(KO_RULES)})")
                continue
            game.board.ko_rule = arg
            writer(f"KO (rule): {arg}")
            continue
        if key not in SETTING_FIELDS:
            writer(f"unknown field: {verb} (try help)")
            continue
        if arg is None:
            writer(f"{key}: {metadata.get(key, '(unset)')}")
            continue
        metadata[key] = arg
        writer(f"{key}: {arg}")

SYMBOLS = {EMPTY: ".", BLACK: "X", WHITE: "O"}
DEAD_SYMBOLS = {BLACK: "x", WHITE: "o"}


def render_position(grid, size, to_play, komi, last=None, captures=None, dead=None) -> str:
    width = len(str(size))
    lines = [" " * (width + 1) + " ".join(COLUMNS[:size])]
    for y in range(size - 1, -1, -1):
        cells = []
        for x in range(size):
            idx = y * size + x
            color = grid[idx]
            if dead and color != EMPTY and idx in dead:
                cells.append(DEAD_SYMBOLS[color])
            else:
                cells.append(SYMBOLS[color])
        lines.append(f"{y + 1:>{width}} " + " ".join(cells))
    lines.append("")
    status = f"{color_name(to_play)} to play   komi {komi}"
    if captures is not None:
        status = (
            f"{color_name(to_play)} to play   "
            f"captures B:{captures[BLACK]} W:{captures[WHITE]}   komi {komi}"
        )
    lines.append(status)
    if last is not None:
        lines.append(f"last move: {format_vertex(last, size)}")
    return "\n".join(lines)


def render(game: Game) -> str:
    board = game.board
    return render_position(
        board.grid,
        board.size,
        board.to_play,
        board.komi,
        game.last_move,
        board.captures,
        game.dead,
    )


def make_move_source(reader):
    def move_source(game: Game) -> int:
        while True:
            try:
                raw = reader(f"{color_name(game.board.to_play)} to play > ")
            except EOFError:
                raise Command("quit")
            text = raw.strip()
            if not text:
                raise Command("show")
            parts = text.split(maxsplit=1)
            verb = parts[0].lower()
            argument = parts[1].strip() if len(parts) > 1 else None
            if verb in ("show", "s", "board"):
                raise Command("show")
            if verb in ("pass", "p"):
                return PASS
            if verb in ("resign", "r"):
                return RESIGN
            if verb in ("undo", "u"):
                raise Command("undo")
            if verb in ("help", "h", "?"):
                raise Command("help", argument)
            if verb in ("quit", "q", "exit"):
                raise Command("quit")
            if verb in ("save", "load"):
                raise Command(verb, argument)
            if verb in ("set", "settings", "config", "meta", "options", "@"):
                raise Command("settings")
            if argument is not None:
                print(f"unknown command: {text}")
                raise Command("show")
            try:
                return parse_vertex(verb, game.board.size)
            except ValueError as error:
                print(error)
                raise Command("show")

    return move_source


def offer_save(game: Game, metadata, record_dir, reader=input, writer=print) -> None:
    if not game.moves:
        writer("no moves to save")
        return
    name = default_filename(metadata)
    try:
        answer = reader(f"Save the game? [y/N]  (default: {name}) > ").strip()
    except EOFError:
        writer("game not saved")
        return
    low = answer.lower()
    if low in ("", "n", "no", "q", "quit", "exit"):
        writer("game not saved")
        return
    if low in ("y", "yes"):
        try:
            chosen = reader(f"File name [{name}] > ").strip()
        except EOFError:
            chosen = ""
        chosen = chosen or name
    else:
        chosen = answer
    path = resolve_write_path(chosen, record_dir)
    try:
        GameRecord.from_game(game, metadata).save(path)
        writer(f"saved to {path}")
    except (OSError, ValueError) as error:
        writer(f"error: {error}")


def mark_dead_phase(game: Game, metadata=None, reader=input, writer=print) -> str:
    metadata = metadata if metadata is not None else {}
    writer("Game ended (two passes). Entering counting phase.")
    writer("Mark dead groups with 'dead <vertex>'; 'done' to count, 'undo' to resume play.")
    while True:
        writer(render(game))
        if game.dead:
            writer(f"marked dead: {len(game.dead)} stone(s)")
        try:
            raw = reader("count > ").strip()
        except EOFError:
            return "done"
        if not raw:
            continue
        parts = raw.split(maxsplit=1)
        verb = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else None
        if verb in ("done", "count", "finish", "ok"):
            return "done"
        if verb in ("undo", "u", "resume"):
            game.undo()
            game.dead.clear()
            writer("resuming play")
            return "resumed"
        if verb in ("quit", "q", "exit"):
            return "quit"
        if verb in ("show", "s", "board", "r"):
            continue
        if verb in ("help", "h", "?"):
            writer(helpmod.resolve(arg, "counting"))
            continue
        if verb in ("set", "settings", "config", "meta"):
            settings_phase(game, metadata, reader, writer)
            continue
        if verb in ("dead", "mark", "d"):
            if not arg:
                writer("usage: dead <vertex>")
                continue
            target = arg
        else:
            target = verb
        try:
            idx = parse_vertex(target, game.board.size)
        except ValueError as error:
            writer(error)
            writer("use 'dead <vertex>' to mark, 'done' to count")
            continue
        if game.board.grid[idx] == EMPTY:
            writer("no stone at that point")
            continue
        count = game.toggle_dead(idx)
        writer(f"toggled {count} stone(s)")


def play_game(
    game: Game,
    metadata=None,
    record_dir=None,
    reader=input,
    writer=print,
    engine=None,
    ai_color=None,
) -> None:
    metadata = metadata or {}
    record_dir = Path(record_dir) if record_dir is not None else default_record_dir()
    move_source = make_move_source(reader)
    players = {
        BLACK: HumanPlayer("Black", move_source),
        WHITE: HumanPlayer("White", move_source),
    }
    if engine is not None and ai_color in (BLACK, WHITE):
        players[ai_color] = EnginePlayer("KataGo", engine)

    while True:
        while not game.over:
            writer(render(game))
            color = game.board.to_play
            if isinstance(players[color], EnginePlayer):
                writer(f"{players[color].name} 思考中…")
            try:
                move = players[color].choose_move(game)
            except EngineError as error:
                writer(f"AI 错误：{error}")
                players[color] = HumanPlayer(color_name(color), move_source)
                continue
            except Command as command:
                if command.command == "quit":
                    offer_save(game, metadata, record_dir, reader, writer)
                    writer("bye")
                    return
                if command.command == "undo":
                    try:
                        game.undo()
                    except IllegalMove as error:
                        writer(error)
                elif command.command == "help":
                    writer(helpmod.resolve(command.argument, "play"))
                elif command.command == "save":
                    if command.argument:
                        path = resolve_write_path(command.argument, record_dir)
                    else:
                        path = resolve_write_path(default_filename(metadata), record_dir)
                    try:
                        GameRecord.from_game(game, metadata).save(path)
                        writer(f"saved to {path}")
                    except (OSError, ValueError) as error:
                        writer(f"error: {error}")
                elif command.command == "load":
                    if not command.argument:
                        writer("usage: load <file.sgf>")
                    else:
                        try:
                            record = GameRecord.load(
                                resolve_read_path(command.argument, record_dir)
                            )
                            new_game = record.to_game()
                            new_game.board.ko_rule = game.board.ko_rule
                            game = new_game
                            merge_record_metadata(metadata, record)
                            writer(f"loaded {command.argument}")
                        except (OSError, ValueError, SGFError) as error:
                            writer(f"error: {error}")
                elif command.command == "settings":
                    settings_phase(game, metadata, reader, writer)
                continue
            if move == RESIGN:
                game.resign()
                break
            if move == PASS:
                game.pass_move()
                continue
            try:
                captured = game.play(move)
            except IllegalMove:
                writer(f"illegal move: {format_vertex(move, game.board.size)}")
                continue
            if captured:
                writer(f"captured {captured} stone(s)")

        if game.resigned_by is not None:
            break
        action = mark_dead_phase(game, metadata, reader, writer)
        if action == "resumed":
            continue
        break

    result = game.result()
    writer(render(game))
    if result["reason"] == "score":
        black, white = result["score"]
        writer(f"area score   Black {black:g}   White {white:g}")
        if game.dead:
            writer(f"dead stones removed: {len(game.dead)}")
    writer(game.result_text())
    offer_save(game, metadata, record_dir, reader, writer)


def view_main(argv) -> int:
    parser = argparse.ArgumentParser(prog="goban view", description="Replay an SGF record.")
    parser.add_argument("file", help="path to an .sgf file")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds per move in auto mode")
    args = parser.parse_args(argv)

    try:
        record = GameRecord.load(args.file)
    except (OSError, ValueError, SGFError) as error:
        print(f"error: {error}")
        return 1

    steps = record.steps()
    last_index = len(steps) - 1
    cursor = 0
    while True:
        step = steps[cursor]
        last = step["idx"] if step["idx"] not in (None, PASS) else None
        print(render_position(step["grid"], record.size, step["to_play"], record.komi, last))
        print(f"move {step['number']}  (position {cursor}/{last_index})")
        if step.get("comment"):
            print(f"comment: {step['comment']}")
        try:
            raw = input("view > ").strip()
        except EOFError:
            break
        tokens = raw.split(maxsplit=1)
        verb = tokens[0].lower() if tokens else ""
        topic = tokens[1].strip() if len(tokens) > 1 else None
        if verb in ("", "r", "redraw"):
            continue
        if verb in ("q", "quit", "exit"):
            break
        if verb in ("n", "next", ">"):
            cursor = min(cursor + 1, last_index)
        elif verb in ("p", "prev", "<"):
            cursor = max(cursor - 1, 0)
        elif verb in ("f", "first", "start"):
            cursor = 0
        elif verb in ("l", "last", "end"):
            cursor = last_index
        elif verb in ("info", "i"):
            print(record.info())
        elif verb in ("help", "h", "?"):
            print(helpmod.resolve(topic, "view"))
        elif verb in ("auto", "a"):
            for index in range(cursor + 1, last_index + 1):
                step = steps[index]
                last = step["idx"] if step["idx"] not in (None, PASS) else None
                print(render_position(step["grid"], record.size, step["to_play"], record.komi, last))
                print(f"move {step['number']}  (position {index}/{last_index})")
                time.sleep(max(args.delay, 0.0))
            cursor = last_index
        elif verb.isdigit():
            cursor = max(0, min(int(verb), last_index))
        else:
            print("unknown command (try help)")
    return 0


def play_main(argv) -> int:
    parser = argparse.ArgumentParser(prog="goban", description="Play Go in the terminal.")
    parser.add_argument("--size", type=int, default=19, help="board size (default 19)")
    parser.add_argument("--komi", type=float, default=7.5, help="komi for white (default 7.5)")
    parser.add_argument(
        "--ko",
        choices=KO_RULES,
        default=KO_CHINESE,
        help=f"ko rule (default {KO_CHINESE})",
    )
    parser.add_argument("--load", metavar="FILE", help="start from an SGF file")
    parser.add_argument(
        "--record-dir",
        default=str(default_record_dir()),
        help="directory for saved SGF files",
    )
    parser.add_argument("--black", help="black player name")
    parser.add_argument("--white", help="white player name")
    parser.add_argument("--event", help="event name")
    parser.add_argument("--rules", help="ruleset name")
    parser.add_argument("--date", help="date (YYYY-MM-DD)")
    parser.add_argument("--ai", action="store_true", help="让本机 KataGo 执一方")
    parser.add_argument(
        "--ai-color",
        choices=("black", "white"),
        default="white",
        help="AI 执黑或执白（默认 white）",
    )
    add_cli_arguments(parser)
    args = parser.parse_args(argv)

    metadata = {}
    for key, value in (
        ("PB", args.black),
        ("PW", args.white),
        ("EV", args.event),
        ("RU", args.rules),
        ("DT", args.date),
    ):
        if value:
            metadata[key] = value

    if args.load:
        try:
            record = GameRecord.load(resolve_read_path(args.load, args.record_dir))
            game = record.to_game()
            game.board.ko_rule = args.ko
            merge_record_metadata(metadata, record)
        except (OSError, ValueError, SGFError) as error:
            print(f"error: {error}")
            return 1
    else:
        game = Game(size=args.size, komi=args.komi, ko_rule=args.ko)

    engine = None
    ai_color = None
    if args.ai:
        try:
            ai_config = discover_config(
                overrides_from_args(args),
                config_path=args.ai_config,
            )
        except ValueError as error:
            print(f"error: {error}")
            return 1
        if ai_config is None:
            print(
                "error: 未找到 KataGo；macOS 可运行 brew install katago，"
                "或用 --ai-bin / --ai-model 指定。"
            )
            return 1
        if not ai_config.available():
            print(f"error: {ai_config.missing_reason()}")
            return 1
        engine = KataGoGTP(ai_config)
        ai_color = BLACK if args.ai_color == "black" else WHITE
        print(
            f"AI: {ai_config.binary_path()}  "
            f"model={Path(ai_config.model).name}  visits={ai_config.max_visits}"
        )

    try:
        play_game(
            game,
            metadata,
            record_dir=args.record_dir,
            engine=engine,
            ai_color=ai_color,
        )
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130
    finally:
        if engine is not None:
            engine.close()
    return 0


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in ("help", "-H"):
        topic = arguments[1] if len(arguments) > 1 else None
        print(helpmod.resolve(topic))
        return 0
    if arguments and arguments[0] == "view":
        return view_main(arguments[1:])
    if arguments and arguments[0] == "web":
        from . import web

        return web.main(arguments[1:])
    return play_main(arguments)


if __name__ == "__main__":
    sys.exit(main())
