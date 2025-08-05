"""
AWS Organizations Organizational Unit Management Module.

This module provides comprehensive management of AWS Organizations Organizational Units (OUs),
including creation, updating, deletion, and account movement operations. It handles the
complexities of AWS Organizations' eventual consistency model with robust retry mechanisms.

**Supported Operations:**
    - List Organizational Units
    - Create Organizational Unit
    - Update Organizational Unit
    - Delete Organizational Unit
    - Move accounts between OUs
    - Move all child accounts to root during deletion

**Key Features:**
    - Automatic retry logic for eventual consistency issues
    - Comprehensive validation of OU parameters and account IDs
    - Intelligent handling of parent ID resolution (including "root")
    - Detailed logging for troubleshooting and audit trails
    - Graceful error handling with CloudFormation integration
    - Support for bulk account movement operations
"""

import re
from typing import Any, Dict, List, Optional
from time import sleep
from random import randint
import collections.abc

import core_framework as util
import core_logging as log
import core_helper.aws as aws

from .response import send_success_response, send_failure_response

# Constants for AWS Organizations
MAX_RETRY_ATTEMPTS = 10
MIN_RETRY_DELAY = 5
MAX_RETRY_DELAY = 30
CHILD_MOVE_MIN_DELAY = 5
CHILD_MOVE_MAX_DELAY = 20

# AWS Organizations ID patterns
ROOT_ID_PATTERN = re.compile(r"^r-[0-9a-z]{4,32}$")
ACCOUNT_ID_PATTERN = re.compile(r"^[0-9]{12}$")
OU_ID_PATTERN = re.compile(r"^ou-[0-9a-z]{4,32}-[0-9a-z]{8,32}$")


def validate_account_id(account_id: str) -> bool:
    """
    Validate AWS account ID format.

    :param account_id: Account ID to validate
    :type account_id: str

    :returns: True if valid account ID format
    :rtype: bool
    """
    return bool(ACCOUNT_ID_PATTERN.match(account_id))


def validate_ou_id(ou_id: str) -> bool:
    """
    Validate Organizational Unit ID format.

    :param ou_id: OU ID to validate
    :type ou_id: str

    :returns: True if valid OU ID format
    :rtype: bool
    """
    return bool(OU_ID_PATTERN.match(ou_id))


def resolve_parent_id(parent_id: str, organizations_client: Any) -> str:
    """
    Resolve parent ID, handling special "root" case.

    :param parent_id: Parent ID or "root"
    :type parent_id: str
    :param organizations_client: AWS Organizations client
    :type organizations_client: Any

    :returns: Resolved parent ID
    :rtype: str

    :raises ValueError: If parent ID cannot be resolved
    """
    log.trace("Resolving parent ID", details={"parent_id": parent_id})

    if parent_id.lower() == "root":
        try:
            response = organizations_client.list_roots()
            if not response.get("Roots"):
                raise ValueError("No organizational roots found")

            resolved_id = response["Roots"][0]["Id"]
            log.debug("Resolved root parent ID", details={"original": parent_id, "resolved": resolved_id})
            return resolved_id
        except Exception as e:
            raise ValueError(f"Failed to resolve root ID: {str(e)}")

    # Validate existing parent ID format
    if not (ROOT_ID_PATTERN.match(parent_id) or OU_ID_PATTERN.match(parent_id)):
        raise ValueError(f"Invalid parent ID format: {parent_id}")

    return parent_id


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


