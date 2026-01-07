from __future__ import annotations

import argparse
import getpass
import os
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from .client import LibotClient, LibotError
from .config import load_config


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="libot", description="Libot: ZJU library booking wrapper")
    p.add_argument("--base-url", default=None, help="Override base URL (default from config)")

    sub = p.add_subparsers(dest="cmd", required=False)

    sub.add_parser("ping", help="Check connectivity (GET /)")

    login_p = sub.add_parser("login", help="Login (placeholder; not implemented yet)")
    login_p.add_argument("--username", required=True)
    login_p.add_argument("--password", default=None, help="If omitted, will prompt")

    seats_p = sub.add_parser("seats", help="List free seats in an area")
    seats_p.add_argument("--area", required=True, help="Area/room id from Seat/tree (levels=3,type=1)")
    seats_p.add_argument("--day", default=date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    seats_p.add_argument("--segment", default="1", help="Time segment id (default: 1)")
    seats_p.add_argument("--start", dest="start_time", default="08:00", help="HH:MM (default: 08:00)")
    seats_p.add_argument("--end", dest="end_time", default="22:00", help="HH:MM (default: 22:00)")
    seats_p.add_argument(
        "--cookie",
        default=None,
        help='Browser Cookie header value, e.g. "a=b; c=d" (or set LIBOT_COOKIE)'
    )
    seats_p.add_argument("--limit", type=int, default=0, help="Limit output count (0 = no limit)")
    seats_p.add_argument(
        "--coords",
        action="store_true",
        help="Show seat coordinates (point_x/point_y) from the API",
    )

    areas_p = sub.add_parser("areas", help="List seat areas (rooms) with ids")
    areas_p.add_argument(
        "--cookie",
        default=None,
        help='Browser Cookie header value, e.g. "a=b; c=d" (or set LIBOT_COOKIE)'
    )

    viz_p = sub.add_parser("viz", help="Visualize free seats on the area map (SVG)")
    viz_p.add_argument("--area", required=True, help="Area/room id from Seat/tree (levels=3,type=1)")
    viz_p.add_argument("--day", default=date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    viz_p.add_argument("--segment", default="1", help="Time segment id (default: 1)")
    viz_p.add_argument("--start", dest="start_time", default="08:00", help="HH:MM (default: 08:00)")
    viz_p.add_argument("--end", dest="end_time", default="22:00", help="HH:MM (default: 22:00)")
    viz_p.add_argument(
        "--cookie",
        default=None,
        help='Browser Cookie header value, e.g. "a=b; c=d" (or set LIBOT_COOKIE)'
    )
    viz_p.add_argument("--out", default="seats.svg", help="Output SVG path (default: seats.svg)")
    viz_p.add_argument("--limit", type=int, default=0, help="Limit plotted seats (0 = no limit)")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config()
    if args.base_url:
        # 轻量覆盖，不写入磁盘
        config = type(config)(base_url=args.base_url)

    client = LibotClient(config=config)

    if args.cmd in (None, ""):
        parser.print_help()
        return 0

    if args.cmd == "ping":
        ok = client.healthcheck()
        print("ok" if ok else "failed")
        return 0 if ok else 2

    if args.cmd == "login":
        password = args.password or getpass.getpass("Password: ")
        # 占位：明确提示
        _ = password  # noqa: F841
        print("login: not implemented yet (need confirm auth flow)")
        return 2

    if args.cmd == "seats":
        cookie = args.cookie or os.environ.get("LIBOT_COOKIE") or config.cookie
        if cookie:
            client.set_cookie_header(cookie)
        try:
            seats = client.list_free_seats(
                area=args.area,
                day=args.day,
                segment=args.segment,
                start_time=args.start_time,
                end_time=args.end_time,
            )
        except LibotError as e:
            print(f"error: {e}")
            return 2

        if not seats:
            print("(no free seats)")
            return 0

        limit = int(args.limit or 0)
        shown = seats[:limit] if limit > 0 else seats
        area_name = shown[0].area_name if shown and shown[0].area_name else None
        header = f"free seats: {len(seats)}"
        if area_name:
            header += f" | area: {area_name}"
        header += f" | day: {args.day} | {args.start_time}-{args.end_time} | segment: {args.segment}"
        print(header)

        bg = client.area_background_image_url(args.area)
        if bg:
            print(f"map: {bg}")

        for s in shown:
            if args.coords:
                x = "" if s.point_x is None else f"{s.point_x:.3f}"
                y = "" if s.point_y is None else f"{s.point_y:.3f}"
                print(f"{s.no}\t{x}\t{y}\t{s.status_name}")
            else:
                print(s.no)
        return 0

    if args.cmd == "areas":
        cookie = args.cookie or os.environ.get("LIBOT_COOKIE") or config.cookie
        if cookie:
            client.set_cookie_header(cookie)

        try:
            tree = client.seat_tree()
        except LibotError as e:
            print(f"error: {e}")
            return 2

        # 只打印“房间/区域”节点：levels=3 且 type=1（从 Seat/tree 返回中观察到）
        def walk(nodes):
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                levels = str(node.get("levels")) if node.get("levels") is not None else ""
                typ = str(node.get("type")) if node.get("type") is not None else ""
                if levels == "3" and typ == "1":
                    _id = str(node.get("id", ""))
                    name = str(node.get("name", ""))
                    print(f"{_id}\t{name}")
                children = node.get("children")
                if isinstance(children, list):
                    walk(children)

        walk(tree)
        return 0

    if args.cmd == "viz":
        cookie = args.cookie or os.environ.get("LIBOT_COOKIE") or config.cookie
        if cookie:
            client.set_cookie_header(cookie)

        try:
            area_meta = client.find_area(args.area)
            bg = client.area_background_image_url(args.area)
            if not bg:
                print("error: cannot find area background image; try `libot areas` to confirm area id")
                return 2
            seats = client.list_free_seats(
                area=args.area,
                day=args.day,
                segment=args.segment,
                start_time=args.start_time,
                end_time=args.end_time,
            )
        except LibotError as e:
            print(f"error: {e}")
            return 2

        limit = int(args.limit or 0)
        shown = seats[:limit] if limit > 0 else seats

        # 该站点的 point_x/point_y 看起来是 0-100 的归一化坐标。
        # 为避免引入图片处理依赖，这里直接生成 viewBox=0..100 的 SVG，背景用远程 image_url。
        img_url = escape(bg)
        area_name = area_meta.name if area_meta else ""
        title = escape(f"area={area_name} id={args.area} day={args.day} {args.start_time}-{args.end_time} seg={args.segment}")
        circles = []
        for s in shown:
            if s.point_x is None or s.point_y is None:
                continue
            cx = s.point_x
            cy = s.point_y
            # tooltip
            tip = escape(f"{s.no} ({s.status_name})")
            circles.append(
                f"<g>"
                f"<title>{tip}</title>"
                f"<circle cx=\"{cx:.3f}\" cy=\"{cy:.3f}\" r=\"0.8\" fill=\"lime\" fill-opacity=\"0.35\" stroke=\"green\" stroke-width=\"0.15\" />"
                f"</g>"
            )

        svg = "\n".join(
            [
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
                f"<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 100 100\" width=\"1000\" height=\"1000\" preserveAspectRatio=\"none\">",
                f"<title>{title}</title>",
                f"<image href=\"{img_url}\" x=\"0\" y=\"0\" width=\"100\" height=\"100\" preserveAspectRatio=\"none\" />",
                "<g>",
                *circles,
                "</g>",
                "</svg>",
            ]
        )

        out_path = Path(args.out).expanduser().resolve()
        out_path.write_text(svg, encoding="utf-8")
        print(f"wrote: {out_path}")
        print(f"map: {bg}")
        print(f"plotted: {len(shown)} (free seats total: {len(seats)})")
        return 0

    parser.print_help()
    return 0
