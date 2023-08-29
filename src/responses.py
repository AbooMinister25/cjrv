import json
from pathlib import Path

import requests

from schemas import FormResponse
from settings import settings


def get_responses() -> list[FormResponse]:
    cookies = {"token": settings.forms_api_key}
    responses = requests.get(f"{settings.responses_api_url}/responses", cookies=cookies).json()

    if settings.only_show_confirmed:
        confirmed = requests.get(f"{settings.confirmed_api_url}/responses", cookies=cookies).json()
        confirmed_ids = [c["user"]["id"] for c in confirmed]
        ret = [FormResponse(**i) for i in responses if i["user"]["id"] in confirmed_ids]
    else:
        ret = [FormResponse(**i) for i in responses]

    filename = Path(__file__).parent.absolute() / "chatgpt_response.json"
    with open(filename, "r") as f:
        chatgpt_response = json.load(f)

    ret.append(FormResponse(**chatgpt_response))
    return ret