def move_account_with_retry(account_id: str, source_parent_id: str, destination_parent_id: str, organizations_client: Any) -> None:
    """
    Move an account between organizational units with retry logic.

    :param account_id: Account ID to move
    :type account_id: str
    :param source_parent_id: Source parent OU/root ID
    :type source_parent_id: str
    :param destination_parent_id: Destination parent OU/root ID
    :type destination_parent_id: str
    :param organizations_client: AWS Organizations client
    :type organizations_client: Any

    :raises Exception: If account move fails after all retries
    """
    log.trace(
        "Moving account with retry",
        details={"account_id": account_id, "source_parent_id": source_parent_id, "destination_parent_id": destination_parent_id},
    )

    def move_account():
        return organizations_client.move_account(
            AccountId=account_id, SourceParentId=source_parent_id, DestinationParentId=destination_parent_id
        )

    # Use shorter delays for account moves within child operations
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            if attempt > 0:
                delay = randint(CHILD_MOVE_MIN_DELAY, CHILD_MOVE_MAX_DELAY)
                log.debug(
                    "Retrying account move", details={"account_id": account_id, "attempt": attempt + 1, "delay_seconds": delay}
                )
                sleep(delay)

            move_account()

            log.info(
                "Account moved successfully",
                details={
                    "account_id": account_id,
                    "source_parent_id": source_parent_id,
                    "destination_parent_id": destination_parent_id,
                    "attempts": attempt + 1,
                },
            )
            return

        except Exception as e:
            error_msg = str(e)
            retryable_errors = ["PolicyInUseException", "ConcurrentModificationException"]
            is_retryable = any(error in error_msg for error in retryable_errors)

            log.warning(
                "Account move failed",
                details={"account_id": account_id, "attempt": attempt + 1, "error": error_msg, "is_retryable": is_retryable},
            )

            if not is_retryable or attempt == MAX_RETRY_ATTEMPTS - 1:
                raise


def list_organizational_units(event: Dict[str, Any], context: Any) -> None:
    """
    List all organizational units under a specified parent.

    :param event: CloudFormation event containing parent ID
    :type event: Dict[str, Any]
    :param context: Lambda context
    :type context: Any
    """
    log.info(
        "Starting organizational unit listing",
        details={"logical_resource_id": event.get("LogicalResourceId"), "stack_id": event.get("StackId")},
    )

    try:
        # Get AWS Organizations client
        role_arn = util.get_provisioning_role_arn()
        organizations_client = aws.org_client(role_arn=role_arn)

        # Extract and validate parameters
        resource_properties = event.get("ResourceProperties", {})
        parent_id = resource_properties.get("ParentId")

        if not parent_id:
            raise ValueError("ParentId is required")

        # Resolve parent ID
        resolved_parent_id = resolve_parent_id(parent_id, organizations_client)

        log.info("Listing organizational units", details={"parent_id": resolved_parent_id})

        # List organizational units
        def list_ous():
            return organizations_client.list_organizational_units_for_parent(ParentId=resolved_parent_id)

        response = retry_with_backoff(list_ous)

        ou_list = response.get("OrganizationalUnits", [])

        log.info(
            "Successfully listed organizational units",
            details={"parent_id": resolved_parent_id, "ou_count": len(ou_list), "ou_ids": [ou.get("Id") for ou in ou_list]},
        )

        response_data = {
            "OrganizationalUnits": ou_list,
            "ParentId": resolved_parent_id,
            "Count": len(ou_list),
            "Message": "Listed organizational units successfully",
        }

        send_success_response(
            event=event, context=context, response_data=response_data, physical_resource_id=f"Listed-{resolved_parent_id}"
        )

    except ValueError as validation_error:
        error_msg = f"Validation error listing OUs: {str(validation_error)}"
        log.error(
            "OU listing validation failed",
            details={"error": str(validation_error), "resource_properties": event.get("ResourceProperties", {})},
        )
        send_failure_response(event, context, error_msg)

    except Exception as e:
        error_msg = f"Failed to list organizational units: {str(e)}"
        log.error(
            "Organizational unit listing failed",
            details={
                "error": str(e),
                "error_type": type(e).__name__,
                "parent_id": event.get("ResourceProperties", {}).get("ParentId"),
            },
        )
        send_failure_response(event, context, error_msg)


