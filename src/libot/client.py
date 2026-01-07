from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from .config import LibotConfig


class LibotError(RuntimeError):
    pass


@dataclass
class LoginResult:
    ok: bool
    detail: str | None = None


@dataclass(frozen=True)
class Seat:
    id: str
    no: str
    name: str
    area: str
    status: str
    status_name: str
    area_name: str | None = None
    point_x: float | None = None
    point_y: float | None = None
    width: float | None = None
    height: float | None = None


@dataclass(frozen=True)
class AreaNode:
    id: str
    name: str
    levels: str | None = None
    type: str | None = None
    image_url: str | None = None


class LibotClient:
    """对 booking.lib.zju.edu.cn 的最小封装。

    说明：具体接口/登录流程需根据站点实际实现。
    这里先提供 Session、base_url、以及占位方法，避免一开始就把业务“猜死”。
    """

    def __init__(self, config: LibotConfig | None = None, session: requests.Session | None = None):
        self.config = config or LibotConfig()
        self.session = session or requests.Session()
        if self.config.cookie:
            self.set_cookie_header(self.config.cookie)

    @property
    def base_url(self) -> str:
        return self.config.base_url.rstrip("/")

    def set_cookie_header(self, cookie: str) -> None:
        cookie = cookie.strip()
        if not cookie:
            return
        # 按用户要求：直接走浏览器 Cookie（等价于在请求头里带 Cookie: ...）
        self.session.headers.update({"Cookie": cookie})

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        url = self.base_url + (path if path.startswith("/") else f"/{path}")
        resp = self.session.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        url = self.base_url + (path if path.startswith("/") else f"/{path}")
        resp = self.session.post(url, **kwargs)
        resp.raise_for_status()
        return resp

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self.post(path, json=payload)
        try:
            data = resp.json()
        except Exception as e:  # pragma: no cover
            raise LibotError(f"Invalid JSON response from {path}") from e
        if not isinstance(data, dict):
            raise LibotError(f"Unexpected response shape from {path}")
        return data

    def login(self, username: str, password: str) -> LoginResult:
        """占位：登录流程。

        你确认登录方式后（例如：浙大统一认证 CAS / OAuth / 站内账号），
        我再把这里补齐成可用实现。
        """
        raise NotImplementedError(
            "login() 需要根据 booking.lib.zju.edu.cn 实际登录流程实现；"
            "请先确认是否走 ZJU 统一认证（CAS）以及是否有验证码/二次验证。"
        )

    def seat_tree(self) -> list[dict[str, Any]]:
        """获取场馆/楼层/房间树。

        该接口目前不要求登录，但我们依然会带上 Cookie（如果配置了）。
        """
        data = self.post_json("/api/Seat/tree", {})
        code = data.get("code")
        if code != 1:
            raise LibotError(str(data.get("msg") or data))
        tree = data.get("data")
        if not isinstance(tree, list):
            raise LibotError("Unexpected Seat/tree data")
        return tree

    def find_area(self, area_id: str) -> AreaNode | None:
        target = str(area_id)

        def walk(nodes: list[dict[str, Any]]) -> AreaNode | None:
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if str(node.get("id")) == target:
                    return AreaNode(
                        id=str(node.get("id", "")),
                        name=str(node.get("name", "")),
                        levels=(str(node.get("levels")) if node.get("levels") is not None else None),
                        type=(str(node.get("type")) if node.get("type") is not None else None),
                        image_url=(str(node.get("image_url")) if node.get("image_url") is not None else None),
                    )
                children = node.get("children")
                if isinstance(children, list):
                    hit = walk(children)
                    if hit:
                        return hit
            return None

        tree = self.seat_tree()
        return walk(tree)

    def seat_map_images(self, area_id: str) -> dict[str, str]:
        """获取某个区域的座位图资源（更可靠的平面图/底图来源）。

        站点提供 /api/seat/map（注意参数名是 id，不是 area）。
        返回内容通常包含：config/free/use/close/book/leave/not 等图片 URL。
        """
        data = self.post_json("/api/seat/map", {"id": str(area_id)})
        code = data.get("code")
        if code != 1:
            raise LibotError(str(data.get("msg") or data.get("message") or data))
        raw = data.get("data")
        if not isinstance(raw, dict):
            raise LibotError("Unexpected seat/map data")

        out: dict[str, str] = {}
        for k, v in raw.items():
            if v is None:
                continue
            out[str(k)] = str(v)
        return out

    def area_background_image_url(self, area_id: str) -> str | None:
        """用于可视化的背景图 URL。

        Seat/tree 里的 image_url 在部分区域可能是 404；优先使用 seat/map 的 config。
        """
        try:
            images = self.seat_map_images(area_id)
            if images.get("config"):
                return images["config"]
            if images.get("free"):
                return images["free"]
        except Exception:
            pass

        area = self.find_area(area_id)
        return area.image_url if area else None

    def list_seats(
        self,
        *,
        area: str,
        day: str,
        segment: str = "1",
        start_time: str = "08:00",
        end_time: str = "22:00",
    ) -> list[Seat]:
        """列出指定区域在给定日期/时段下的座位状态。

        通过 /api/Seat/seat：
        - area: 区域/房间 id（可从 /api/Seat/tree 的 levels=3,type=1 节点取 id）
        - segment: 时段编号（目前已验证 "1" 可用；其它值可后续再补自动获取）
        - day: YYYY-MM-DD
        - startTime/endTime: HH:MM
        """
        payload = {
            "area": str(area),
            "segment": str(segment),
            "day": str(day),
            "startTime": str(start_time),
            "endTime": str(end_time),
        }
        data = self.post_json("/api/Seat/seat", payload)
        code = data.get("code")
        if code != 1:
            raise LibotError(str(data.get("msg") or data.get("message") or data))
        raw = data.get("data")
        if not isinstance(raw, list):
            raise LibotError("Unexpected Seat/seat data")

        seats: list[Seat] = []
        for item in raw:
            if not isinstance(item, dict):
                continue

            def _to_float(v: Any) -> float | None:
                if v is None:
                    return None
                try:
                    return float(v)
                except Exception:
                    return None

            seats.append(
                Seat(
                    id=str(item.get("id", "")),
                    no=str(item.get("no", "")),
                    name=str(item.get("name", "")),
                    area=str(item.get("area", "")),
                    status=str(item.get("status", "")),
                    status_name=str(item.get("status_name", "")),
                    area_name=(str(item.get("area_name")) if item.get("area_name") is not None else None),
                    point_x=_to_float(item.get("point_x")),
                    point_y=_to_float(item.get("point_y")),
                    width=_to_float(item.get("width")),
                    height=_to_float(item.get("height")),
                )
            )
        return seats

    def list_free_seats(
        self,
        *,
        area: str,
        day: str,
        segment: str = "1",
        start_time: str = "08:00",
        end_time: str = "22:00",
    ) -> list[Seat]:
        seats = self.list_seats(area=area, day=day, segment=segment, start_time=start_time, end_time=end_time)
        return [s for s in seats if s.status == "1" or s.status_name == "空闲"]

    # 预留：后续按你选的功能补齐
    def healthcheck(self) -> bool:
        """简单连通性检查（不保证业务可用）。"""
        try:
            self.get("/")
            return True
        except Exception:
            return False
