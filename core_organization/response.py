"""
CloudFormation Custom Resource Response Module.

This module provides functionality to send HTTP responses back to CloudFormation
when processing custom resource requests. It handles the communication protocol
required by CloudFormation custom resources.

**CloudFormation Custom Resource Protocol:**
    When CloudFormation invokes a custom resource, it expects an HTTP PUT response
    to a pre-signed URL with specific JSON structure containing the operation status
    and any response data.

**Response Flow:**
    1. CloudFormation sends custom resource event to Lambda
    2. Lambda processes the request
    3. Lambda calls send_response() with results
    4. Function sends HTTP PUT to CloudFormation's ResponseURL
    5. CloudFormation continues stack operation based on response
"""

from typing import Any, Dict, Optional
from urllib.request import build_opener, HTTPHandler, Request
from urllib.error import HTTPError, URLError

import core_logging as log

import core_framework as util


def send_response(
    event: Dict[str, Any],
    context: Any,
    response_status: str,
    response_data: Dict[str, Any],
    physical_resource_id: str,
    no_echo: bool = False,
) -> None:
    """
    Send an HTTP response back to CloudFormation for a custom resource request.

    This function constructs and sends the required response to CloudFormation's
    pre-signed URL to indicate the success or failure of a custom resource operation.

    :param event: The original CloudFormation custom resource event
    :type event: Dict[str, Any]
    :param context: AWS Lambda context object containing execution information
    :type context: Any
    :param response_status: Status of the custom resource operation
    :type response_status: str
    :param response_data: Data to return to CloudFormation template
    :type response_data: Dict[str, Any]
    :param physical_resource_id: Unique identifier for the custom resource instance
    :type physical_resource_id: str
    :param no_echo: Whether to mask the response data in CloudFormation console
    :type no_echo: bool

    :returns: None
    :rtype: None

    :raises HTTPError: If the HTTP request to CloudFormation fails
    :raises URLError: If there are network connectivity issues
    :raises KeyError: If required fields are missing from the event
    :raises Exception: For other unexpected errors during response sending

    **Response Status Values:**
        - ``SUCCESS``: The custom resource operation completed successfully
        - ``FAILED``: The custom resource operation failed

    **Required Event Fields:**
        The event parameter must contain the following CloudFormation-provided fields:

        - ``ResponseURL``: Pre-signed URL to send the response
        - ``StackId``: CloudFormation stack identifier
        - ``RequestId``: Unique identifier for this request
        - ``LogicalResourceId``: Logical ID of the resource in the template

    **Response Body Structure:**
        The function sends a JSON response with the following structure:

        .. code-block:: json

            {
                "Status": "SUCCESS|FAILED",
                "Reason": "Descriptive message with CloudWatch log reference",
                "PhysicalResourceId": "unique-resource-identifier",
                "StackId": "arn:aws:cloudformation:region:account:stack/name/id",
                "RequestId": "unique-request-id",
                "LogicalResourceId": "MyCustomResource",
                "NoEcho": false,
                "Data": {
                    "OutputKey1": "OutputValue1",
                    "OutputKey2": "OutputValue2"
                }
            }

    **Example Usage:**
        .. code-block:: python

            # Success response
            send_response(
                event=event,
                context=context,
                response_status="SUCCESS",
                response_data={"ResourceId": "my-resource-123"},
                physical_resource_id="my-resource-123"
            )

            # Failure response
            send_response(
                event=event,
                context=context,
                response_status="FAILED",
                response_data={"Message": "Resource creation failed"},
                physical_resource_id=""
            )

    **Error Handling:**
        The function logs all errors but does not re-raise them to prevent
        CloudFormation from hanging. If the response cannot be sent, CloudFormation
        will eventually timeout the operation.

    **Security Notes:**
        - The ResponseURL contains temporary credentials and should be treated securely
        - Response data may be visible in CloudFormation console unless no_echo=True
        - Log messages are written to CloudWatch Logs for debugging
    """
    try:
        # Validate required event fields
        required_fields = ["ResponseURL", "StackId", "RequestId", "LogicalResourceId"]
        missing_fields = [field for field in required_fields if field not in event]

        if missing_fields:
            raise KeyError(f"Missing required event fields: {missing_fields}")

        # Construct reason message with CloudWatch log reference
        log_stream_name = getattr(context, "log_stream_name", "unknown-log-stream")
        reason_message = f"See the details in CloudWatch Log Stream: {log_stream_name}"

        # Add custom message if provided in response_data
        if "Message" in response_data:
            reason_message += f"\n{response_data['Message']}"

        # Construct the response body according to CloudFormation specification
        response_body = {
            "Status": response_status,
            "Reason": reason_message,
            "PhysicalResourceId": physical_resource_id,
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
            "Data": response_data,
        }

        # Add NoEcho if specified
        if no_echo:
            response_body["NoEcho"] = True

        # Convert response to JSON
        response_body_json = util.to_json(response_body)

        log.info(
            "Sending CloudFormation response",
            details={
                "response_url": event["ResponseURL"],
                "status": response_status,
                "physical_resource_id": physical_resource_id,
                "logical_resource_id": event["LogicalResourceId"],
                "response_body": response_body_json,
            },
        )

        # Send HTTP PUT request to CloudFormation
        _send_http_response(event["ResponseURL"], response_body_json)

        log.info(
            "CloudFormation response sent successfully",
            details={
                "status": response_status,
                "physical_resource_id": physical_resource_id,
            },
        )

    except KeyError as key_error:
        log.error(
            "Missing required fields in CloudFormation event",
            details={
                "error": str(key_error),
                "event_keys": (
                    list(event.keys()) if isinstance(event, dict) else "not_dict"
                ),
            },
        )
        # Don't re-raise - let CloudFormation timeout to avoid hanging

    except (HTTPError, URLError) as http_error:
        log.error(
            "Failed to send response to CloudFormation",
            details={
                "error": str(http_error),
                "error_type": type(http_error).__name__,
                "response_url": event.get("ResponseURL", "unknown"),
                "status": response_status,
            },
        )
        # Don't re-raise - let CloudFormation timeout to avoid hanging

    except Exception as unexpected_error:
        log.error(
            "Unexpected error sending CloudFormation response",
            details={
                "error": str(unexpected_error),
                "error_type": type(unexpected_error).__name__,
                "status": response_status,
                "physical_resource_id": physical_resource_id,
            },
        )
        # Don't re-raise - let CloudFormation timeout to avoid hanging