def create_organizational_unit(event: Dict[str, Any], context: Any) -> None:
    """
    Create a new organizational unit in AWS Organizations.

    :param event: CloudFormation event containing OU details
    :type event: Dict[str, Any]
    :param context: Lambda context
    :type context: Any
    """
    log.info(
        "Starting organizational unit creation",
        details={"logical_resource_id": event.get("LogicalResourceId"), "stack_id": event.get("StackId")},
    )

    try:
        # Get AWS Organizations client
        role_arn = util.get_provisioning_role_arn()
        organizations_client = aws.org_client(role_arn=role_arn)

        # Extract and validate parameters
        resource_properties = event.get("ResourceProperties", {})
        parent_id = resource_properties.get("ParentId")
        ou_name = resource_properties.get("Name")
        children = resource_properties.get("Children", [])

        if not parent_id:
            raise ValueError("ParentId is required")

        if not ou_name:
            raise ValueError("Name is required")

        # Validate OU name
        if len(ou_name.strip()) == 0:
            raise ValueError("OU name cannot be empty")

        # Resolve parent ID
        resolved_parent_id = resolve_parent_id(parent_id, organizations_client)

        log.info(
            "Creating organizational unit",
            details={"ou_name": ou_name, "parent_id": resolved_parent_id, "child_count": len(children) if children else 0},
        )

        # Create the organizational unit
        def create_ou():
            return organizations_client.create_organizational_unit(ParentId=resolved_parent_id, Name=ou_name)

        response = retry_with_backoff(create_ou)

        # Extract response details
        ou_data = response["OrganizationalUnit"]
        ou_id = ou_data["Id"]
        ou_arn = ou_data["Arn"]

        log.info(
            "Organizational unit created successfully",
            details={"ou_id": ou_id, "ou_arn": ou_arn, "ou_name": ou_name, "parent_id": resolved_parent_id},
        )

        response_data = {
            "Id": ou_id,
            "Arn": ou_arn,
            "Name": ou_name,
            "ParentId": resolved_parent_id,
            "Message": "Organizational unit created successfully",
        }

        # Send success response early to establish physical resource ID
        send_success_response(event=event, context=context, response_data=response_data, physical_resource_id=ou_id)

        # Handle child account movements if specified
        if children and isinstance(children, collections.abc.Iterable) and not isinstance(children, str):
            log.info("Processing child account movements", details={"ou_id": ou_id, "child_count": len(children)})

            for child_account_id in children:
                try:
                    if not validate_account_id(str(child_account_id)):
                        log.warning("Invalid child account ID format", details={"account_id": child_account_id, "ou_id": ou_id})
                        continue

                    # Get current parent of the account
                    parent_response = organizations_client.list_parents(ChildId=child_account_id)
                    if not parent_response.get("Parents"):
                        log.warning("No parent found for account", details={"account_id": child_account_id})
                        continue

                    current_parent_id = parent_response["Parents"][0]["Id"]

                    log.info(
                        "Moving child account to new OU",
                        details={"account_id": child_account_id, "current_parent_id": current_parent_id, "new_parent_id": ou_id},
                    )

                    # Move the account
                    move_account_with_retry(child_account_id, current_parent_id, ou_id, organizations_client)

                except Exception as child_error:
                    log.error(
                        "Failed to move child account",
                        details={"account_id": child_account_id, "ou_id": ou_id, "error": str(child_error)},
                    )
                    # Continue with other children rather than failing entire operation

            log.info("Completed child account movements", details={"ou_id": ou_id, "child_count": len(children)})

    except ValueError as validation_error:
        error_msg = f"Validation error creating OU: {str(validation_error)}"
        log.error(
            "OU creation validation failed",
            details={"error": str(validation_error), "resource_properties": event.get("ResourceProperties", {})},
        )
        send_failure_response(event, context, error_msg)

    except Exception as e:
        error_msg = f"Failed to create organizational unit: {str(e)}"
        log.error(
            "Organizational unit creation failed",
            details={"error": str(e), "error_type": type(e).__name__, "ou_name": event.get("ResourceProperties", {}).get("Name")},
        )
        send_failure_response(event, context, error_msg)


