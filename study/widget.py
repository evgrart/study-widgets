"""Small standalone YPT-inspired study timer for Windows."""
from __future__ import annotations

import ctypes
import argparse
from ctypes import wintypes
from datetime import date, timedelta
import json
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox

from study_core import COLORS, Store, Timer, format_time, now_moscow
from page_transitions import PageStack

from app_paths import ROOT, CODE_ROOT
BG = "#16191F"
PANEL = "#20252E"
ACTIVE = "#2D3029"
TEXT = "#F2F3F5"
MUTED = "#9DA5B3"
YELLOW = "#F4CF70"
LINE = "#303640"


def dpi_setup():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("StudyWidgets.Timer")


class CategoryList(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self.p = app.p
        self.canvas = tk.Canvas(self, bg=BG, bd=0, highlightthickness=0, yscrollincrement=1)
        self.canvas.pack(fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self.resize)
        self.canvas.bind("<Configure>", self.width_changed)
        self.remainder = 0.0

    def resize(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def width_changed(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        self.app.wrap_rows(event.width)

    def scroll_pixels(self, pixels):
        self.remainder += pixels
        whole = int(self.remainder)
        self.remainder -= whole
        self.canvas.yview_scroll(whole, "units")

    def scroll_delta(self, delta):
        self.scroll_pixels(-delta * self.p(40) / 120)


class App:
    def __init__(self, root, folder=ROOT, timer=None, native=True, resume_category=None):
        self.root, self.folder = root, Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.store = timer.store if timer else Store(self.folder / "study-time.sqlite3")
        self.timer = timer or Timer(self.store)
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96)
        self.rows = {}
        self.categories = []
        try:
            self.day = date.fromisoformat(self.store.setting('view_day',now_moscow().date().isoformat()))
        except (ValueError,TypeError):
            self.day = now_moscow().date()
        self.follow_today = self.day == now_moscow().date()
        self.closed = False
        self.native = None
        self.last_status = None
        self.job = None
        self.error = ""
        self.stats = None
        self.category_actions = None
        self.sleep_page = None
        self.page = 'timer'
        self.native_enabled = native
        self.root.title("Учебный таймер")
        self.root.configure(bg=BG)
        self.root.minsize(self.p(350), self.p(430))
        width = min(self.p(430), int(root.winfo_screenwidth() * .8))
        height = min(self.p(650), int(root.winfo_screenheight() * .85))
        saved = self.store.setting("geometry", "")
        if saved:
            try:
                geometry = json.loads(saved)
                width = max(self.p(350), min(int(geometry[0]), root.winfo_screenwidth()))
                height = max(self.p(430), min(int(geometry[1]), root.winfo_screenheight() - self.p(40)))
                x = max(0, min(int(geometry[2]), root.winfo_screenwidth() - width))
                y = max(0, min(int(geometry[3]), root.winfo_screenheight() - height - self.p(30)))
            except (ValueError, TypeError, IndexError):
                x, y = self.p(80), self.p(50)
        else:
            x, y = (root.winfo_screenwidth()-width)//2, self.p(50)
        root.geometry(f"{width}x{height}+{x}+{y}")
        icon = CODE_ROOT / "study.ico"
        if icon.exists():
            root.iconbitmap(str(icon))

        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", padx=self.p(22), pady=(self.p(17), self.p(10)))
        self.label(top, "STUDY TIMER", 10, color=MUTED, bold=True).pack(side="left")
        self.stats_button = self.button(top, "Статистика ↗", self.show_stats, small=True)
        self.stats_button.pack(side="right")
        self.pinned = tk.BooleanVar(value=self.store.setting("pinned", "0") == "1")
        self.pin(save=False)

        tabs = tk.Frame(root, bg=BG)
        tabs.pack(fill='x', padx=self.p(22), pady=(0,self.p(10)))
        self.tab_buttons = {}
        for name,title in [('timer','Таймер'),('sleep','Сон')]:
            button = self.button(tabs,title,lambda page=name:self.show_page(page),small=True)
            button.pack(side='left',padx=(0,self.p(6)))
            self.tab_buttons[name] = button
        self.pages=tk.Frame(root,bg=BG)
        self.pages.pack(fill='both',expand=True)
        self.page_stack=PageStack(self.pages)
        self.timer_page = tk.Frame(self.pages,bg=BG)
        dates = tk.Frame(self.timer_page, bg=BG)
        dates.pack(fill="x", padx=self.p(22))
        self.button(dates, "‹", lambda: self.change_day(-1), small=True).pack(side="left")
        self.date_text = self.label(dates, "", 10, color=MUTED)
        self.date_text.pack(side="left", expand=True)
        self.button(dates, "›", lambda: self.change_day(1), small=True).pack(side="right")
        self.day_off = tk.BooleanVar(value=False)
        day_flags = tk.Frame(self.timer_page,bg=BG)
        day_flags.pack(fill='x',padx=self.p(22),pady=(self.p(5),0))
        tk.Checkbutton(day_flags,text='Выходной',variable=self.day_off,
                       command=self.toggle_day_off,bg=BG,fg=MUTED,activebackground=BG,
                       activeforeground=TEXT,selectcolor=PANEL,bd=0,highlightthickness=0,
                       font=('Segoe UI',9),cursor='hand2').pack(anchor='w')
        self.total = self.label(self.timer_page, "00:00:00", 39, color=YELLOW, family="Consolas", bold=True)
        self.total.pack(pady=(self.p(12), 0))
        self.session = self.label(self.timer_page, "Выбери категорию и начни занятие", 10, color=MUTED)
        self.session.pack(fill="x", padx=self.p(16), pady=(self.p(1), self.p(18)))

        controls = tk.Frame(self.timer_page, bg=BG)
        controls.pack(fill="x", padx=self.p(22), pady=(0, self.p(15)))
        self.play = self.button(controls, "▶  Начать", self.toggle_selected, primary=True)
        self.play.pack(side="left", fill="x", expand=True, padx=(0, self.p(9)))
        self.button(controls, "+ Категория", self.edit_category).pack(side="right")
        self.banner = self.label(self.timer_page, "", 9, color="#F09898")

        subhead = tk.Frame(self.timer_page, bg=BG)
        subhead.pack(fill="x", padx=self.p(22), pady=(0, self.p(7)))
        self.label(subhead, "КАТЕГОРИИ", 9, color=MUTED, bold=True).pack(side="left")
        self.list = CategoryList(self.timer_page, self)
        self.list.pack(fill="both", expand=True, padx=self.p(16))
        self.empty = tk.Frame(self.list.inner, bg=BG)
        self.label(self.empty, "Здесь будут твои категории", 13, bold=True).pack(pady=(self.p(45), self.p(8)))
        self.label(self.empty, "Добавь предметы, когда будешь готов.\nДля каждого будет свой счётчик.", 10, color=MUTED).pack()
        self.button(self.empty, "+ Добавить категорию", self.edit_category).pack(pady=self.p(20))
        self.menu = tk.Menu(root, tearoff=False, bg=PANEL, fg=TEXT, activebackground=LINE,
                            activeforeground=TEXT, font=("Segoe UI", 10))
        self.menu.add_command(label="Сегодня", command=self.today)
        self.menu.add_command(label="Скрыть (Win + 2)", command=self.hide)
        self.menu.add_separator()
        self.menu.add_command(label="Завершить и остановить таймер", command=self.close)
        for element in (top,*top.winfo_children()):
            element.bind('<Button-3>',self.header_menu)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.root.bind("<MouseWheel>", self.wheel, add="+")
        self.root.bind('<Map>',lambda event:self.root.after_idle(self.dark_title)
                       if event.widget is self.root else None,add='+')
        self.root.bind('<FocusIn>',lambda event:self.dark_title()
                       if event.widget is self.root else None,add='+')
        self.reload_categories()
        if resume_category is not None:
            self.timer.start(resume_category,self.day)
            self.follow_today = False
            self.refresh()
        self.root.update_idletasks()
        if native and os.name == "nt":
            from native_scroll import NativeStudyScroll
            self.native = NativeStudyScroll(self.list, self.list.scroll_delta, self.list.scroll_pixels)
        self.show_page('timer')
        self.root.after(100, self.dark_title)
        self.root.after(60,self.poll_requests)
        self.tick()

    def p(self, value):
        return int(round(value * self.scale))

    def header_menu(self,event):
        try:self.menu.tk_popup(event.x_root,event.y_root)
        finally:self.menu.grab_release()
        return 'break'

    def show_page(self,page):
        self.close_category_actions()
        if page not in ('timer','sleep'):
            return
        if page=='sleep' and self.sleep_page is None:
            from sleep_view import SleepPane
            self.sleep_page = SleepPane(self.pages,self)
        elif page=='sleep' and self.page!='sleep':
            self.sleep_page.anchor = self.day
        if page=='sleep':self.sleep_page.refresh(force=True)
        self.page_stack.show(self.timer_page if page=='timer' else self.sleep_page,direction=1 if page=='sleep' else -1)
        self.page = page
        for name,button in self.tab_buttons.items():
            button.configure(bg=YELLOW if name==page else PANEL,fg=BG if name==page else TEXT)

    def label(self, parent, text, size, color=TEXT, bold=False, family="Segoe UI"):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=(family, size, "bold" if bold else "normal"), bd=0)

    def button(self, parent, text, command, primary=False, small=False):
        bg, fg = (YELLOW, BG) if primary else (PANEL, TEXT)
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                         activebackground="#E4BB57" if primary else LINE,
                         activeforeground=fg, disabledforeground="#606774",
                         font=("Segoe UI", 10 if not small else 9, "bold" if primary else "normal"),
                         bd=0, highlightthickness=0, cursor="hand2", relief="flat",
                         padx=self.p(13 if not small else 8), pady=self.p(8 if not small else 3))

    def dark_title(self,window=None):
        try:
            window=window or self.root
            user=ctypes.windll.user32
            user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
            user.GetAncestor.restype=wintypes.HWND
            hwnd = user.GetAncestor(window.winfo_id(),2)
            dwm=ctypes.windll.dwmapi
            dwm.DwmSetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
            flag = ctypes.c_int(1)
            result=dwm.DwmSetWindowAttribute(hwnd,20,ctypes.byref(flag),4)
            if result:
                dwm.DwmSetWindowAttribute(hwnd,19,ctypes.byref(flag),4)
            # Tk can restyle the native frame after creating a transient popup.
            # Recalculate/repaint it without hiding, moving or activating the window.
            user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,
                                       ctypes.c_int,ctypes.c_int,wintypes.UINT]
            user.SetWindowPos(hwnd,None,0,0,0,0,0x0037)
            user.RedrawWindow.argtypes=[wintypes.HWND,ctypes.c_void_p,wintypes.HRGN,wintypes.UINT]
            user.RedrawWindow(hwnd,None,None,0x0501)
        except (OSError, AttributeError):
            pass

    def pin(self, save=True):
        self.root.attributes("-topmost", self.pinned.get())
        if save:
            self.store.set_setting("pinned", int(self.pinned.get()))

    def reload_categories(self):
        self.categories = self.store.categories()
        if self.timer.selected is None and self.categories:
            saved = self.store.setting("selected", "")
            self.timer.selected = next((c["id"] for c in self.categories if str(c["id"]) == saved), self.categories[0]["id"])
        if self.categories:
            self.empty.pack_forget()
        else:
            self.empty.pack(fill="both", expand=True)
        for category in self.categories:
            cid = category["id"]
            if cid not in self.rows:
                row = tk.Frame(self.list.inner, bg=PANEL)
                row.pack(fill="x", padx=self.p(5), pady=self.p(4))
                stripe = tk.Frame(row, bg=category["color"], width=self.p(4))
                stripe.pack(side="left", fill="y")
                start = self.button(row, "▶", lambda c=cid: self.toggle(c))
                start.pack(side="right", padx=(0, self.p(6)))
                numbers = tk.Frame(row, bg=PANEL)
                numbers.pack(side="right", padx=self.p(9), pady=self.p(12))
                daily = self.label(numbers, "00:00:00", 12, bold=True, family="Consolas")
                daily.pack(anchor="e")
                title = self.label(row, category["title"], 11, bold=True)
                title.configure(anchor="w", justify="left", cursor="hand2")
                title.pack(side="left", fill="both", expand=True, padx=self.p(13), pady=self.p(12))
                for target in (row, title, daily, numbers):
                    target.bind("<Button-1>", lambda e, c=cid: self.select(c))
                    target.bind("<Button-3>", lambda e, c=cid: self.show_category_actions(c))
                    target.bind("<Double-Button-1>", lambda e, c=cid: self.edit_category(c))
                self.rows[cid] = dict(row=row, stripe=stripe, title=title, numbers=numbers,
                                      daily=daily, start=start, active=None)
            self.rows[cid]["title"].configure(text=category["title"])
            self.rows[cid]["stripe"].configure(bg=category["color"])
            self.rows[cid]["active"] = None
        self.wrap_rows(self.list.canvas.winfo_width())
        self.refresh()

    def wrap_rows(self, width):
        for row in self.rows.values():
            row["title"].configure(wraplength=max(self.p(65), width-self.p(230)))

    def show_stats(self,section=None):
        self.close_category_actions()
        section=section or ('sleep' if self.page=='sleep' else 'study')
        if self.stats is None:
            from stats_window import StatsWindow
            self.stats = StatsWindow(self)
        else:
            self.stats.hidden_by_owner=False
            self.stats.window.deiconify()
            self.stats.refresh()
        self.stats.show_section(section)
        self.stats.window.lift()
        self.stats.window.focus_force()

    def restore_session(self,state):
        """Continue a fresh update handoff without counting sleep or lost time twice."""
        from datetime import datetime
        stamp = datetime.fromisoformat(state['created_at'])
        age = (now_moscow()-stamp).total_seconds()
        gap = self.timer.clock()-float(state['awake_seconds'])
        if not (0<=age<=120 and 0<=gap<=120):
            return False
        resumed_day = date.fromisoformat(state['active_day']) if state.get('active_day') else self.day
        self.timer.start(int(state['category']),resumed_day)
        self.day = date.fromisoformat(state.get('view_day',resumed_day.isoformat()))
        self.follow_today = False
        self.store.set_setting('view_day',self.day.isoformat())
        self.timer.session_seconds = max(0,float(state['session_seconds']))
        self.timer._last = float(state['awake_seconds'])
        self.timer.checkpoint()
        self.refresh()
        self.write_status()
        return True

    def select(self, cid):
        self.timer.selected = cid
        self.store.set_setting("selected", cid)
        self.refresh()




    def toggle_selected(self):
        active_day = self.timer.active_day or now_moscow().date()
        if self.timer.active is not None and self.store.groups.start(self.day) == self.store.groups.start(active_day):
            self.timer.pause()
            self.refresh()
        elif self.timer.selected is not None:
            self.toggle(self.timer.selected)

    def toggle(self, cid):
        self.close_category_actions()
        try:
            active_day = self.timer.active_day or now_moscow().date()
            if self.timer.active == cid and self.store.groups.start(self.day) == self.store.groups.start(active_day):
                self.timer.pause()
            else:
                self.timer.start(cid,self.day)
                self.follow_today = False
                self.store.set_setting('view_day',self.day.isoformat())
            self.store.set_setting("selected", cid)
            self.show_error("")
            self.refresh()
        except Exception:
            self.show_error("Не удалось сохранить время. Попробуй ещё раз.")

    def today(self):
        self.close_category_actions()
        self.day = now_moscow().date()
        self.follow_today = True
        self.store.set_setting('view_day',self.day.isoformat())
        self.refresh()

    def change_day(self, delta):
        self.close_category_actions()
        self.day = (self.store.groups.end(self.day) if delta>0 else self.store.groups.start(self.day)) + timedelta(days=delta)
        self.follow_today = self.day == now_moscow().date()
        self.store.set_setting('view_day',self.day.isoformat())
        self.refresh()

    def toggle_day_off(self):
        self.store.set_day_off(self.day,self.day_off.get())
        self.refresh()
        if self.stats:self.stats.refresh(force=True)
        if self.sleep_page:self.sleep_page.refresh(force=True)

    def refresh(self):
        today = now_moscow().date()
        if self.follow_today:
            self.day = today
        suffix = " · сегодня" if self.day == today else ""
        start=self.store.groups.start(self.day);end=self.store.groups.end(self.day)
        off = str(start) in self.store.days_off()
        if self.day_off.get()!=off:self.day_off.set(off)
        if off:suffix += ' · выходной'
        weekdays = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
        label=f"{weekdays[self.day.weekday()]}, {self.day:%d.%m.%Y}" if start==end else f'{start:%d.%m} — {end:%d.%m.%Y}'
        self.date_text.configure(text=label+suffix)
        self.total.configure(text=format_time(self.timer.day_time(self.day)))
        active = next((c for c in self.categories if c["id"] == self.timer.active), None)
        selected = next((c for c in self.categories if c["id"] == self.timer.selected), None)
        active_day = self.timer.active_day or today
        viewing_active_day = active is not None and start == self.store.groups.start(active_day)
        if active:
            title = active["title"]
            if len(title) > 25:
                title = title[:24] + "…"
            prefix = f'{active_day:%d.%m} · ' if not viewing_active_day else ''
            self.session.configure(text=f"● {prefix}{title} · занятие {format_time(self.timer.session_seconds)}", fg=active["color"])
        else:
            name = selected["title"] if selected else "Выбери категорию и начни занятие"
            description = f"Пауза · {name}" if selected else name
            self.session.configure(text=description, fg=MUTED,
                                   wraplength=self.root.winfo_width()-self.p(40))
        has_day_time = selected and self.timer.category_time(selected['id'],self.day)>0
        play_text = 'Ⅱ  Пауза' if viewing_active_day else ('▶  Продолжить' if has_day_time else '▶  Начать')
        self.play.configure(text=play_text,
                            state="normal" if self.categories else "disabled")
        for category in self.categories:
            cid = category["id"]
            row = self.rows[cid]
            row["daily"].configure(text=format_time(self.timer.category_time(cid, self.day)))
            state = (self.timer.active == cid and start == self.store.groups.start(active_day), self.timer.selected == cid)
            if row["active"] != state:
                bg = ACTIVE if state[0] else PANEL
                for key in ("row", "numbers", "title", "daily"):
                    row[key].configure(bg=bg)
                row["title"].configure(fg=category["color"] if state[1] else TEXT)
                row["start"].configure(text="Ⅱ" if state[0] else "▶", fg=category["color"] if state[0] else TEXT)
                row["active"] = state

    def show_error(self, text):
        if text == self.error:
            return
        self.error = text
        self.banner.configure(text=text)
        if text:
            self.banner.pack(before=self.list, fill="x", padx=self.p(16))
        else:
            self.banner.pack_forget()

    def edit_category(self, category_id=None):
        self.close_category_actions()
        category = next((c for c in self.categories if c["id"] == category_id), None)
        dialog = tk.Toplevel(self.root)
        dialog.title("Категория" if category else "Новая категория")
        dialog.configure(bg=BG)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()
        body = tk.Frame(dialog, bg=BG, padx=self.p(20), pady=self.p(20))
        body.pack(fill="both", expand=True)
        self.label(body, "Название категории", 11, bold=True).pack(anchor="w")
        name = tk.StringVar(value=category["title"] if category else "")
        entry = tk.Entry(body, textvariable=name, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=("Segoe UI", 12), width=27)
        entry.pack(fill="x", pady=(self.p(10), self.p(18)), ipady=self.p(7))
        color = tk.StringVar(value=category["color"] if category else COLORS[len(self.categories) % len(COLORS)])
        palette = tk.Frame(body, bg=BG)
        palette.pack(fill="x")
        for shade in COLORS:
            tk.Radiobutton(palette, variable=color, value=shade, bg=BG, fg=shade, selectcolor=BG,
                           activebackground=BG, activeforeground=shade, text="●", font=("Segoe UI", 18),
                           indicatoron=True, bd=0, highlightthickness=0).pack(side="left")
        error = self.label(body, "", 9, color="#F09898")
        error.pack(pady=self.p(8))

        def save(event=None):
            try:
                cid = self.store.save_category(name.get(), color.get(), category_id)
                self.timer.selected = cid
                self.store.set_setting("selected", cid)
            except ValueError as exc:
                error.configure(text=str(exc))
                return
            except Exception:
                error.configure(text="Не удалось сохранить категорию.")
                return
            dialog.destroy()
            self.reload_categories()

        self.button(body, "Сохранить" if category else "Добавить", save, primary=True).pack(fill="x")
        dialog.bind("<Return>", save)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width()-dialog.winfo_width())//2
        y = self.root.winfo_y() + self.p(90)
        dialog.geometry(f"+{max(0,x)}+{max(0,y)}")
        entry.focus_set()
        entry.selection_range(0, "end")

    def wheel(self, event):
        if self.root.grab_current():
            return
        x, y = event.x_root, event.y_root
        panel = self.sleep_page if self.page=='sleep' else self.list
        if panel.winfo_rootx() <= x < panel.winfo_rootx()+panel.winfo_width() and panel.winfo_rooty() <= y < panel.winfo_rooty()+panel.winfo_height():
            panel.scroll_delta(event.delta)
            return "break"

    def tick(self):
        if self.closed:
            return
        try:
            self.timer.checkpoint()
            self.show_error("")
        except Exception:
            self.show_error("Не удалось сохранить время. Оставь приложение открытым.")
        self.refresh()
        if self.page=='sleep' and self.sleep_page:
            self.sleep_page.refresh()
        if self.stats is not None and self.stats.window.state()=='normal':
            self.stats.refresh()
        state = (self.timer.active,self.timer.active_day,self.day,len(self.categories),self.root.state(),self.page)
        if state != self.last_status:
            self.write_status()
            self.last_status = state
        self.job = self.root.after(250, self.tick)

    def poll_requests(self):
        if self.closed:return
        request = self.folder / "show.request"
        if request.exists():
            try:
                request.unlink()
            except OSError:
                pass
            self.show()
        stats_request = self.folder / "stats.request"
        if stats_request.exists():
            stats_request.unlink()
            self.show()
            self.show_stats()
        sleep_request = self.folder / 'sleep.request'
        if sleep_request.exists():
            sleep_request.unlink()
            self.show()
            self.show_page('sleep')
        self.root.after(60,self.poll_requests)

    def write_status(self):
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) if os.name == "nt" else self.root.winfo_id()
        status = dict(pid=os.getpid(), window_handle=hwnd, category_count=len(self.categories),
                      running=self.timer.active is not None, active_category=self.timer.active,
                      active_day=self.timer.active_day.isoformat() if self.timer.active_day else None,
                      view_day=self.day.isoformat(),
                      view_tab=self.page,
                      session_seconds=self.timer.session_seconds,
                      visible=self.root.state() not in ("withdrawn", "iconic"))
        path = self.folder / "status.json"
        try:
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(status), encoding="utf-8")
            temp.replace(path)
        except OSError:
            pass

    def save_geometry(self):
        if self.root.state() != "withdrawn":
            self.store.set_setting("geometry", json.dumps([self.root.winfo_width(), self.root.winfo_height(),
                                                            self.root.winfo_x(), self.root.winfo_y()]))

    def show(self):
        self.root.deiconify()
        self.dark_title()
        self.root.lift()
        self.root.focus_force()
        self.refresh()
        if self.stats:
            self.stats.restore()
        self.write_status()

    def hide(self):
        self.close_category_actions()
        try:
            self.timer.tick()
            self.timer.flush()
            self.save_geometry()
        except Exception:
            self.show_error("Не удалось сохранить время. Оставь приложение открытым.")
            return
        if self.stats:
            self.stats.hide()
        self.root.withdraw()
        self.write_status()

    def close(self):
        self.close_category_actions()
        try:
            self.timer.pause()
            self.save_geometry()
        except Exception:
            messagebox.showerror("Учебный таймер", "Не удалось сохранить время. Окно оставлено открытым — попробуй ещё раз.", parent=self.root)
            return
        self.closed = True
        if self.job:
            self.root.after_cancel(self.job)
        if self.native:
            self.native.stop()
        if self.stats:
            self.stats.close()
        if self.sleep_page:
            self.sleep_page.close()
        self.write_status()
        self.store.close()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-category", type=int, default=None)
    parser.add_argument("--resume-state", type=Path)
    parser.add_argument("--statistics", action='store_true')
    args = parser.parse_args()
    dpi_setup()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    mutex = kernel.CreateMutexW(None, False, "Local\\StudyWidgetsTimer-" + os.environ.get("USERNAME", "user"))
    error = ctypes.get_last_error()
    if not mutex:
        raise ctypes.WinError(error)
    if error == 183:
        (ROOT / "show.request").touch()
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle(mutex)
        return
    root = tk.Tk()
    app = App(root, resume_category=args.resume_category)
    if args.resume_state is not None:
        state = json.loads(args.resume_state.read_text(encoding='utf-8'))
        if app.restore_session(state):
            args.resume_state.replace(args.resume_state.with_suffix('.consumed.json'))
    if args.statistics:
        app.show_stats()

    def tk_error(kind, value, trace):
        import traceback
        with (ROOT / "error.log").open("a", encoding="utf-8") as log:
            traceback.print_exception(kind, value, trace, file=log)
        app.show_error("Возникла ошибка. Время сохранится при закрытии.")

    root.report_callback_exception = tk_error
    root.mainloop()
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle(mutex)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        (ROOT / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
