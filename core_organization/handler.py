"""Main lambda handler for the core-organization package."""

from typing import Callable
from typing import Any

import core_logging as log

from .response import send_response

from .scp import (
    create_service_control_policy,
    update_service_control_policy,
    delete_service_control_policy,
    create_service_control_policy_attachment,
    update_service_control_policy_attachment,
    delete_service_control_policy_attachment,
)

from .units import (
    create_organizational_unit,
    update_organizational_unit,
    delete_organizational_unit,
)

organizational_unit: dict[str, Callable] = {
    "Create": create_organizational_unit,
    "Update": update_organizational_unit,
    "Delete": delete_organizational_unit,
}


# Action mapper
service_control_policy: dict[str, Callable] = {
    "Create": create_service_control_policy,
    "Update": update_service_control_policy,
    "Delete": delete_service_control_policy,
}

service_control_policy_attachment: dict[str, Callable] = {
    "Create": create_service_control_policy_attachment,
    "Update": update_service_control_policy_attachment,
    "Delete": delete_service_control_policy_attachment,
}

actionmap: dict[str, dict] = {
    "Custom::ServiceControlPolicy": service_control_policy,
    "Custom::ServiceControlPolicyAttachment": service_control_policy_attachment,
    "Custom::OrganizationalUnit": organizational_unit,
}


def handler(event: dict, context: Any):

    log.info("REQUEST RECEIVED:", details=event)

    try:
        resource_type = event.get("ResourceType", "")
        map = actionmap.get(resource_type, None)
        if map is None:
            raise ValueError(f"Unexpected resource type [{resource_type}]!")

        request_type = event.get("RequestType", "")
        fn = map.get(request_type, None)
        if fn is None:
            raise ValueError(
                f"Resource [{request_type}] has no function [{request_type}]!"
            )

        fn(event, context)

    except Exception as e:
        log.error("FAILED: ", e)
        send_response(
            event,
            context,
            "FAILED",
            {"Message": "Unexpected event received from CloudFormation"},
            "",
        )