def update_organizational_unit(event: Dict[str, Any], context: Any) -> None:
    """
    Update an existing organizational unit in AWS Organizations.

    :param event: CloudFormation event containing updated OU details
    :type event: Dict[str, Any]
    :param context: Lambda context
    :type context: Any
    """
    ou_id = event.get("PhysicalResourceId")

    log.info("Starting organizational unit update", details={"ou_id": ou_id, "logical_resource_id": event.get("LogicalResourceId")})

    try:
        if not ou_id:
            raise ValueError("PhysicalResourceId (OU ID) is required for update")

        if not validate_ou_id(ou_id):
            raise ValueError(f"Invalid OU ID format: {ou_id}")

        # Get AWS Organizations client
        role_arn = util.get_provisioning_role_arn()
        organizations_client = aws.org_client(role_arn=role_arn)

        # Extract and validate parameters
        resource_properties = event.get("ResourceProperties", {})
        ou_name = resource_properties.get("Name")
        children = resource_properties.get("Children", [])

        if not ou_name:
            raise ValueError("Name is required")

        if len(ou_name.strip()) == 0:
            raise ValueError("OU name cannot be empty")

        log.info(
            "Updating organizational unit",
            details={"ou_id": ou_id, "new_name": ou_name, "child_count": len(children) if children else 0},
        )

        # Update the organizational unit
        def update_ou():
            return organizations_client.update_organizational_unit(OrganizationalUnitId=ou_id, Name=ou_name)

        response = retry_with_backoff(update_ou)

        # Extract response details
        ou_data = response["OrganizationalUnit"]
        ou_arn = ou_data["Arn"]

        log.info("Organizational unit updated successfully", details={"ou_id": ou_id, "ou_arn": ou_arn, "new_name": ou_name})

        # Handle child account movements if specified
        if children and isinstance(children, collections.abc.Iterable) and not isinstance(children, str):
            log.info("Processing child account movements for update", details={"ou_id": ou_id, "child_count": len(children)})

            for child_account_id in children:
                try:
                    if not validate_account_id(str(child_account_id)):
                        log.warning("Invalid child account ID format", details={"account_id": child_account_id, "ou_id": ou_id})
                        continue

                    # Get current parent of the account
                    parent_response = organizations_client.list_parents(ChildId=child_account_id)
                    if not parent_response.get("Parents"):
                        log.warning("No parent found for account", details={"account_id": child_account_id})
                        continue

                    current_parent_id = parent_response["Parents"][0]["Id"]

                    # Skip if already in the correct OU
                    if current_parent_id == ou_id:
                        log.debug("Account already in target OU", details={"account_id": child_account_id, "ou_id": ou_id})
                        continue

                    log.info(
                        "Moving child account to updated OU",
                        details={"account_id": child_account_id, "current_parent_id": current_parent_id, "target_ou_id": ou_id},
                    )

                    # Move the account
                    move_account_with_retry(child_account_id, current_parent_id, ou_id, organizations_client)

                except Exception as child_error:
                    log.error(
                        "Failed to move child account during update",
                        details={"account_id": child_account_id, "ou_id": ou_id, "error": str(child_error)},
                    )
                    # Continue with other children

        response_data = {"Id": ou_id, "Arn": ou_arn, "Name": ou_name, "Message": "Organizational unit updated successfully"}

        send_success_response(event=event, context=context, response_data=response_data, physical_resource_id=ou_id)

    except ValueError as validation_error:
        error_msg = f"Validation error updating OU: {str(validation_error)}"
        log.error("OU update validation failed", details={"ou_id": ou_id, "error": str(validation_error)})
        send_failure_response(event, context, error_msg, ou_id)

    except Exception as e:
        error_msg = f"Failed to update organizational unit: {str(e)}"
        log.error("Organizational unit update failed", details={"ou_id": ou_id, "error": str(e), "error_type": type(e).__name__})
        send_failure_response(event, context, error_msg, ou_id)


