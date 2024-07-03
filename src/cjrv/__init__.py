import json
from dataclasses import asdict

from rich.syntax import Syntax
from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, VerticalScroll
from textual.reactive import var
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    Pretty,
    Static,
    TabbedContent,
    TabPane,
)

from .marked import marked
from .schemas import FormResponse
from .views import DiffAllView, DiffView, FilterView, FlaggedView, SelectedDiffView
from .widgets import ResponseTree


class ConfirmPlagiarism(Screen[None]):
    def __init__(self, form: FormResponse):
        self.form = form
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Flag as plagiarism?", id="question"),
            Button("Yes", variant="primary", id="yes"),
            Button("Cancel", variant="warning", id="no"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            marked.plagiarized.append(self.form)

        self.app.pop_screen()


class ConfirmGenerated(Screen[None]):
    def __init__(self, form: FormResponse):
        self.form = form
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Flag as AI generated?", id="question"),
            Button("Yes", variant="primary", id="yes"),
            Button("Cancel", variant="warning", id="no"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            marked.generated.append(self.form)

        self.app.pop_screen()


class Responses(App):
    CSS_PATH = "responses.css"
    BINDINGS = [
        ("t", "toggle_tree", "Toggle Tree"),
        ("q", "quit", "Quit"),
        ("p", "flag_plagiarism", "Flag as Plagiarism"),
        ("g", "flag_generated", "Flag as AI Generated"),
        ("v", "view_flagged", "View Flagged Responses"),
        ("d", "show_diff", "Compare files"),
        ("f", "filter", "Filter Respones"),
        ("o", "diff_all", "Diff All Responses"),
    ]

    show_tree = var(True)
    currently_selected = var(None)

    def watch_show_tree(self, show_tree: bool):
        self.set_class(show_tree, "-show-tree")

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal():
            r = ResponseTree(id="tree-view")
            self.responses = r.responses
            yield r
            with TabbedContent():
                with TabPane("Response Code"):
                    with VerticalScroll(id="code-view"):
                        yield Static(id="code", expand=True)
                with TabPane("Form Details"):
                    yield Pretty("", id="form-info")

        yield Footer()

    def on_response_tree_response_selected(
        self, message: ResponseTree.ResponseSelected
    ):
        code_view = self.query_one("#code", Static)

        if isinstance(message.data, tuple):
            self.push_screen(SelectedDiffView(message.data[0], message.data[1]))
        else:
            code = message.data.response["qualifier"]["value"]
            syntax = Syntax(code, "python", line_numbers=True)

            code_view.update(syntax)
            self.sub_title = message.label

            form_info = self.query_one("#form-info", Pretty)
            form_info.update(asdict(message.data))

            self.currently_selected = message.data

    def action_toggle_tree(self) -> None:
        """Called in response to key binding."""
        self.show_tree = not self.show_tree

    def action_flag_plagiarism(self) -> None:
        """Called in response to key binding"""
        if self.currently_selected is not None:
            self.push_screen(ConfirmPlagiarism(self.currently_selected))

    def action_flag_generated(self) -> None:
        """Called in response to key binding"""
        if self.currently_selected is not None:
            self.push_screen(ConfirmGenerated(self.currently_selected))

    def action_view_flagged(self) -> None:
        """Called in response to key binding"""
        if isinstance(self.screen, FlaggedView):
            self.pop_screen()
        else:
            self.push_screen(FlaggedView())

    def action_show_diff(self) -> None:
        """Called in response to key binding"""
        if isinstance(self.screen, DiffView):
            self.pop_screen()
        else:
            self.push_screen(DiffView(self.responses))

    def action_diff_all(self) -> None:
        """Called in response to key binding"""
        if isinstance(self.screen, DiffAllView):
            self.pop_screen()
        else:
            self.push_screen(DiffAllView(self.responses))

    def action_filter(self) -> None:
        """Called in response to key binding"""
        if isinstance(self.screen, FilterView):
            self.pop_screen()
        else:
            self.push_screen(FilterView(self.responses))

    def on_mount(self, _) -> None:
        self.query_one(ResponseTree).focus()


def main() -> None:
    app = Responses()
    app.run()

    print("Dumping flagged responses to flagged.json")
    with open("flagged.json", "w") as f:
        json.dump(asdict(marked), f)
