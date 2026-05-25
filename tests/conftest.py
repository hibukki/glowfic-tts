import json
from pathlib import Path

import pytest

from glowfic_tts.api import RawApiPost, RawApiReply, RawPost
from glowfic_tts.models import Coverage

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def raw_api_post() -> RawApiPost:
    return RawApiPost.model_validate(_load("post_7508.json"))


@pytest.fixture
def raw_api_replies() -> list[RawApiReply]:
    return [RawApiReply.model_validate(r) for r in _load("replies_7508_p1.json")]


@pytest.fixture
def raw_post(raw_api_post, raw_api_replies) -> RawPost:
    return RawPost(
        coverage=Coverage.of(len(raw_api_replies)),
        post=raw_api_post,
        replies=raw_api_replies,
    )