def move_all_children_to_root(ou_id: str, organizations_client: Any) -> None:
    """
    Move all child accounts from an OU to the organization root.

    :param ou_id: Organizational Unit ID to move children from
    :type ou_id: str
    :param organizations_client: AWS Organizations client
    :type organizations_client: Any

    :raises Exception: If account movements fail
    """
    log.trace("Moving all children to root", details={"ou_id": ou_id})

    try:
        # Get root ID
        root_response = organizations_client.list_roots()
        if not root_response.get("Roots"):
            raise ValueError("No organizational roots found")

        root_id = root_response["Roots"][0]["Id"]

        # Get all child accounts
        children_response = organizations_client.list_children(ParentId=ou_id, ChildType="ACCOUNT")

        children = children_response.get("Children", [])

        if not children:
            log.info("No child accounts to move", details={"ou_id": ou_id})
            return

        log.info("Moving child accounts to root", details={"ou_id": ou_id, "root_id": root_id, "child_count": len(children)})

        for child in children:
            child_id = child["Id"]

            try:
                log.info(
                    "Moving child account to root", details={"account_id": child_id, "source_ou_id": ou_id, "root_id": root_id}
                )

                move_account_with_retry(child_id, ou_id, root_id, organizations_client)

            except Exception as child_error:
                log.error(
                    "Failed to move child account to root",
                    details={"account_id": child_id, "ou_id": ou_id, "root_id": root_id, "error": str(child_error)},
                )
                raise

        log.info("Successfully moved all children to root", details={"ou_id": ou_id, "child_count": len(children)})

    except Exception as e:
        log.error("Failed to move children to root", details={"ou_id": ou_id, "error": str(e)})
        raise


def delete_organizational_unit(event: Dict[str, Any], context: Any) -> None:
    """
    Delete an organizational unit from AWS Organizations.

    :param event: CloudFormation event containing OU to delete
    :type event: Dict[str, Any]
    :param context: Lambda context
    :type context: Any
    """
    ou_id = event.get("PhysicalResourceId")

    log.info(
        "Starting organizational unit deletion", details={"ou_id": ou_id, "logical_resource_id": event.get("LogicalResourceId")}
    )

    try:
        if not ou_id or ou_id.startswith("Failed/"):
            log.info("Skipping deletion - invalid or failed OU ID", details={"ou_id": ou_id})
            send_success_response(
                event=event,
                context=context,
                response_data={"Message": "Skipped deletion - OU was never created"},
                physical_resource_id=ou_id or "",
            )
            return

        if not validate_ou_id(ou_id):
            raise ValueError(f"Invalid OU ID format: {ou_id}")

        # Get AWS Organizations client
        role_arn = util.get_provisioning_role_arn()
        organizations_client = aws.org_client(role_arn=role_arn)

        log.info("Deleting organizational unit", details={"ou_id": ou_id})

        # Move all children to root before deletion
        try:
            move_all_children_to_root(ou_id, organizations_client)
        except Exception as move_error:
            log.error("Failed to move children to root", details={"ou_id": ou_id, "error": str(move_error)})
            # Continue with deletion attempt anyway

        # Delete the organizational unit
        def delete_ou():
            return organizations_client.delete_organizational_unit(OrganizationalUnitId=ou_id)

        retry_with_backoff(delete_ou)

        log.info("Organizational unit deleted successfully", details={"ou_id": ou_id})

        response_data = {"Id": ou_id, "Message": "Organizational unit deleted successfully"}

        send_success_response(event=event, context=context, response_data=response_data, physical_resource_id=ou_id)

    except Exception as e:
        error_msg = f"Failed to delete organizational unit: {str(e)}"
        log.error("Organizational unit deletion failed", details={"ou_id": ou_id, "error": str(e), "error_type": type(e).__name__})
        send_failure_response(event, context, error_msg, ou_id)


