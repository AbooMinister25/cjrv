import difflib
import itertools
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TypedDict

import requests
from dotenv import load_dotenv
from rich.syntax import Syntax
from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import var
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Pretty,
    Static,
    TabbedContent,
    TabPane,
    Tree,
)
from thefuzz import process

load_dotenv()


class MissingToken(Exception):
    pass


token = os.getenv("FORMS_API_TOKEN")

if not token:
    raise MissingToken("Environment variable FORMS_API_TOKEN must be set")

cookies = {"token": token}


QUERY_REGEX = re.compile(r"\w+:\w+:?\w+")


class User(TypedDict):
    username: str
    id: str
    discriminator: str
    avatar: str
    bot: str | None
    system: str | None
    locale: str | None
    verified: str | None
    email: str | None
    flags: int
    premium_type: str | None
    public_flags: int
    admin: bool


class AntiSpam(TypedDict):
    ip_hash: str
    user_agent_hash: str
    captcha_pass: bool


class Qualifier(TypedDict):
    value: str
    passed: bool
    failures: list


class Response(TypedDict):
    age_range: str
    timezone_explainer: bool
    timezone: str
    python_experience: str
    git_experience: str
    team_leader: str
    code_jam_experience: str
    qualifier_text: bool
    qualifier: Qualifier


@dataclass
class FormResponse:
    id: str
    user: User
    antispam: AntiSpam
    response: Response
    form_id: str
    timestamp: str


@dataclass
class Marked:
    """Represent responses marked as plagiarized or AI-generated"""

    plagiarized: list[FormResponse] = field(default_factory=list)
    generated: list[FormResponse] = field(default_factory=list)


marked = Marked()


class ConfirmPlagiarism(Screen):
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


class ConfirmGenerated(Screen):
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


class FlaggedView(Screen):
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


class DiffView(Screen):
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


class FilterView(Screen):
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


class DiffAllView(Screen):
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

        try:
            min_ratio = float(query)

            if 1 > min_ratio > 0:
                raise ValueError("Ratio should be between 0 and 1")
        except ValueError:
            label = self.query_one("#fprompt", Static)
            label.update("Invalid ratio - make sure it's a float in the range [0, 1]")
            message.input.value = ""
            return

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


class ResponseTree(Widget):
    """A tree of responses"""

    class ResponseSelected(Message):
        """Selected response"""

        def __init__(self, label, data):
            self.label = label
            self.data = data
            super().__init__()

    def __init__(self, id):
        r = requests.get(
            "https://forms-api.pythondiscord.com/forms/cj10-2023-qualifier/responses",
            cookies=cookies,
        )
        participating = requests.get(
            "https://forms-api.pythondiscord.com/forms/cj10-2023-participation-confirmation/responses",
            cookies=cookies,
        ).json()

        participating_ids = [p["user"]["id"] for p in participating]

        self.responses = [
            FormResponse(**i) for i in r.json() if i["user"]["id"] in participating_ids
        ]

        filename = Path(__file__).parent.absolute() / "chatgpt_response.json"
        with open(filename, "r") as f:
            chatgpt_respose = json.load(f)

        self.responses.append(FormResponse(**chatgpt_respose))

        super().__init__(id=id)

    def compose(self) -> ComposeResult:
        tree = Tree("responses")
        tree.root.expand()

        for response in self.responses:
            tree.root.add_leaf(response.user["username"], data=response)

        yield tree

    def on_tree_node_selected(self, event):
        if event.node.data is not None:
            self.post_message(self.ResponseSelected(event.node.label, event.node.data))


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

    def on_response_tree_response_selected(self, message: ResponseTree.ResponseSelected):
        code_view = self.query_one("#code", Static)
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


def filter_responses(query: str, responses: list[FormResponse]) -> list[FormResponse]:
    query = query.replace(" ", "")
    if not QUERY_REGEX.match(query):
        raise ValueError("Invalid query")

    match query.split(":"):
        case ["username" | "user", username]:
            usernames = [r.user["username"] for r in responses]
            matches = [m[0] for m in process.extract(username, usernames, limit=10) if m[1] >= 75]
            return [r for r in responses if r.user["username"] in matches]
        case ["username" | "user", "exact", username]:
            return [r for r in responses if r.user["username"] == username]
        case ["response" | "res", response]:
            return [r for r in responses if response in r.response["qualifier"]["value"]]
        case ["response" | "res", "fuzzy", response]:
            qualifier_responses = [r.response["qualifier"]["value"] for r in responses]
            matches = [
                m[0] for m in process.extract(response, qualifier_responses, limit=10) if m[1] > 75
            ]
            return [r for r in responses if r.response["qualifier"]["value"] in matches]
        case ["response" | "res", "re" | "regex", pattern]:
            return [r for r in responses if re.search(pattern, r.response["qualifier"]["value"])]
        case _:
            return []


if __name__ == "__main__":
    app = Responses()
    app.run()

    print("Dumping flagged responses to flagged.json")
    with open("flagged.json", "w") as f:
        json.dump(asdict(marked), f)
