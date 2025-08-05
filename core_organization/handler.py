"""
Main Lambda handler for the core-organization package.

This Lambda function handles CloudFormation custom resource requests for AWS Organizations
resources including Service Control Policies, Policy Attachments, and Organizational Units.
It acts as a CloudFormation custom resource provider.

**Supported Resource Types:**
    - Custom::ServiceControlPolicy
    - Custom::ServiceControlPolicyAttachment
    - Custom::OrganizationalUnit

**Supported Operations:**
    - Create: Creates new AWS Organizations resources
    - Update: Updates existing AWS Organizations resources
    - Delete: Deletes AWS Organizations resources
"""

from typing import Callable, Any, Dict, Optional
import traceback

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

# Type alias for action functions
ActionFunction = Callable[[dict, Any], None]
ActionMap = Dict[str, ActionFunction]
ResourceMap = Dict[str, ActionMap]

# Action mappings for each resource type
ORGANIZATIONAL_UNIT_ACTIONS: ActionMap = {
    "Create": create_organizational_unit,
    "Update": update_organizational_unit,
    "Delete": delete_organizational_unit,
}

SERVICE_CONTROL_POLICY_ACTIONS: ActionMap = {
    "Create": create_service_control_policy,
    "Update": update_service_control_policy,
    "Delete": delete_service_control_policy,
}

SERVICE_CONTROL_POLICY_ATTACHMENT_ACTIONS: ActionMap = {
    "Create": create_service_control_policy_attachment,
    "Update": update_service_control_policy_attachment,
    "Delete": delete_service_control_policy_attachment,
}

# Master action mapper - maps CloudFormation resource types to their action handlers
RESOURCE_ACTION_MAP: ResourceMap = {
    "Custom::ServiceControlPolicy": SERVICE_CONTROL_POLICY_ACTIONS,
    "Custom::ServiceControlPolicyAttachment": SERVICE_CONTROL_POLICY_ATTACHMENT_ACTIONS,
    "Custom::OrganizationalUnit": ORGANIZATIONAL_UNIT_ACTIONS,
}

# Supported CloudFormation request types
SUPPORTED_REQUEST_TYPES = {"Create", "Update", "Delete"}
SUPPORTED_RESOURCE_TYPES = set(RESOURCE_ACTION_MAP.keys())


def validate_event(event: dict) -> tuple[str, str]:
    """
    Validate the CloudFormation event and extract required fields.

    :param event: CloudFormation custom resource event
    :type event: dict

    :returns: Tuple of (resource_type, request_type)
    :rtype: tuple[str, str]

    :raises ValueError: If event is missing required fields or has invalid values

    **Required Event Fields:**
        - ResourceType: CloudFormation resource type
        - RequestType: CloudFormation operation type

    **Example:**
        >>> validate_event({"ResourceType": "Custom::ServiceControlPolicy", "RequestType": "Create"})
        ("Custom::ServiceControlPolicy", "Create")
    """
    # Validate required fields exist
    if not isinstance(event, dict):
        raise ValueError("Event must be a dictionary")

    resource_type = event.get("ResourceType")
    if not resource_type:
        raise ValueError("Event missing required field 'ResourceType'")

    request_type = event.get("RequestType")
    if not request_type:
        raise ValueError("Event missing required field 'RequestType'")

    # Validate resource type is supported
    if resource_type not in SUPPORTED_RESOURCE_TYPES:
        supported = ", ".join(SUPPORTED_RESOURCE_TYPES)
        raise ValueError(f"Unsupported resource type '{resource_type}'. " f"Supported types: {supported}")

    # Validate request type is supported
    if request_type not in SUPPORTED_REQUEST_TYPES:
        supported = ", ".join(SUPPORTED_REQUEST_TYPES)
        raise ValueError(f"Unsupported request type '{request_type}'. " f"Supported types: {supported}")

    return resource_type, request_type


def get_action_function(resource_type: str, request_type: str) -> ActionFunction:
    """
    Get the appropriate action function for the given resource and request type.

    :param resource_type: CloudFormation resource type
    :type resource_type: str
    :param request_type: CloudFormation request type
    :type request_type: str

    :returns: Action function to handle the request
    :rtype: ActionFunction

    :raises ValueError: If no action function is found

    **Note:**
        The action function must follow the signature: ``(event: dict, context: Any) -> None``

    **Example:**
        >>> func = get_action_function("Custom::ServiceControlPolicy", "Create")
        >>> func.__name__
        'create_service_control_policy'
    """
    action_map = RESOURCE_ACTION_MAP.get(resource_type)
    if not action_map:
        raise ValueError(f"No action map found for resource type '{resource_type}'")

    action_function = action_map.get(request_type)
    if not action_function:
        available_actions = ", ".join(action_map.keys())
        raise ValueError(
            f"No action function found for '{request_type}' on resource '{resource_type}'. "
            f"Available actions: {available_actions}"
        )

    return action_function


