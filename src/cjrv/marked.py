from dataclasses import dataclass, field

from .schemas import FormResponse


@dataclass
class Marked:
    """Represent responses marked as plagiarized or AI-generated"""

    plagiarized: list[FormResponse] = field(default_factory=list)
    generated: list[FormResponse] = field(default_factory=list)


marked = Marked()
