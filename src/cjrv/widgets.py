from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Tree

from .responses import get_responses


class ResponseTree(Widget):
    """A tree of responses"""

    class ResponseSelected(Message):
        """Selected response"""

        def __init__(self, label, data):
            self.label = label
            self.data = data
            super().__init__()

    def __init__(self, id):
        self.responses = get_responses()

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
