"""
AWS Organizations Service Control Policy Management Module.

This module provides comprehensive management of AWS Organizations Service Control Policies (SCPs)
and their attachments to organizational units, accounts, and roots. It handles the complexities
of AWS Organizations' eventual consistency model with robust retry mechanisms and validation.

**Supported Operations:**
    - Create Service Control Policy
    - Update Service Control Policy
    - Delete Service Control Policy
    - Create Service Control Policy Attachment
    - Update Service Control Policy Attachment
    - Delete Service Control Policy Attachment

**Key Features:**
    - Automatic retry logic for eventual consistency issues
    - Comprehensive validation of policy documents and targets
    - Intelligent handling of default policy attachments
    - Detailed logging for troubleshooting and audit trails
    - Graceful error handling with CloudFormation integration
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from time import sleep
from random import randint

import core_framework as util
import core_logging as log
import core_helper.aws as aws

from .response import send_success_response, send_failure_response

# Constants for AWS Organizations
DEFAULT_FULL_ACCESS_POLICY_ID = "p-FullAWSAccess"
MAX_RETRY_ATTEMPTS = 10
MIN_RETRY_DELAY = 5
MAX_RETRY_DELAY = 30
POLICY_TYPE_SCP = "SERVICE_CONTROL_POLICY"

# AWS Organizations ID patterns
ROOT_ID_PATTERN = re.compile(r"^r-[0-9a-z]{4,32}$")
ACCOUNT_ID_PATTERN = re.compile(r"^[0-9]{12}$")
OU_ID_PATTERN = re.compile(r"^ou-[0-9a-z]{4,32}-[0-9a-z]{8,32}$")
POLICY_ID_PATTERN = re.compile(r"^p-[0-9a-z]{4,32}$")


def validate_policy_document(policy_document: Any) -> str:
    """
    Validate and convert policy document to JSON string.

    :param policy_document: Policy document as dict or string
    :type policy_document: Any

    :returns: Valid JSON string representation of the policy
    :rtype: str

    :raises ValueError: If policy document is invalid
    """
    log.trace("Validating policy document")

    try:
        if isinstance(policy_document, str):
            # Validate it's valid JSON
            parsed = json.loads(policy_document)
            policy_json = policy_document
        elif isinstance(policy_document, dict):
            policy_json = json.dumps(policy_document, separators=(",", ":"))
            parsed = policy_document
        else:
            raise ValueError(f"Policy document must be dict or string, got {type(policy_document)}")

        # Validate required policy structure
        if not isinstance(parsed, dict):
            raise ValueError("Policy document must be a JSON object")

        if "Version" not in parsed:
            raise ValueError("Policy document missing required 'Version' field")

        if "Statement" not in parsed:
            raise ValueError("Policy document missing required 'Statement' field")

        if not isinstance(parsed["Statement"], list):
            raise ValueError("Policy 'Statement' must be an array")

        if len(parsed["Statement"]) == 0:
            raise ValueError("Policy must contain at least one statement")

        # Validate each statement has required fields
        for i, statement in enumerate(parsed["Statement"]):
            if not isinstance(statement, dict):
                raise ValueError(f"Statement {i} must be an object")

            if "Effect" not in statement:
                raise ValueError(f"Statement {i} missing required 'Effect' field")

            if statement["Effect"] not in ["Allow", "Deny"]:
                raise ValueError(f"Statement {i} Effect must be 'Allow' or 'Deny'")

        log.debug(
            "Policy document validation successful",
            details={"statement_count": len(parsed["Statement"]), "version": parsed["Version"]},
        )

        return policy_json

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in policy document: {str(e)}")
    except Exception as e:
        log.error("Policy document validation failed", details={"error": str(e), "policy_type": type(policy_document).__name__})
        raise


def validate_target_id(target_id: str, organizations_client: Any) -> str:
    """
    Validate and resolve target ID for policy attachment.

    :param target_id: Target ID (root, account, or OU ID)
    :type target_id: str
    :param organizations_client: AWS Organizations client
    :type organizations_client: Any

    :returns: Resolved and validated target ID
    :rtype: str

    :raises ValueError: If target ID is invalid or doesn't exist
    """
    log.trace("Validating target ID", details={"target_id": target_id})

    if not target_id:
        raise ValueError("Target ID cannot be empty")

    # Handle special "root" case
    if target_id.lower() == "root":
        log.debug("Resolving 'root' target to actual root ID")
        try:
            roots_response = organizations_client.list_roots()
            if not roots_response.get("Roots"):
                raise ValueError("No organizational roots found")

            root_id = roots_response["Roots"][0]["Id"]
            log.info("Resolved root target", details={"resolved_root_id": root_id})
            return root_id
        except Exception as e:
            raise ValueError(f"Failed to resolve root ID: {str(e)}")

    # Validate ID format
    if ROOT_ID_PATTERN.match(target_id):
        target_type = "root"
    elif ACCOUNT_ID_PATTERN.match(target_id):
        target_type = "account"
    elif OU_ID_PATTERN.match(target_id):
        target_type = "organizational_unit"
    else:
        raise ValueError(f"Invalid target ID format: {target_id}")

    # Verify target exists
    try:
        if target_type == "root":
            roots = organizations_client.list_roots()["Roots"]
            if not any(root["Id"] == target_id for root in roots):
                raise ValueError(f"Root {target_id} not found")
        elif target_type == "account":
            try:
                organizations_client.describe_account(AccountId=target_id)
            except organizations_client.exceptions.AccountNotFoundException:
                raise ValueError(f"Account {target_id} not found in organization")
        elif target_type == "organizational_unit":
            try:
                organizations_client.describe_organizational_unit(OrganizationalUnitId=target_id)
            except organizations_client.exceptions.OrganizationalUnitNotFoundException:
                raise ValueError(f"Organizational Unit {target_id} not found")

        log.debug("Target ID validation successful", details={"target_id": target_id, "target_type": target_type})

        return target_id

    except Exception as e:
        if "not found" in str(e).lower():
            raise
        raise ValueError(f"Failed to validate target {target_id}: {str(e)}")


def retry_with_backoff(func, *args, **kwargs) -> Any:
    """
    Execute function with exponential backoff retry for Organizations API calls.

    :param func: Function to execute
    :param args: Function arguments
    :param kwargs: Function keyword arguments

    :returns: Function result
    :raises Exception: Last exception if all retries failed
    """
    last_exception = None

    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            log.trace(
                "Attempting API call",
                details={"function": func.__name__, "attempt": attempt + 1, "max_attempts": MAX_RETRY_ATTEMPTS},
            )

            if attempt > 0:
                delay = randint(MIN_RETRY_DELAY, MAX_RETRY_DELAY)
                log.debug("Retrying with backoff delay", details={"attempt": attempt + 1, "delay_seconds": delay})
                sleep(delay)

            result = func(*args, **kwargs)

            if attempt > 0:
                log.info("API call succeeded after retry", details={"function": func.__name__, "attempt": attempt + 1})

            return result

        except Exception as e:
            last_exception = e
            error_msg = str(e)

            # Check for retryable errors
            retryable_errors = [
                "ConcurrentModificationException",
                "PolicyInUseException",
                "TooManyRequestsException",
                "ServiceException",
                "ThrottlingException",
            ]

            is_retryable = any(error in error_msg for error in retryable_errors)

            log.warning(
                "API call failed",
                details={
                    "function": func.__name__,
                    "attempt": attempt + 1,
                    "error": error_msg,
                    "is_retryable": is_retryable,
                    "will_retry": is_retryable and (attempt + 1) < MAX_RETRY_ATTEMPTS,
                },
            )

            if not is_retryable:
                log.error("Non-retryable error encountered", details={"function": func.__name__, "error": error_msg})
                raise

    # All retries exhausted
    log.error(
        "All retry attempts exhausted",
        details={"function": func.__name__, "max_attempts": MAX_RETRY_ATTEMPTS, "last_error": str(last_exception)},
    )
    raise last_exception


def get_policy_attachments(policy_id: str, organizations_client: Any) -> List[Dict[str, Any]]:
    """
    Get all targets that a policy is attached to.

    :param policy_id: Policy ID to check attachments for
    :type policy_id: str
    :param organizations_client: AWS Organizations client
    :type organizations_client: Any

    :returns: List of target dictionaries
    :rtype: List[Dict[str, Any]]
    """
    log.trace("Getting policy attachments", details={"policy_id": policy_id})

    try:
        response = organizations_client.list_targets_for_policy(PolicyId=policy_id)
        targets = response.get("Targets", [])

        log.debug(
            "Retrieved policy attachments",
            details={
                "policy_id": policy_id,
                "attachment_count": len(targets),
                "targets": [target.get("TargetId") for target in targets],
            },
        )

        return targets
    except Exception as e:
        log.error("Failed to get policy attachments", details={"policy_id": policy_id, "error": str(e)})
        raise


def is_policy_attached_to_target(policy_id: str, target_id: str, organizations_client: Any) -> bool:
    """
    Check if a policy is currently attached to a specific target.

    :param policy_id: Policy ID to check
    :type policy_id: str
    :param target_id: Target ID to check
    :type target_id: str
    :param organizations_client: AWS Organizations client
    :type organizations_client: Any

    :returns: True if policy is attached to target
    :rtype: bool
    """
    try:
        attachments = get_policy_attachments(policy_id, organizations_client)
        is_attached = any(target.get("TargetId") == target_id for target in attachments)

        log.debug(
            "Checked policy attachment status", details={"policy_id": policy_id, "target_id": target_id, "is_attached": is_attached}
        )

        return is_attached
    except Exception as e:
        log.warning(
            "Failed to check policy attachment status", details={"policy_id": policy_id, "target_id": target_id, "error": str(e)}
        )
        return False


def handle_default_policy_attachment(target_id: str, organizations_client: Any, event: Dict[str, Any]) -> None:
    """
    Handle default FullAWSAccess policy attachment when needed.

    :param target_id: Target that needs default policy
    :type target_id: str
    :param organizations_client: AWS Organizations client
    :type organizations_client: Any
    :param event: CloudFormation event for context
    :type event: Dict[str, Any]
    """
    log.trace("Handling default policy attachment", details={"target_id": target_id})

    try:
        # Check if FullAWSAccess is already attached
        if is_policy_attached_to_target(DEFAULT_FULL_ACCESS_POLICY_ID, target_id, organizations_client):
            log.info(
                "Default FullAWSAccess policy already attached",
                details={"target_id": target_id, "policy_id": DEFAULT_FULL_ACCESS_POLICY_ID},
            )
            return

        # Attach default policy
        log.info(
            "Attaching default FullAWSAccess policy", details={"target_id": target_id, "policy_id": DEFAULT_FULL_ACCESS_POLICY_ID}
        )

        def attach_default():
            return organizations_client.attach_policy(PolicyId=DEFAULT_FULL_ACCESS_POLICY_ID, TargetId=target_id)

        retry_with_backoff(attach_default)

        log.info(
            "Successfully attached default FullAWSAccess policy",
            details={"target_id": target_id, "policy_id": DEFAULT_FULL_ACCESS_POLICY_ID},
        )

    except Exception as e:
        log.error(
            "Failed to attach default FullAWSAccess policy",
            details={"target_id": target_id, "policy_id": DEFAULT_FULL_ACCESS_POLICY_ID, "error": str(e)},
        )
        # Don't raise - this is a best-effort operation


def create_service_control_policy(event: Dict[str, Any], context: Any) -> None:
    """
    Create a new Service Control Policy in AWS Organizations.

    :param event: CloudFormation event containing policy details
    :type event: Dict[str, Any]
    :param context: Lambda context
    :type context: Any
    """
    log.info(
        "Starting Service Control Policy creation",
        details={"logical_resource_id": event.get("LogicalResourceId"), "stack_id": event.get("StackId")},
    )

    try:
        # Get AWS Organizations client
        role_arn = util.get_provisioning_role_arn()
        organizations_client = aws.org_client(role_arn=role_arn)

        # Extract and validate parameters
        resource_properties = event.get("ResourceProperties", {})
        policy_name = resource_properties.get("PolicyName")
        policy_description = resource_properties.get("PolicyDescription", "Created by CloudFormation")
        policy_type = resource_properties.get("Type", POLICY_TYPE_SCP)
        policy_document = resource_properties.get("PolicyDocument")

        if not policy_name:
            raise ValueError("PolicyName is required")

        if not policy_document:
            raise ValueError("PolicyDocument is required")

        log.info(
            "Creating Service Control Policy",
            details={"policy_name": policy_name, "policy_description": policy_description, "policy_type": policy_type},
        )

        # Validate policy document
        policy_document_json = validate_policy_document(policy_document)
        log.debug("Policy document validated successfully")

        # Create the policy with retry logic
        def create_policy():
            return organizations_client.create_policy(
                Content=policy_document_json, Description=policy_description, Name=policy_name, Type=policy_type
            )

        response = retry_with_backoff(create_policy)

        # Extract response details
        policy_summary = response["Policy"]["PolicySummary"]
        policy_id = policy_summary["Id"]
        policy_arn = policy_summary["Arn"]

        log.info(
            "Service Control Policy created successfully",
            details={"policy_id": policy_id, "policy_arn": policy_arn, "policy_name": policy_name},
        )

        # Prepare response data
        response_data = {
            "PolicyId": policy_id,
            "PolicyArn": policy_arn,
            "PolicyName": policy_name,
            "Message": "Service Control Policy created successfully",
        }

        send_success_response(event=event, context=context, response_data=response_data, physical_resource_id=policy_id)

    except ValueError as validation_error:
        error_msg = f"Validation error creating Service Control Policy: {str(validation_error)}"
        log.error(
            "Policy creation validation failed",
            details={"error": str(validation_error), "resource_properties": event.get("ResourceProperties", {})},
        )
        send_failure_response(event, context, error_msg)

    except Exception as e:
        error_msg = f"Failed to create Service Control Policy: {str(e)}"
        log.error(
            "Service Control Policy creation failed",
            details={
                "error": str(e),
                "error_type": type(e).__name__,
                "policy_name": event.get("ResourceProperties", {}).get("PolicyName", "Unknown"),
            },
        )
        send_failure_response(event, context, error_msg)


def update_service_control_policy(event: Dict[str, Any], context: Any) -> None:
    """
    Update an existing Service Control Policy in AWS Organizations.

    :param event: CloudFormation event containing updated policy details
    :type event: Dict[str, Any]
    :param context: Lambda context
    :type context: Any
    """
    policy_id = event.get("PhysicalResourceId")

    log.info(
        "Starting Service Control Policy update",
        details={"policy_id": policy_id, "logical_resource_id": event.get("LogicalResourceId")},
    )

    try:
        if not policy_id:
            raise ValueError("PhysicalResourceId (PolicyId) is required for update")

        # Validate policy ID format
        if not POLICY_ID_PATTERN.match(policy_id):
            raise ValueError(f"Invalid policy ID format: {policy_id}")

        # Get AWS Organizations client
        role_arn = util.get_provisioning_role_arn()
        organizations_client = aws.org_client(role_arn=role_arn)

        # Extract and validate parameters
        resource_properties = event.get("ResourceProperties", {})
        policy_name = resource_properties.get("PolicyName")
        policy_description = resource_properties.get("PolicyDescription", "Updated by CloudFormation")
        policy_document = resource_properties.get("PolicyDocument")

        if not policy_name:
            raise ValueError("PolicyName is required")

        if not policy_document:
            raise ValueError("PolicyDocument is required")

        log.info(
            "Updating Service Control Policy",
            details={"policy_id": policy_id, "policy_name": policy_name, "policy_description": policy_description},
        )

        # Validate policy document
        policy_document_json = validate_policy_document(policy_document)
        log.debug("Policy document validated successfully")

        # Update the policy with retry logic
        def update_policy():
            return organizations_client.update_policy(
                PolicyId=policy_id, Name=policy_name, Description=policy_description, Content=policy_document_json
            )

        response = retry_with_backoff(update_policy)

        # Extract response details
        policy_summary = response["Policy"]["PolicySummary"]
        policy_arn = policy_summary["Arn"]

        log.info(
            "Service Control Policy updated successfully",
            details={"policy_id": policy_id, "policy_arn": policy_arn, "policy_name": policy_name},
        )

        # Prepare response data
        response_data = {
            "PolicyId": policy_id,
            "PolicyArn": policy_arn,
            "PolicyName": policy_name,
            "Message": "Service Control Policy updated successfully",
        }

        send_success_response(event=event, context=context, response_data=response_data, physical_resource_id=policy_id)

    except ValueError as validation_error:
        error_msg = f"Validation error updating Service Control Policy: {str(validation_error)}"
        log.error("Policy update validation failed", details={"policy_id": policy_id, "error": str(validation_error)})
        send_failure_response(event, context, error_msg, policy_id)

    except Exception as e:
        error_msg = f"Failed to update Service Control Policy: {str(e)}"
        log.error(
            "Service Control Policy update failed",
            details={"policy_id": policy_id, "error": str(e), "error_type": type(e).__name__},
        )
        send_failure_response(event, context, error_msg, policy_id)


def delete_service_control_policy(event: Dict[str, Any], context: Any) -> None:
    """
    Delete a Service Control Policy from AWS Organizations.

    :param event: CloudFormation event containing policy to delete
    :type event: Dict[str, Any]
    :param context: Lambda context
    :type context: Any
    """
    policy_id = event.get("PhysicalResourceId")

    log.info(
        "Starting Service Control Policy deletion",
        details={"policy_id": policy_id, "logical_resource_id": event.get("LogicalResourceId")},
    )

    try:
        if not policy_id or policy_id.startswith("Failed/"):
            log.info("Skipping deletion - invalid or failed policy ID", details={"policy_id": policy_id})
            send_success_response(
                event=event,
                context=context,
                response_data={"Message": "Skipped deletion - policy was never created"},
                physical_resource_id=policy_id or "",
            )
            return

        # Validate policy ID format
        if not POLICY_ID_PATTERN.match(policy_id):
            raise ValueError(f"Invalid policy ID format: {policy_id}")

        # Get AWS Organizations client
        role_arn = util.get_provisioning_role_arn()
        organizations_client = aws.org_client(role_arn=role_arn)

        # Check if policy still exists and get its attachments
        try:
            attachments = get_policy_attachments(policy_id, organizations_client)

            if attachments:
                log.warning(
                    "Policy has active attachments - deletion may fail",
                    details={
                        "policy_id": policy_id,
                        "attachment_count": len(attachments),
                        "attached_targets": [target.get("TargetId") for target in attachments],
                    },
                )

        except organizations_client.exceptions.PolicyNotFoundException:
            log.info("Policy not found - already deleted", details={"policy_id": policy_id})
            send_success_response(
                event=event, context=context, response_data={"Message": "Policy already deleted"}, physical_resource_id=policy_id
            )
            return
        except Exception as e:
            log.warning("Could not check policy attachments", details={"policy_id": policy_id, "error": str(e)})

        # Delete the policy with retry logic
        def delete_policy():
            return organizations_client.delete_policy(PolicyId=policy_id)

        retry_with_backoff(delete_policy)

        log.info("Service Control Policy deleted successfully", details={"policy_id": policy_id})

        response_data = {"PolicyId": policy_id, "Message": "Service Control Policy deleted successfully"}

        send_success_response(event=event, context=context, response_data=response_data, physical_resource_id=policy_id)

    except Exception as e:
        error_msg = f"Failed to delete Service Control Policy: {str(e)}"
        log.error(
            "Service Control Policy deletion failed",
            details={"policy_id": policy_id, "error": str(e), "error_type": type(e).__name__},
        )
        send_failure_response(event, context, error_msg, policy_id)


def create_service_control_policy_attachment(event: Dict[str, Any], context: Any) -> None:
    """
    Attach a Service Control Policy to a target (root, OU, or account).

    :param event: CloudFormation event containing attachment details
    :type event: Dict[str, Any]
    :param context: Lambda context
    :type context: Any
    """
    log.info("Starting Service Control Policy attachment creation", details={"logical_resource_id": event.get("LogicalResourceId")})

    try:
        # Get AWS Organizations client
        role_arn = util.get_provisioning_role_arn()
        organizations_client = aws.org_client(role_arn=role_arn)

        # Extract and validate parameters
        resource_properties = event.get("ResourceProperties", {})
        policy_id = resource_properties.get("PolicyId")
        target_id = resource_properties.get("TargetId")

        if not policy_id:
            raise ValueError("PolicyId is required")

        if not target_id:
            raise ValueError("TargetId is required")

        # Validate policy ID format
        if not POLICY_ID_PATTERN.match(policy_id):
            raise ValueError(f"Invalid policy ID format: {policy_id}")

        log.info("Creating Service Control Policy attachment", details={"policy_id": policy_id, "target_id": target_id})

        # Validate and resolve target ID
        resolved_target_id = validate_target_id(target_id, organizations_client)

        # Generate physical resource ID for the attachment
        physical_resource_id = f"SCPAttachment-{event.get('LogicalResourceId', 'Unknown')}"

        # Check if already attached
        if is_policy_attached_to_target(policy_id, resolved_target_id, organizations_client):
            log.info("Policy already attached to target", details={"policy_id": policy_id, "target_id": resolved_target_id})

            response_data = {"PolicyId": policy_id, "TargetId": resolved_target_id, "Message": "Policy attachment already exists"}

            send_success_response(
                event=event, context=context, response_data=response_data, physical_resource_id=physical_resource_id
            )
            return

        # Attach the policy with retry logic
        def attach_policy():
            return organizations_client.attach_policy(PolicyId=policy_id, TargetId=resolved_target_id)

        retry_with_backoff(attach_policy)

        log.info(
            "Service Control Policy attached successfully",
            details={"policy_id": policy_id, "target_id": resolved_target_id, "physical_resource_id": physical_resource_id},
        )

        response_data = {
            "PolicyId": policy_id,
            "TargetId": resolved_target_id,
            "AttachmentId": physical_resource_id,
            "Message": "Service Control Policy attached successfully",
        }

        send_success_response(event=event, context=context, response_data=response_data, physical_resource_id=physical_resource_id)

    except ValueError as validation_error:
        error_msg = f"Validation error creating SCP attachment: {str(validation_error)}"
        log.error(
            "SCP attachment creation validation failed",
            details={"error": str(validation_error), "resource_properties": event.get("ResourceProperties", {})},
        )
        send_failure_response(event, context, error_msg)

    except Exception as e:
        error_msg = f"Failed to create Service Control Policy attachment: {str(e)}"
        log.error(
            "Service Control Policy attachment creation failed",
            details={
                "error": str(e),
                "error_type": type(e).__name__,
                "policy_id": event.get("ResourceProperties", {}).get("PolicyId"),
                "target_id": event.get("ResourceProperties", {}).get("TargetId"),
            },
        )
        send_failure_response(event, context, error_msg)


def update_service_control_policy_attachment(event: Dict[str, Any], context: Any) -> None:
    """
    Update a Service Control Policy attachment by detaching from old target and attaching to new target.

    :param event: CloudFormation event containing updated attachment details
    :type event: Dict[str, Any]
    :param context: Lambda context
    :type context: Any
    """
    physical_resource_id = event.get("PhysicalResourceId")

    log.info(
        "Starting Service Control Policy attachment update",
        details={"physical_resource_id": physical_resource_id, "logical_resource_id": event.get("LogicalResourceId")},
    )

    try:
        if not physical_resource_id:
            raise ValueError("PhysicalResourceId is required for update")

        # Get AWS Organizations client
        role_arn = util.get_provisioning_role_arn()
        organizations_client = aws.org_client(role_arn=role_arn)

        # Extract current and old parameters
        resource_properties = event.get("ResourceProperties", {})
        old_resource_properties = event.get("OldResourceProperties", {})

        new_policy_id = resource_properties.get("PolicyId")
        new_target_id = resource_properties.get("TargetId")
        old_policy_id = old_resource_properties.get("PolicyId")
        old_target_id = old_resource_properties.get("TargetId")

        if not new_policy_id or not new_target_id:
            raise ValueError("PolicyId and TargetId are required")

        if not old_policy_id or not old_target_id:
            raise ValueError("OldResourceProperties with PolicyId and TargetId are required")

        log.info(
            "Updating Service Control Policy attachment",
            details={
                "old_policy_id": old_policy_id,
                "old_target_id": old_target_id,
                "new_policy_id": new_policy_id,
                "new_target_id": new_target_id,
            },
        )

        # Validate and resolve target IDs
        resolved_old_target_id = validate_target_id(old_target_id, organizations_client)
        resolved_new_target_id = validate_target_id(new_target_id, organizations_client)

        # Detach from old target
        if is_policy_attached_to_target(old_policy_id, resolved_old_target_id, organizations_client):
            log.info("Detaching policy from old target", details={"policy_id": old_policy_id, "target_id": resolved_old_target_id})

            def detach_old_policy():
                return organizations_client.detach_policy(PolicyId=old_policy_id, TargetId=resolved_old_target_id)

            retry_with_backoff(detach_old_policy)

            log.info("Policy detached from old target successfully")
        else:
            log.warning(
                "Policy was not attached to old target", details={"policy_id": old_policy_id, "target_id": resolved_old_target_id}
            )

        # Attach to new target
        if not is_policy_attached_to_target(new_policy_id, resolved_new_target_id, organizations_client):
            log.info("Attaching policy to new target", details={"policy_id": new_policy_id, "target_id": resolved_new_target_id})

            def attach_new_policy():
                return organizations_client.attach_policy(PolicyId=new_policy_id, TargetId=resolved_new_target_id)

            retry_with_backoff(attach_new_policy)

            log.info("Policy attached to new target successfully")
        else:
            log.info(
                "Policy already attached to new target", details={"policy_id": new_policy_id, "target_id": resolved_new_target_id}
            )

        response_data = {
            "PolicyId": new_policy_id,
            "TargetId": resolved_new_target_id,
            "AttachmentId": physical_resource_id,
            "Message": "Service Control Policy attachment updated successfully",
        }

        send_success_response(event=event, context=context, response_data=response_data, physical_resource_id=physical_resource_id)

    except ValueError as validation_error:
        error_msg = f"Validation error updating SCP attachment: {str(validation_error)}"
        log.error(
            "SCP attachment update validation failed",
            details={"physical_resource_id": physical_resource_id, "error": str(validation_error)},
        )
        send_failure_response(event, context, error_msg, physical_resource_id)

    except Exception as e:
        error_msg = f"Failed to update Service Control Policy attachment: {str(e)}"
        log.error(
            "Service Control Policy attachment update failed",
            details={"physical_resource_id": physical_resource_id, "error": str(e), "error_type": type(e).__name__},
        )
        send_failure_response(event, context, error_msg, physical_resource_id)


def delete_service_control_policy_attachment(event: Dict[str, Any], context: Any) -> None:
    """
    Delete a Service Control Policy attachment from a target.

    :param event: CloudFormation event containing attachment to delete
    :type event: Dict[str, Any]
    :param context: Lambda context
    :type context: Any
    """
    physical_resource_id = event.get("PhysicalResourceId")

    log.info(
        "Starting Service Control Policy attachment deletion",
        details={"physical_resource_id": physical_resource_id, "logical_resource_id": event.get("LogicalResourceId")},
    )

    try:
        if not physical_resource_id or physical_resource_id.startswith("Failed/"):
            log.info("Skipping deletion - invalid or failed attachment ID", details={"physical_resource_id": physical_resource_id})
            send_success_response(
                event=event,
                context=context,
                response_data={"Message": "Skipped deletion - attachment was never created"},
                physical_resource_id=physical_resource_id or "",
            )
            return

        # Get AWS Organizations client
        role_arn = util.get_provisioning_role_arn()
        organizations_client = aws.org_client(role_arn=role_arn)

        # Extract parameters
        resource_properties = event.get("ResourceProperties", {})
        policy_id = resource_properties.get("PolicyId")
        target_id = resource_properties.get("TargetId")

        if not policy_id or not target_id:
            raise ValueError("PolicyId and TargetId are required")

        log.info("Deleting Service Control Policy attachment", details={"policy_id": policy_id, "target_id": target_id})

        # Validate and resolve target ID
        resolved_target_id = validate_target_id(target_id, organizations_client)

        # Check if policy is attached
        if not is_policy_attached_to_target(policy_id, resolved_target_id, organizations_client):
            log.info(
                "Policy not attached to target - already detached",
                details={"policy_id": policy_id, "target_id": resolved_target_id},
            )

            response_data = {"PolicyId": policy_id, "TargetId": resolved_target_id, "Message": "Policy attachment already deleted"}

            send_success_response(
                event=event, context=context, response_data=response_data, physical_resource_id=physical_resource_id
            )
            return

        # Check if this will be the last attachment - if so, attach default policy first
        try:
            attachments = get_policy_attachments(policy_id, organizations_client)
            if len(attachments) <= 1:
                log.info(
                    "This is the last attachment - attaching default policy first",
                    details={"policy_id": policy_id, "target_id": resolved_target_id, "remaining_attachments": len(attachments)},
                )
                handle_default_policy_attachment(resolved_target_id, organizations_client, event)
        except Exception as e:
            log.warning(
                "Could not check attachment count for default policy handling", details={"policy_id": policy_id, "error": str(e)}
            )

        # Detach the policy with retry logic
        def detach_policy():
            return organizations_client.detach_policy(PolicyId=policy_id, TargetId=resolved_target_id)

        retry_with_backoff(detach_policy)

        log.info(
            "Service Control Policy attachment deleted successfully",
            details={"policy_id": policy_id, "target_id": resolved_target_id},
        )

        response_data = {
            "PolicyId": policy_id,
            "TargetId": resolved_target_id,
            "Message": "Service Control Policy attachment deleted successfully",
        }

        send_success_response(event=event, context=context, response_data=response_data, physical_resource_id=physical_resource_id)

    except ValueError as validation_error:
        error_msg = f"Validation error deleting SCP attachment: {str(validation_error)}"
        log.error(
            "SCP attachment deletion validation failed",
            details={"physical_resource_id": physical_resource_id, "error": str(validation_error)},
        )
        send_failure_response(event, context, error_msg, physical_resource_id)

    except Exception as e:
        error_msg = f"Failed to delete Service Control Policy attachment: {str(e)}"
        log.error(
            "Service Control Policy attachment deletion failed",
            details={"physical_resource_id": physical_resource_id, "error": str(e), "error_type": type(e).__name__},
        )
        send_failure_response(event, context, error_msg, physical_resource_id)


def get_default_policy() -> List[Dict[str, Any]]:
    """
    Get list of all Service Control Policies in the organization.

    :returns: List of policy dictionaries
    :rtype: List[Dict[str, Any]]
    """
    log.trace("Getting default policies")

    try:
        role_arn = util.get_provisioning_role_arn()
        organizations_client = aws.org_client(role_arn=role_arn)

        response = organizations_client.list_policies(Filter=POLICY_TYPE_SCP)
        policies = response.get("Policies", [])

        log.info(
            "Retrieved Service Control Policies",
            details={"policy_count": len(policies), "policies": [{"Id": p.get("Id"), "Name": p.get("Name")} for p in policies]},
        )

        return policies

    except Exception as e:
        log.error("Failed to get default policies", details={"error": str(e), "error_type": type(e).__name__})
        return []


# Export public functions
__all__ = [
    "create_service_control_policy",
    "update_service_control_policy",
    "delete_service_control_policy",
    "create_service_control_policy_attachment",
    "update_service_control_policy_attachment",
    "delete_service_control_policy_attachment",
    "get_default_policy",
]
