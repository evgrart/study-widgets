"""Exercise the GUI with disposable data and an injected clock."""
import ctypes
import json
from pathlib import Path
import tempfile
import tkinter as tk

from study_core import COLORS, Store, Timer, now_moscow
from verify_timer import Clock
from widget import App, dpi_setup


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def main():
    dpi_setup()
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        clock = Clock(now_moscow())
        store = Store(folder / "test.sqlite3")
        timer = Timer(store, clock.read, clock.wall)
        root = tk.Tk()
        app = App(root, folder, timer, native=True)
        root.geometry("900x1300+20000+20000")
        root.update()
        assert app.play.cget("state") == "disabled"
        assert app.empty.winfo_manager() == "pack"

        # Add a category through the actual dialog; no seed data in the real app.
        app.edit_category()
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        entry = next(w for w in descendants(dialog) if isinstance(w, tk.Entry))
        entry.insert(0, "Тест алгоритмов")
        button = next(w for w in descendants(dialog) if isinstance(w, tk.Button) and w.cget("text") == "Добавить")
        button.invoke()
        root.update()
        assert len(app.rows) == 1
        assert not app.empty.winfo_manager()
        a = app.categories[0]["id"]
        b = store.save_category("Тест математики", COLORS[1])
        app.reload_categories()
        app.toggle(a)
        clock.advance(65)
        app.tick()
        root.update()
        assert app.total.cget("text") == "00:01:05"
        assert app.rows[a]["daily"].cget("text") == "00:01:05"
        original_row = app.rows[b]["row"]
        app.rows[b]["start"].invoke()
        clock.advance(10)
        app.tick()
        app.play.invoke()
        assert timer.active is None
        assert timer.category_time(a) == 65
        assert timer.category_time(b) == 10
        assert app.rows[b]["row"] is original_row
        assert "Пауза" in app.session.cget("text")
        app.change_day(-1)
        assert app.total.cget("text") == "00:00:00"
        app.today()
        assert app.total.cget("text") == "00:01:15"
        app.toggle(a)
        clock.advance(2)
        # Invoke the real window-manager close protocol: it must hide, not stop.
        root.tk.call(root.protocol("WM_DELETE_WINDOW"))
        root.update()
        assert root.state() == "withdrawn"
        assert not app.closed and timer.active == a
        clock.advance(23)
        app.tick()
        assert timer.category_time(a) == 90
        app.show()
        root.update()
        assert root.state() == "normal"
        assert timer.active == a
        app.play.invoke()
        assert timer.active is None
        for index in range(15):
            store.save_category(f"Тест {index}", COLORS[index % len(COLORS)])
        app.reload_categories()
        root.update()
        before = app.list.canvas.yview()
        app.list.scroll_delta(-240)
        root.update()
        after = app.list.canvas.yview()
        assert after[0] > before[0]
        report = app.native.report()
        assert report["raw_hook"] and report["subclassed_windows"] > 0
        app.close()
        db = Store(folder / "test.sqlite3")
        assert sum(db.totals().values()) == 100
        db.close()
        return dict(empty_state=True, add_dialog=True, start_pause=True, switch=True,
                    counters=True, history=True, scrolling=True, native_scroll=True,
                    persistence=True, rows_reused=True, close_hides=True,
                    hidden_timer_continues=True, show_same_timer=True)


if __name__ == "__main__":
    result = main()
    (Path(__file__).parent / "gui-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