def _send_http_response(response_url: str, response_body: str) -> None:
    """
    Send the actual HTTP PUT request to CloudFormation's ResponseURL.

    This is a private helper function that handles the low-level HTTP communication
    with CloudFormation's pre-signed URL.

    :param response_url: CloudFormation's pre-signed ResponseURL
    :type response_url: str
    :param response_body: JSON response body to send
    :type response_body: str

    :returns: None
    :rtype: None

    :raises HTTPError: If the HTTP request fails
    :raises URLError: If there are network connectivity issues

    **HTTP Request Details:**
        - Method: PUT
        - Content-Type: "" (empty as required by CloudFormation)
        - Body: JSON response data
        - Encoding: UTF-8

    **CloudFormation Requirements:**
        - Must use HTTP PUT method
        - Content-Type header must be empty string
        - Content-Length must be set correctly
        - Response body must be valid JSON
    """
    # Create HTTP opener with PUT support
    opener = build_opener(HTTPHandler)

    # Create PUT request with JSON body
    request = Request(
        response_url,
        data=response_body.encode(encoding="utf-8", errors="strict"),
    )

    # Set required headers for CloudFormation
    request.add_header("Content-Type", "")  # CloudFormation requires empty Content-Type
    request.add_header("Content-Length", str(len(response_body)))
    request.get_method = lambda: "PUT"  # Force PUT method

    # Send the request
    response = opener.open(request)

    log.debug(
        "HTTP response received from CloudFormation",
        details={
            "status_code": response.getcode(),
            "status_message": response.msg,
            "response_url": response_url,
        },
    )


def send_success_response(
    event: Dict[str, Any],
    context: Any,
    response_data: Optional[Dict[str, Any]] = None,
    physical_resource_id: Optional[str] = None,
) -> None:
    """
    Convenience function to send a SUCCESS response to CloudFormation.

    :param event: The original CloudFormation custom resource event
    :type event: Dict[str, Any]
    :param context: AWS Lambda context object
    :type context: Any
    :param response_data: Optional data to return to CloudFormation template
    :type response_data: Optional[Dict[str, Any]]
    :param physical_resource_id: Optional physical resource ID
    :type physical_resource_id: Optional[str]

    :returns: None
    :rtype: None

    **Example:**
        .. code-block:: python

            send_success_response(
                event=event,
                context=context,
                response_data={"BucketName": "my-created-bucket"},
                physical_resource_id="my-bucket-id"
            )
    """
    send_response(
        event=event,
        context=context,
        response_status="SUCCESS",
        response_data=response_data or {},
        physical_resource_id=physical_resource_id or event.get("LogicalResourceId", ""),
    )


def send_failure_response(
    event: Dict[str, Any],
    context: Any,
    error_message: str,
    physical_resource_id: Optional[str] = None,
) -> None:
    """
    Convenience function to send a FAILED response to CloudFormation.

    :param event: The original CloudFormation custom resource event
    :type event: Dict[str, Any]
    :param context: AWS Lambda context object
    :type context: Any
    :param error_message: Error message describing the failure
    :type error_message: str
    :param physical_resource_id: Optional physical resource ID
    :type physical_resource_id: Optional[str]

    :returns: None
    :rtype: None

    **Example:**
        .. code-block:: python

            send_failure_response(
                event=event,
                context=context,
                error_message="Failed to create S3 bucket: Access denied",
                physical_resource_id="failed-bucket-id"
            )
    """
    send_response(
        event=event,
        context=context,
        response_status="FAILED",
        response_data={"Message": error_message},
        physical_resource_id=physical_resource_id or "",
    )


# Export public functions
__all__ = ["send_response", "send_success_response", "send_failure_response"]
