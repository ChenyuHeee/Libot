from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime


from .client import LibotClient, LibotError
from .bundled import get_bundled_dingtalk_webhook
from .config import load_config


def _require_pyside6() -> None:
    try:
        import PySide6  # noqa: F401
    except Exception as e:  # pragma: no cover
        raise SystemExit(
            "GUI 依赖未安装。请执行：pip install -e '.[gui]'\n"
            "然后运行：libot-gui"
        ) from e


@dataclass(frozen=True)
class Query:
    day: str
    segment: str
    start_time: str
    end_time: str


def main(argv: list[str] | None = None) -> int:
    # 延迟导入，避免没装 GUI 依赖时影响 CLI。
    _require_pyside6()

    from PySide6.QtCore import QDate, Qt, QTimer
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QDateEdit,
        QFormLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QStyle,
        QSpinBox,
        QSplitter,
        QSystemTrayIcon,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    def _macos_hide_dock_icon_best_effort() -> None:
        if sys.platform != "darwin":
            return
        try:
            import ctypes

            objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
            objc.objc_getClass.restype = ctypes.c_void_p
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.objc_msgSend.restype = ctypes.c_void_p

            def cls(name: str) -> ctypes.c_void_p:
                return ctypes.c_void_p(objc.objc_getClass(name.encode("utf-8")))

            def sel(name: str) -> ctypes.c_void_p:
                return ctypes.c_void_p(objc.sel_registerName(name.encode("utf-8")))

            objc_msgSend = objc.objc_msgSend
            objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

            NSApplication = cls("NSApplication")
            shared = objc_msgSend(NSApplication, sel("sharedApplication"))

            # NSApplicationActivationPolicyProhibited = 2
            objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
            objc.objc_msgSend(ctypes.c_void_p(shared), sel("setActivationPolicy:"), 2)
        except Exception:
            # 失败也不影响功能；打包 .app 会用 Info.plist 保证隐藏 Dock 图标
            return

    config = load_config()
    client = LibotClient(config=config)

    app = QApplication(argv or [])
    app.setQuitOnLastWindowClosed(False)

    _macos_hide_dock_icon_best_effort()

    is_quitting = {"flag": False}

    class MainWindow(QMainWindow):
        def closeEvent(self, event) -> None:  # type: ignore[override]
            # 点击左上角关闭：仅隐藏，不退出
            if is_quitting["flag"]:
                return super().closeEvent(event)
            event.ignore()
            self.hide()

    window = MainWindow()
    window.setWindowTitle("Libot")

    root = QWidget()
    window.setCentralWidget(root)

    splitter = QSplitter(Qt.Orientation.Horizontal)

    # 左侧：控制面板
    panel = QWidget()
    form = QFormLayout(panel)

    cookie_input = QLineEdit()
    cookie_input.setPlaceholderText('Cookie: a=b; c=d (可留空，或用环境变量 LIBOT_COOKIE)')
    if os.environ.get("LIBOT_COOKIE"):
        cookie_input.setText(os.environ.get("LIBOT_COOKIE", ""))
    elif config.cookie:
        cookie_input.setText(config.cookie)

    day_edit = QDateEdit()
    day_edit.setCalendarPopup(True)
    day_edit.setDate(QDate.currentDate())

    segment_input = QLineEdit("1")
    start_input = QLineEdit("08:00")
    end_input = QLineEdit("22:00")

    # 钉钉 webhook（可选）
    webhook_input = QLineEdit()
    webhook_input.setPlaceholderText('钉钉机器人 webhook (可选)')
    if os.environ.get("DINGTALK_WEBHOOK"):
        webhook_input.setText(os.environ.get("DINGTALK_WEBHOOK", ""))
    else:
        bundled_webhook = get_bundled_dingtalk_webhook()
        if bundled_webhook:
            webhook_input.setText(bundled_webhook)

    # 选择要监控的馆舍（启动时会填充馆舍列表；默认全部）
    monitor_list = QListWidget()
    monitor_list.setToolTip("勾选要监控的馆舍（可多选）。若不勾选任何馆舍，则不推送。")
    monitor_list.setMinimumHeight(120)

    limit_spin = QSpinBox()
    limit_spin.setRange(0, 10000)
    limit_spin.setValue(0)
    limit_spin.setToolTip("每个房间最多展示多少个空闲座位号；0 表示不限制")

    reload_btn = QPushButton("刷新")

    keep_awake_checkbox = QCheckBox("锁屏后继续运行（防睡眠）")
    keep_awake_checkbox.setToolTip(
        "macOS 下通过 caffeinate 防止系统睡眠；锁屏不影响运行。注意：合盖通常仍会睡眠。"
    )
    if sys.platform != "darwin":
        keep_awake_checkbox.setEnabled(False)
        keep_awake_checkbox.setToolTip("仅支持 macOS（依赖 caffeinate）")
    else:
        keep_awake_checkbox.setChecked(True)

    status_label = QLabel("")
    status_label.setWordWrap(True)

    form.addRow("Cookie", cookie_input)
    form.addRow("钉钉 webhook", webhook_input)
    form.addRow("监控馆舍", monitor_list)
    form.addRow("日期", day_edit)
    form.addRow("时段 segment", segment_input)
    form.addRow("开始时间", start_input)
    form.addRow("结束时间", end_input)
    form.addRow("每房间显示座位数", limit_spin)
    form.addRow(keep_awake_checkbox)
    form.addRow(reload_btn)
    form.addRow("状态", status_label)

    # 右侧：列表（按馆舍分组）
    tree_widget = QTreeWidget()
    tree_widget.setHeaderLabels(["馆舍/房间", "空闲数", "空闲座位(示例)"])
    tree_widget.setUniformRowHeights(True)

    splitter.addWidget(panel)
    splitter.addWidget(tree_widget)
    splitter.setStretchFactor(1, 1)

    layout = QVBoxLayout(root)
    layout.addWidget(splitter)

    def show_error(title: str, message: str) -> None:
        QMessageBox.critical(window, title, message)

    def ensure_cookie() -> None:
        cookie = cookie_input.text().strip() or os.environ.get("LIBOT_COOKIE") or config.cookie
        if cookie:
            client.set_cookie_header(cookie)

    def load_room_index() -> dict[str, list[tuple[str, str]]]:
        """返回：馆舍名 -> [(room_id, room_name), ...]"""

        ensure_cookie()
        try:
            raw_tree = client.seat_tree()
        except LibotError as e:
            raise LibotError(f"加载区域失败：{e}") from e

        grouped: dict[str, list[tuple[str, str]]] = {}

        def walk(nodes, current_library: str | None = None) -> None:
            for n in nodes:
                if not isinstance(n, dict):
                    continue

                levels = str(n.get("levels")) if n.get("levels") is not None else ""
                typ = str(n.get("type")) if n.get("type") is not None else ""

                lib = current_library
                if levels == "1":
                    name = str(n.get("name", ""))
                    lib = name or current_library

                # levels=3,type=1 为房间节点
                if levels == "3" and typ == "1":
                    room_id = str(n.get("id", ""))
                    room_name = str(n.get("name", ""))
                    if room_id:
                        key = lib or "未知馆舍"
                        grouped.setdefault(key, []).append((room_id, room_name))

                children = n.get("children")
                if isinstance(children, list):
                    walk(children, lib)

        walk(raw_tree)

        for k in grouped:
            grouped[k].sort(key=lambda x: (x[1], x[0]))
        return dict(sorted(grouped.items(), key=lambda x: x[0]))

    def send_dingtalk(webhook: str, text: str) -> bool:
        """发送文本消息到钉钉自定义机器人，返回是否成功。"""
        if not webhook:
            return False
        if not text.startswith("[ZJU]"):
            text = "[ZJU]" + text
        payload = {"msgtype": "text", "text": {"content": text}}
        try:
            resp = client.session.post(webhook, json=payload, timeout=6)
            try:
                resp.raise_for_status()
            except Exception:
                return False
            return True
        except Exception:
            return False

    # 保留状态字典（未来如需去重/节流可用）
    last_has_free: dict[str, bool] = {}

    caffeinate_proc: subprocess.Popen[str] | None = None

    def set_keep_awake(enabled: bool) -> None:
        nonlocal caffeinate_proc
        if sys.platform != "darwin":
            return

        if enabled:
            if caffeinate_proc and caffeinate_proc.poll() is None:
                return
            try:
                # -w <pid>：当本进程退出时 caffeinate 自动结束
                caffeinate_proc = subprocess.Popen(
                    ["caffeinate", "-dimsu", "-w", str(os.getpid())],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                status_label.setText(status_label.text() + "\n已开启防睡眠（锁屏可继续运行）")
            except Exception as e:
                caffeinate_proc = None
                show_error("开启防睡眠失败", repr(e))
        else:
            if caffeinate_proc and caffeinate_proc.poll() is None:
                try:
                    caffeinate_proc.terminate()
                except Exception:
                    pass
            caffeinate_proc = None

    keep_awake_checkbox.toggled.connect(set_keep_awake)

    def _monitor_key(libs: list[str]) -> str:
        libs_sorted = sorted({x for x in libs if x})
        return "|".join(libs_sorted) if libs_sorted else "__none__"

    def get_selected_libraries(grouped: dict[str, list[tuple[str, str]]]) -> list[str]:
        # 勾选项列表（排除“全部馆舍”占位）
        selected: list[str] = []
        for i in range(monitor_list.count()):
            it = monitor_list.item(i)
            lib = it.data(Qt.ItemDataRole.UserRole)
            if lib == "__all__":
                continue
            if it.checkState() == Qt.CheckState.Checked and isinstance(lib, str):
                selected.append(lib)

        # 如果勾选“全部馆舍”，等价于监控所有馆舍
        all_item = monitor_list.item(0) if monitor_list.count() > 0 else None
        if all_item and all_item.data(Qt.ItemDataRole.UserRole) == "__all__":
            if all_item.checkState() == Qt.CheckState.Checked:
                return list(grouped.keys())

        return selected

    def refresh() -> None:
        ensure_cookie()

        q = Query(
            day=day_edit.date().toString("yyyy-MM-dd"),
            segment=segment_input.text().strip() or "1",
            start_time=start_input.text().strip() or "08:00",
            end_time=end_input.text().strip() or "22:00",
        )

        try:
            grouped = load_room_index()
            per_room_limit = int(limit_spin.value())

            tree_widget.clear()

            total_rooms = 0
            total_free = 0

            lib_free_map: dict[str, int] = {}
            seat_nos_map: dict[str, list[str]] = {}

            for lib_name, rooms in grouped.items():
                lib_item = QTreeWidgetItem([lib_name, "", ""])
                lib_item.setFirstColumnSpanned(False)
                tree_widget.addTopLevelItem(lib_item)

                lib_free = 0
                for room_id, room_name in rooms:
                    total_rooms += 1
                    seats = client.list_free_seats(
                        area=room_id,
                        day=q.day,
                        segment=q.segment,
                        start_time=q.start_time,
                        end_time=q.end_time,
                    )
                    lib_free += len(seats)
                    total_free += len(seats)

                    seat_nos = [s.no for s in seats if s.no]
                    if per_room_limit > 0:
                        shown = seat_nos[:per_room_limit]
                        more = len(seat_nos) - len(shown)
                    else:
                        shown = seat_nos
                        more = 0

                    seat_text = ", ".join(shown)
                    if more > 0:
                        seat_text += f" …(+{more})"

                    room_title = f"{room_name} ({room_id})" if room_name else str(room_id)
                    room_item = QTreeWidgetItem([room_title, str(len(seats)), seat_text])
                    if seat_nos:
                        room_item.setToolTip(2, ", ".join(seat_nos))
                    # 保存房间座位号用于通知构建
                    seat_nos_map[room_id] = seat_nos
                    lib_item.addChild(room_item)

                lib_item.setText(1, str(lib_free))
                lib_free_map[lib_name] = lib_free
                lib_item.setExpanded(False)

            tree_widget.resizeColumnToContents(0)
            tree_widget.resizeColumnToContents(1)

            status_label.setText(
                f"日期：{q.day}  时间：{q.start_time}-{q.end_time}  segment={q.segment}\n"
                f"馆舍数：{len(grouped)}  房间数：{total_rooms}  总空闲：{total_free}\n"
                f"最近刷新：{datetime.now().strftime('%H:%M:%S')}（每 60 秒自动刷新）"
            )

            # --- 钉钉推送逻辑 ---
            webhook = (
                webhook_input.text().strip()
                or os.environ.get("DINGTALK_WEBHOOK")
                or get_bundled_dingtalk_webhook()
                or ""
            )
            selected_libs = get_selected_libraries(grouped)
            monitor_key = _monitor_key(selected_libs)

            # 未选择任何馆舍：不推送
            has_free = False
            if selected_libs:
                has_free = any(lib_free_map.get(lib, 0) > 0 for lib in selected_libs)

            # 用户期望“每分钟自动推送”：只要监控集合有空位，每次刷新都推送；无空位则不推送。
            should_send = bool(webhook) and bool(selected_libs) and has_free
            last_has_free[monitor_key] = has_free

            if should_send:
                chunks: list[str] = []
                for lib in selected_libs:
                    if lib_free_map.get(lib, 0) <= 0:
                        continue

                    room_lines: list[str] = []
                    for room_id, room_name in grouped.get(lib, []):
                        if not seat_nos_map.get(room_id):
                            continue
                        link = (
                            f"{client.base_url}/h5/index.html#/SeatScreening/{q.segment}"
                            f"/roomDetail?detail={room_id}&date={q.day}"
                        )
                        room_title = room_name or room_id
                        room_lines.append(f"【{room_title}】{link}")

                    # 理论上有空位时 room_lines 应该非空；这里做兜底。
                    header = f"{lib}有空位："
                    if room_lines:
                        chunks.append(header + "\n" + "\n".join(room_lines))
                    else:
                        chunks.append(header)

                text = "\n\n".join(chunks) if chunks else "当前无空位"

                ok = send_dingtalk(webhook, text)
                if ok:
                    status_label.setText(status_label.text() + "\n已推送通知到钉钉")
                else:
                    status_label.setText(status_label.text() + "\n推送钉钉失败")

        except LibotError as e:
            show_error("刷新失败", str(e))
        except Exception as e:  # pragma: no cover
            show_error("刷新失败", repr(e))

    reload_btn.clicked.connect(refresh)

    # 尝试填充监控馆舍下拉（不成功也不阻塞）
    try:
        grouped_init = load_room_index()

        monitor_list.clear()
        all_item = QListWidgetItem("全部馆舍")
        all_item.setData(Qt.ItemDataRole.UserRole, "__all__")
        all_item.setFlags(all_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        all_item.setCheckState(Qt.CheckState.Unchecked)
        monitor_list.addItem(all_item)

        for lib in grouped_init.keys():
            it = QListWidgetItem(lib)
            it.setData(Qt.ItemDataRole.UserRole, lib)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # 默认只监控：主馆、基础馆
            if ("主馆" in lib) or ("基础馆" in lib) or (lib == "基础") or (lib == "基础馆"):
                it.setCheckState(Qt.CheckState.Checked)
            else:
                it.setCheckState(Qt.CheckState.Unchecked)
            monitor_list.addItem(it)

        changing = {"flag": False}

        def on_monitor_item_changed(item: QListWidgetItem) -> None:
            if changing["flag"]:
                return

            lib = item.data(Qt.ItemDataRole.UserRole)
            if lib == "__all__":
                # 切换“全部馆舍”时，同步其他项
                changing["flag"] = True
                try:
                    state = item.checkState()
                    for i in range(1, monitor_list.count()):
                        monitor_list.item(i).setCheckState(state)
                finally:
                    changing["flag"] = False

            # 选择变化后，允许下一次出现空位时推送
            refresh()

        monitor_list.itemChanged.connect(on_monitor_item_changed)
    except LibotError:
        # 忽略，如果后续刷新才能成功加载
        pass

    # 每分钟自动刷新一次
    timer = QTimer(window)
    timer.setInterval(60_000)
    timer.timeout.connect(refresh)
    timer.start()

    refresh()

    window.resize(1200, 800)
    window.show()

    # 菜单栏图标（macOS 会显示在 menu bar；其他系统显示在托盘）
    tray_icon = QSystemTrayIcon()
    icon = app.windowIcon()
    if icon.isNull():
        icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    tray_icon.setIcon(icon)
    tray_icon.setToolTip("Libot")

    tray_menu = QMenu()
    action_show = QAction("显示/隐藏")
    action_quit = QAction("退出")
    tray_menu.addAction(action_show)
    tray_menu.addSeparator()
    tray_menu.addAction(action_quit)
    tray_icon.setContextMenu(tray_menu)

    def toggle_window() -> None:
        if window.isVisible():
            window.hide()
        else:
            window.show()
            window.raise_()
            window.activateWindow()

    def quit_app() -> None:
        is_quitting["flag"] = True
        tray_icon.hide()
        app.quit()

    action_show.triggered.connect(toggle_window)
    action_quit.triggered.connect(quit_app)
    tray_icon.activated.connect(lambda _reason: toggle_window())
    tray_icon.show()

    return app.exec()