def move_account_between_ous(event: Dict[str, Any], context: Any) -> None:
    """
    Move an account from one organizational unit to another.

    :param event: CloudFormation event containing move details
    :type event: Dict[str, Any]
    :param context: Lambda context
    :type context: Any
    """
    log.info("Starting account move operation", details={"logical_resource_id": event.get("LogicalResourceId")})

    try:
        # Get AWS Organizations client
        role_arn = util.get_provisioning_role_arn()
        organizations_client = aws.org_client(role_arn=role_arn)

        # Extract and validate parameters
        resource_properties = event.get("ResourceProperties", {})
        account_id = resource_properties.get("AccountId")
        source_parent_id = resource_properties.get("SourceParentId")
        destination_parent_id = resource_properties.get("DestinationParentId")

        if not account_id:
            raise ValueError("AccountId is required")

        if not validate_account_id(account_id):
            raise ValueError(f"Invalid account ID format: {account_id}")

        if not destination_parent_id:
            raise ValueError("DestinationParentId is required")

        # Resolve destination parent ID
        resolved_destination_id = resolve_parent_id(destination_parent_id, organizations_client)

        # Get current parent if source not specified
        if not source_parent_id:
            parent_response = organizations_client.list_parents(ChildId=account_id)
            if not parent_response.get("Parents"):
                raise ValueError(f"No parent found for account {account_id}")

            resolved_source_id = parent_response["Parents"][0]["Id"]
            log.debug("Auto-detected source parent", details={"account_id": account_id, "source_parent_id": resolved_source_id})
        else:
            resolved_source_id = resolve_parent_id(source_parent_id, organizations_client)

        # Check if account is already in destination
        if resolved_source_id == resolved_destination_id:
            log.info(
                "Account already in destination parent", details={"account_id": account_id, "parent_id": resolved_destination_id}
            )

            response_data = {
                "AccountId": account_id,
                "SourceParentId": resolved_source_id,
                "DestinationParentId": resolved_destination_id,
                "Message": "Account already in destination parent",
            }

            send_success_response(
                event=event, context=context, response_data=response_data, physical_resource_id=f"AccountMove-{account_id}"
            )
            return

        log.info(
            "Moving account between OUs",
            details={
                "account_id": account_id,
                "source_parent_id": resolved_source_id,
                "destination_parent_id": resolved_destination_id,
            },
        )

        # Move the account
        move_account_with_retry(account_id, resolved_source_id, resolved_destination_id, organizations_client)

        response_data = {
            "AccountId": account_id,
            "SourceParentId": resolved_source_id,
            "DestinationParentId": resolved_destination_id,
            "Message": "Account moved successfully",
        }

        send_success_response(
            event=event, context=context, response_data=response_data, physical_resource_id=f"AccountMove-{account_id}"
        )

    except ValueError as validation_error:
        error_msg = f"Validation error moving account: {str(validation_error)}"
        log.error(
            "Account move validation failed",
            details={"error": str(validation_error), "resource_properties": event.get("ResourceProperties", {})},
        )
        send_failure_response(event, context, error_msg)

    except Exception as e:
        error_msg = f"Failed to move account: {str(e)}"
        log.error(
            "Account move failed",
            details={
                "error": str(e),
                "error_type": type(e).__name__,
                "account_id": event.get("ResourceProperties", {}).get("AccountId"),
            },
        )
        send_failure_response(event, context, error_msg)


# Export public functions
__all__ = [
    "list_organizational_units",
    "create_organizational_unit",
    "update_organizational_unit",
    "delete_organizational_unit",
    "move_account_between_ous",
]
