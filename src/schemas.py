from dataclasses import dataclass
from typing import TypedDict


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