def send_failure_response(event: dict, context: Any, error_message: str, physical_resource_id: Optional[str] = None) -> None:
    """
    Send a failure response to CloudFormation.

    :param event: Original CloudFormation event
    :type event: dict
    :param context: Lambda context
    :type context: Any
    :param error_message: Error message to include in response
    :type error_message: str
    :param physical_resource_id: Optional physical resource ID
    :type physical_resource_id: Optional[str]

    :returns: None
    :rtype: None

    **Response Structure:**
        The function sends a FAILED response to CloudFormation with the following structure:

        .. code-block:: json

            {
                "Status": "FAILED",
                "Reason": "error_message",
                "PhysicalResourceId": "physical_resource_id",
                "Data": {
                    "Message": "error_message"
                }
            }

    **Note:**
        If sending the failure response itself fails, the error is logged but not re-raised
        to prevent infinite loops.
    """
    try:
        log.error(
            "Sending failure response to CloudFormation",
            details={
                "error_message": error_message,
                "resource_type": event.get("ResourceType", "Unknown"),
                "request_type": event.get("RequestType", "Unknown"),
                "stack_id": event.get("StackId", "Unknown"),
                "logical_resource_id": event.get("LogicalResourceId", "Unknown"),
            },
        )

        send_response(
            event=event,
            context=context,
            response_status="FAILED",
            response_data={"Message": error_message},
            physical_resource_id=physical_resource_id or "",
        )
    except Exception as response_error:
        log.error(
            "Failed to send failure response to CloudFormation",
            details={"original_error": error_message, "response_error": str(response_error)},
        )


def handler(event: dict, context: Any) -> None:
    """
    Main Lambda handler for AWS Organizations CloudFormation custom resources.

    This function processes CloudFormation custom resource events for AWS Organizations
    resources and delegates to the appropriate action handlers.

    :param event: CloudFormation custom resource event
    :type event: dict
    :param context: AWS Lambda context object
    :type context: Any

    :returns: None - Function communicates with CloudFormation via HTTP response to ResponseURL
    :rtype: None

    :raises Exception: All exceptions are caught and converted to CloudFormation failure responses

    **CloudFormation Event Structure:**
        The event parameter contains the following fields:

        .. code-block:: json

            {
                "RequestType": "Create|Update|Delete",
                "ResourceType": "Custom::ServiceControlPolicy|Custom::ServiceControlPolicyAttachment|Custom::OrganizationalUnit",
                "StackId": "arn:aws:cloudformation:region:account:stack/stack-name/guid",
                "LogicalResourceId": "MyResource",
                "PhysicalResourceId": "physical-id-if-update-or-delete",
                "ResourceProperties": {
                    "PropertyName": "PropertyValue"
                },
                "ResponseURL": "https://cloudformation-custom-resource-response-..."
            }

    **Supported Resource Types:**
        - ``Custom::ServiceControlPolicy``: Manages AWS Organizations Service Control Policies
        - ``Custom::ServiceControlPolicyAttachment``: Manages SCP attachments to OUs/accounts
        - ``Custom::OrganizationalUnit``: Manages AWS Organizations Organizational Units

    **Request Flow:**
        1. Validate event structure and extract required fields
        2. Determine appropriate action function based on resource type and request type
        3. Execute action function (function handles CloudFormation response)
        4. Log completion status

    **Error Handling:**
        - Validation errors result in immediate failure response to CloudFormation
        - Unexpected errors are logged with full traceback and failure response sent
        - Action functions are responsible for their own success responses

    **Example Usage:**
        This handler is typically invoked by CloudFormation when deploying templates with
        custom resources:

        .. code-block:: yaml

            MyServiceControlPolicy:
              Type: Custom::ServiceControlPolicy
              Properties:
                ServiceToken: !GetAtt CoreOrganizationLambda.Arn
                PolicyName: "RestrictHighRiskServices"
                PolicyDocument:
                  Version: "2012-10-17"
                  Statement:
                    - Effect: Deny
                      Action: "ec2:TerminateInstances"
                      Resource: "*"
    """
    log.info(
        "CloudFormation custom resource request received",
        details={
            "request_type": event.get("RequestType", "Unknown"),
            "resource_type": event.get("ResourceType", "Unknown"),
            "logical_resource_id": event.get("LogicalResourceId", "Unknown"),
            "stack_id": event.get("StackId", "Unknown"),
            "event": event,
        },
    )

    try:
        # Validate event structure and extract required fields
        resource_type, request_type = validate_event(event)

        log.debug("Event validation successful", details={"resource_type": resource_type, "request_type": request_type})

        # Get the appropriate action function
        action_function = get_action_function(resource_type, request_type)

        log.info(
            "Executing action",
            details={"resource_type": resource_type, "request_type": request_type, "function_name": action_function.__name__},
        )

        # Execute the action function
        # Note: Action functions are responsible for sending success responses to CloudFormation
        action_function(event, context)

        log.info("Action completed successfully", details={"resource_type": resource_type, "request_type": request_type})

    except ValueError as validation_error:
        # Handle validation errors (bad input)
        error_message = f"Validation error: {str(validation_error)}"
        log.error("Event validation failed", details={"error": str(validation_error), "event": event})
        send_failure_response(event, context, error_message)

    except Exception as unexpected_error:
        # Handle all other unexpected errors
        error_message = f"Unexpected error processing CloudFormation request: {str(unexpected_error)}"

        log.error(
            "Unexpected error in handler",
            details={
                "error": str(unexpected_error),
                "error_type": type(unexpected_error).__name__,
                "traceback": traceback.format_exc(),
                "event": event,
            },
        )

        send_failure_response(event, context, error_message)


# Export the supported resource types for external reference
__all__ = ["handler", "SUPPORTED_REQUEST_TYPES", "SUPPORTED_RESOURCE_TYPES", "RESOURCE_ACTION_MAP"]
