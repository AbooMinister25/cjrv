import difflib
import itertools

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.reactive import var
from textual.screen import Screen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from .filter import filter_responses
from .marked import marked
from .schemas import FormResponse


class FlaggedView(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Plagiarized", classes="flabel"),
            Label("AI-Generated", classes="flabel"),
            ListView(
                *(
                    ListItem(Label(r.user["username"]), classes="lilabel")
                    for r in marked.plagiarized
                ),
                classes="flagged",
            ),
            ListView(
                *(ListItem(Label(r.user["username"]), classes="lilabel") for r in marked.generated),
                classes="flagged",
            ),
            id="flagged-view",
        )


class DiffView(Screen[None]):
    is_first = var(True)

    def __init__(self, responses: list[FormResponse]):
        self.responses = responses
        self.first_response = None
        self.second_response = None
        super().__init__()

    def compose(self) -> ComposeResult:
        items = []
        for response in self.responses:
            item = ListItem(Label(response.user["username"]))
            item.data = response
            items.append(item)

        yield Grid(
            Label("Select first response", id="prompt"),
            ListView(*items),
            Button("Show Diff", variant="primary", id="show"),
            Button("Cancel", variant="warning", id="cancel"),
            id="dialog",
        )

    def on_list_view_selected(self, selected):
        label = self.query_one("#prompt", Label)

        if self.is_first:
            self.first_response = selected.item.data
            label.update("Select second response")
            self.is_first = not self.is_first
        else:
            self.second_response = selected.item.data
            label.update("Both responses selected")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "show":
            if self.is_first:
                label = self.query_one("#prompt", Label)
                label.update("Please select your second response first.")
                return

            differ = difflib.Differ()
            html = differ.compare(
                self.first_response.response["qualifier"]["value"].splitlines(),
                self.second_response.response["qualifier"]["value"].splitlines(),
            )

            grid = self.query_one("#dialog", Grid)
            grid.remove()

            self.app.sub_title = (
                f"{self.first_response.user['username']} x {self.second_response.user['username']}"
            )

            self.mount(
                Static(
                    f"{self.first_response.user['username']} x {self.second_response.user['username']}",
                    id="diff_title",
                ),
                Static(Syntax("\n".join(html), "diff", line_numbers=True)),
                Button("Return", variant="warning", id="cancel"),
            )
        else:
            self.app.pop_screen()


class FilterView(Screen[None]):
    def __init__(self, responses: list[FormResponse]):
        self.responses = responses

        super().__init__()

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Filter your results in the format `filter:<type>:value`.", id="fprompt"),
            Input(placeholder="query"),
            ListView(id="results"),
            Button("Return", variant="warning", id="cancel"),
        )

    def on_input_submitted(self, message: Input.Changed):
        query = message.value

        try:
            filtered = filter_responses(query, self.responses)
        except ValueError:
            label = self.query_one("#fprompt", Static)
            label.update("Invalid query - make suer it's in the format `filter:value`")
            message.input.value = ""
            return

        list_view = self.query_one("#results", ListView)
        list_view.clear()
        message.input.value = ""

        for response in filtered:
            item = ListItem(Label(response.user["username"], classes="lilabel"))
            item.data = response
            list_view.append(item)

    def on_list_view_selected(self, message: ListView.Selected):
        self.app.post_message(
            ResponseTree.ResponseSelected(message.item.children[0].renderable, message.item.data)
        )

        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed):
        self.app.pop_screen()


class DiffAllView(Screen[None]):
    def __init__(self, responses: list[FormResponse]):
        self.responses = responses

        super().__init__()

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(
                "Enter the minimum ratio of similarity for responses to show up here (The ratio should be a float in the range [0, 1])",
                id="fprompt",
            ),
            Input(placeholder="query"),
            ListView(id="results"),
            Button("Return", variant="warning", id="cancel"),
        )

    def on_input_submitted(self, message: Input.Changed):
        query = message.value
        label = self.query_one("#fprompt", Static)

        try:
            min_ratio = float(query)

            if not 1 > min_ratio > 0:
                raise ValueError("Ratio should be between 0 and 1")
        except ValueError:
            label.update("Invalid ratio - make sure it's a float in the range [0, 1]")
            message.input.value = ""
            return

        label.update("Diffing...this may take a while")
        self.app.refresh()

        filtered: list[tuple[FormResponse, FormResponse]] = []
        matcher = difflib.SequenceMatcher()

        for first, second in itertools.combinations(self.responses, 2):
            matcher.set_seqs(
                first.response["qualifier"]["value"],
                second.response["qualifier"]["value"],
            )
            ratio = matcher.ratio()
            if ratio >= min_ratio:
                filtered.append((first, second))

        list_view = self.query_one("#results", ListView)
        list_view.clear()
        message.input.value = ""

        for response in filtered:
            item = ListItem(
                Label(
                    f"First: {response[0].user['username']} | Second: {response[1].user['username']}",
                    classes="lilabel",
                )
            )
            item.data = response
            list_view.append(item)

    def on_list_view_selected(self, message: ListView.Selected):
        self.app.post_message(
            ResponseTree.ResponseSelected(message.item.children[0].renderable, message.item.data)
        )

        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed):
        self.app.pop_screen()
