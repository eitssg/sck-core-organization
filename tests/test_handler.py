import os
from types import SimpleNamespace
import json
import pytest

import core_organization.handler as handler

import core_helper.aws as aws


@pytest.fixture
def context():

    d = {"key1": "value1", "log_stream_name": "value2"}
    context = SimpleNamespace(**d)

    return context


@pytest.fixture
def real_aws(pytestconfig):
    return pytestconfig.getoption("--real-aws")


def test_handler(context):

    fn = os.path.join(os.path.dirname(__file__), "test-create-scp.json")

    with open(fn, "r") as stream:
        d = json.load(stream)

    d["Identity"] = aws.get_identity()

    credentials = aws.get_session_credentials()

    d["Credentials"] = credentials["SessionToken"]

    response = handler.handler(d, context)

    print(json.dumps(response, indent=2))
