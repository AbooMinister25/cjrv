import re

from thefuzz import process

from schemas import FormResponse

QUERY_REGEX = re.compile(r"\w+:\w+:?\w+")


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
