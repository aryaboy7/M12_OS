# M12 OS Drawing Screen - shared UI scale version

import json
from pathlib import Path

from kivy.graphics import Color, Line, Rectangle
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout

from utils.ui_scale import (
    button_font,
    list_font,
    text_font,
    input_font,
    status_font,
    row_height,
    button_height,
    input_height,
    padding_size,
    spacing_size,
)


BASE_DIR = Path(__file__).resolve().parent.parent
DRAWINGS_DIR = BASE_DIR / "data" / "drawings"
DRAWINGS_DIR.mkdir(parents=True, exist_ok=True)


class DrawingCanvas(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.strokes = []
        self.current_color = (0, 0, 0, 1)
        self.current_width = 3
        self.current_points = None
        self.current_line = None

        with self.canvas.before:
            Color(1, 1, 1, 1)
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)

        self.bind(pos=self.update_bg, size=self.update_bg)

    def update_bg(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False

        self.current_points = [touch.x, touch.y]

        with self.canvas:
            Color(*self.current_color)
            self.current_line = Line(
                points=self.current_points,
                width=self.current_width
            )
        return True

    def on_touch_move(self, touch):
        if self.current_line is None:
            return False

        self.current_points += [touch.x, touch.y]
        self.current_line.points = self.current_points
        return True

    def on_touch_up(self, touch):
        if self.current_line is None:
            return False

        self.strokes.append({
            "color": list(self.current_color),
            "width": self.current_width,
            "points": list(self.current_points)
        })

        self.current_line = None
        self.current_points = None
        return True

    def redraw(self):
        self.canvas.clear()

        with self.canvas.before:
            Color(1, 1, 1, 1)
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)

        for s in self.strokes:
            with self.canvas:
                Color(*s["color"])
                Line(points=s["points"], width=s["width"])

    def undo(self):
        if self.strokes:
            self.strokes.pop()
            self.redraw()

    def clear_all(self):
        self.strokes = []
        self.canvas.clear()

        with self.canvas.before:
            Color(1, 1, 1, 1)
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)

    def save_file(self, path):
        path.write_text(json.dumps({"strokes": self.strokes}), encoding="utf-8")

    def load_file(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        self.strokes = data.get("strokes", [])
        self.redraw()


class DrawingScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.current_file = None

        root = BoxLayout(orientation="vertical", spacing=spacing_size(), padding=padding_size())

        top = BoxLayout(size_hint=(1, None), height=button_height(), spacing=spacing_size())

        for txt, cb in [
            ("Back", self.go_back),
            ("Open", self.open_dialog),
            ("Save", self.save_dialog),
            ("Undo", self.undo),
            ("Clear", self.clear_canvas),
        ]:
            b = Button(text=txt, font_size=button_font())
            b.bind(on_press=cb)
            top.add_widget(b)

        root.add_widget(top)

        colors = BoxLayout(size_hint=(1, None), height=button_height(), spacing=spacing_size())
        for clr in [
            (0,0,0,1),
            (1,0,0,1),
            (0,1,0,1),
            (0,0,1,1),
            (1,1,0,1),
            (1,1,1,1),
        ]:
            b = Button(
                text="",
                background_normal="",
                background_color=clr
            )
            b.bind(on_press=lambda inst, c=clr: self.set_color(c))
            colors.add_widget(b)
        root.add_widget(colors)

        brushes = BoxLayout(size_hint=(1, None), height=button_height(), spacing=spacing_size())
        for txt, w in [("S",2),("M",4),("L",8)]:
            b = Button(text=txt, font_size=button_font())
            b.bind(on_press=lambda inst, width=w: self.set_brush(width))
            brushes.add_widget(b)
        root.add_widget(brushes)

        self.canvas_widget = DrawingCanvas()
        root.add_widget(self.canvas_widget)

        self.add_widget(root)

    def set_color(self, color):
        self.canvas_widget.current_color = color

    def set_brush(self, width):
        self.canvas_widget.current_width = width

    def undo(self, *a):
        self.canvas_widget.undo()

    def clear_canvas(self, *a):
        self.canvas_widget.clear_all()

    def save_dialog(self, *a):
        box = BoxLayout(orientation="vertical", spacing=spacing_size(), padding=padding_size())
        inp = TextInput(
            text=self.current_file.stem if self.current_file else "",
            multiline=False,
            font_size=input_font(),
            size_hint=(1, None),
            height=input_height(),
            use_bubble=False,
            use_handles=False
        )
        box.add_widget(inp)

        row = BoxLayout(size_hint=(1, None), height=button_height(), spacing=spacing_size())
        pop = Popup(title="Save Drawing", content=box, size_hint=(0.88, 0.45))

        def do_save(*x):
            name = inp.text.strip() or "Drawing"
            path = DRAWINGS_DIR / f"{name}.drw"
            self.canvas_widget.save_file(path)
            self.current_file = path
            pop.dismiss()

        btn = Button(text="Save", font_size=button_font(), background_normal="", background_color=(0.12, 0.20, 0.35, 1))
        btn.bind(on_press=do_save)
        row.add_widget(btn)
        box.add_widget(row)
        pop.open()

    def make_unique_path(self, path):
        path = Path(path)

        if not path.exists():
            return path

        parent = path.parent
        stem = path.stem
        suffix = path.suffix

        for i in range(1, 1000):
            candidate = parent / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                return candidate

        return parent / f"{stem}_copy{suffix}"

    def clean_filename(self, name):
        name = str(name).strip()

        if not name:
            return ""

        bad = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]
        for ch in bad:
            name = name.replace(ch, "_")

        if name.lower().endswith(".drw"):
            name = name[:-4]

        return name.strip()

    def open_dialog(self, *a):
        main = BoxLayout(orientation="vertical", spacing=spacing_size(), padding=padding_size())

        list_layout = GridLayout(cols=1, size_hint_y=None, spacing=spacing_size())
        list_layout.bind(minimum_height=list_layout.setter("height"))

        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        scroll.add_widget(list_layout)
        main.add_widget(scroll)

        bottom = BoxLayout(size_hint=(1, None), height=button_height(), spacing=spacing_size())

        pop = Popup(
            title="Open Drawing",
            content=main,
            size_hint=(0.90, 0.85)
        )

        close_btn = Button(text="Cancel", font_size=button_font())
        close_btn.bind(on_press=lambda inst: pop.dismiss())
        bottom.add_widget(close_btn)
        main.add_widget(bottom)

        files = sorted(DRAWINGS_DIR.glob("*.drw"))

        if not files:
            list_layout.add_widget(Button(
                text="No drawings saved",
                font_size=button_font(),
                size_hint_y=None,
                height=row_height(),
                disabled=True
            ))

        for f in files:
            row = BoxLayout(size_hint_y=None, height=row_height(), spacing=spacing_size())

            open_btn = Button(
                text=f.name,
                font_size=list_font(),
                background_normal="",
                background_color=(0.10, 0.15, 0.25, 1)
            )

            def open_file(inst, path=f):
                try:
                    self.canvas_widget.load_file(path)
                    self.current_file = path
                    pop.dismiss()
                except Exception as e:
                    pop.title = f"Open failed: {e}"

            open_btn.bind(on_press=open_file)

            ren_btn = Button(
                text="Rename",
                font_size=status_font(),
                size_hint=(0.25, 1),
                background_normal="",
                background_color=(0.12, 0.20, 0.35, 1)
            )
            ren_btn.bind(on_press=lambda inst, p=f, parent_popup=pop: self.rename_dialog(p, parent_popup))

            del_btn = Button(
                text="Delete",
                font_size=status_font(),
                size_hint=(0.25, 1),
                background_normal="",
                background_color=(0.35, 0.12, 0.12, 1)
            )
            del_btn.bind(on_press=lambda inst, p=f, parent_popup=pop: self.delete_confirm(p, parent_popup))

            row.add_widget(open_btn)
            row.add_widget(ren_btn)
            row.add_widget(del_btn)
            list_layout.add_widget(row)

        pop.open()

    def rename_dialog(self, old_path, parent_popup=None):
        old_path = Path(old_path)

        box = BoxLayout(orientation="vertical", spacing=spacing_size(), padding=padding_size())

        inp = TextInput(
            text=old_path.stem,
            multiline=False,
            font_size=input_font(),
            use_bubble=False,
            use_handles=False
        )
        box.add_widget(inp)

        status = Button(
            text="Enter new drawing name",
            font_size=status_font(),
            disabled=True,
            size_hint=(1, 0.25)
        )
        box.add_widget(status)

        buttons = BoxLayout(size_hint=(1, 0.30), spacing=spacing_size())

        pop = Popup(
            title=f"Rename {old_path.name}",
            content=box,
            size_hint=(0.85, 0.45)
        )

        def do_rename(instance):
            try:
                new_name = self.clean_filename(inp.text)

                if not new_name:
                    status.text = "Name is empty."
                    return

                new_path = old_path.parent / f"{new_name}.drw"

                if new_path == old_path:
                    pop.dismiss()
                    return

                if new_path.exists():
                    status.text = "File already exists."
                    return

                old_path.rename(new_path)

                if self.current_file == old_path:
                    self.current_file = new_path

                pop.dismiss()

                if parent_popup:
                    parent_popup.dismiss()
                    self.open_dialog()

            except Exception as e:
                status.text = f"Rename failed: {e}"

        rename_btn = Button(
            text="Rename",
            font_size=button_font(),
            background_normal="",
            background_color=(0.12, 0.20, 0.35, 1)
        )
        rename_btn.bind(on_press=do_rename)

        cancel_btn = Button(
            text="Cancel",
            font_size=button_font(),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        cancel_btn.bind(on_press=lambda inst: pop.dismiss())

        buttons.add_widget(rename_btn)
        buttons.add_widget(cancel_btn)
        box.add_widget(buttons)

        pop.open()

    def delete_confirm(self, path, parent_popup=None):
        path = Path(path)

        box = BoxLayout(orientation="vertical", spacing=spacing_size(), padding=padding_size())

        warning = Button(
            text=f"Delete?\n{path.name}",
            font_size=button_font(),
            disabled=True,
            size_hint=(1, 0.55)
        )
        box.add_widget(warning)

        buttons = BoxLayout(size_hint=(1, 0.35), spacing=spacing_size())

        pop = Popup(
            title="Confirm Delete",
            content=box,
            size_hint=(0.85, 0.45)
        )

        def do_delete(instance):
            try:
                if path.exists():
                    path.unlink()

                if self.current_file == path:
                    self.current_file = None
                    self.canvas_widget.clear_all()

                pop.dismiss()

                if parent_popup:
                    parent_popup.dismiss()
                    self.open_dialog()

            except Exception as e:
                warning.text = f"Delete failed:\n{e}"

        yes_btn = Button(
            text="Delete",
            font_size=button_font(),
            background_normal="",
            background_color=(0.35, 0.12, 0.12, 1)
        )
        yes_btn.bind(on_press=do_delete)

        cancel_btn = Button(
            text="Cancel",
            font_size=button_font(),
            background_normal="",
            background_color=(0.10, 0.15, 0.25, 1)
        )
        cancel_btn.bind(on_press=lambda inst: pop.dismiss())

        buttons.add_widget(yes_btn)
        buttons.add_widget(cancel_btn)
        box.add_widget(buttons)

        pop.open()


    def go_back(self, *a):
        self.manager.current = "home"
