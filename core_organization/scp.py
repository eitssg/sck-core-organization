"""Module to manage Service Control Policy"""

from typing import Any

import json

from time import sleep
from random import randint

import boto3

import core_logging as log

from .response import send_response


def create_service_control_policy(event: dict, context: Any):  # noqa: C901

    log.info("Create_ServiceControlPolicy.\n")
    boto_organizations_client = boto3.client("organizations")
    reponse_data = dict()
    try:
        policy_description = event["ResourceProperties"].get(
            "PolicyDescription", "Undefined Policy Description"
        )
        policy_name = event["ResourceProperties"].get(
            "PolicyName", "Undefined Policy Name"
        )
        policy_type = event["ResourceProperties"].get("Type", "SERVICE_CONTROL_POLICY")
        policy_document_as_json = json.dumps(
            event["ResourceProperties"]["PolicyDocument"]
        )

        log.info(policy_document_as_json)
        for i in range(0, 10):
            try:

                sleep(randint(5, 30))
                log.info("Attempting request " + str(i))

                response = boto_organizations_client.create_policy(
                    Content=policy_document_as_json,
                    Description=policy_description,
                    Name=policy_name,
                    Type=policy_type,
                )

            except Exception as BotoException:

                log.info(str(BotoException))

                if "PolicyInUseException" in str(
                    BotoException
                ) or "ConcurrentModificationException" in str(BotoException):
                    log.info("A PolicyInUseException was detected, will retry")
                    continue
                else:
                    raise

            break

        policy_id = response["Policy"]["PolicySummary"]["Id"]
        log.info("The policy id was" + policy_id)
        policy_arn = response["Policy"]["PolicySummary"]["Arn"]

        reponse_data["Arn"] = policy_arn
        reponse_data["Id"] = policy_id
        reponse_data["Message"] = "Created resource with success"

        log.debug(reponse_data)

        send_response(event, context, "SUCCESS", reponse_data, policy_id)

    except Exception as e:

        reponse_data_fail = {"Message": "Failed Create_ServiceControlPolicy: " + str(e)}

        log.error("Create Error:", details=reponse_data_fail)

        send_response(event, context, "FAILED", reponse_data_fail, "Failed/Create")


def update_service_control_policy(event: dict, context: Any):
    log.info("Update_ServiceControlPolicy.\n")
    boto_organizations_client = boto3.client("organizations")
    reponse_data = dict()
    try:
        policy_description = event["ResourceProperties"].get(
            "PolicyDescription", "Undefined Policy Description"
        )
        policy_name = event["ResourceProperties"].get(
            "PolicyName", "Undefined Policy Name"
        )
        policy_document_as_json = json.dumps(
            event["ResourceProperties"]["PolicyDocument"]
        )

        for i in range(0, 10):
            try:
                sleep(randint(5, 30))
                log.info("Attempting request " + str(i))

                response = boto_organizations_client.update_policy(
                    PolicyId=event["PhysicalResourceId"],
                    Name=policy_name,
                    Description=policy_description,
                    Content=policy_document_as_json,
                )

            except Exception as BotoException:

                log.info(str(BotoException))

                if "PolicyInUseException" in str(
                    BotoException
                ) or "ConcurrentModificationException" in str(BotoException):
                    log.info("A PolicyInUseException was detected, will retry")
                    continue
                else:
                    raise

            break

        reponse_data["Arn"] = response["Policy"]["PolicySummary"]["Id"]
        reponse_data["Id"] = response["Policy"]["PolicySummary"]["Arn"]
        reponse_data["Message"] = "Resource updated successfully"

        log.debug(reponse_data)

        send_response(
            event, context, "SUCCESS", reponse_data, event["PhysicalResourceId"]
        )

    except Exception as e:
        reponse_data_fail = {
            "Message": "Failed Update_ServiceControlPolicy with failure: " + str(e)
        }

        log.error("Update Error:", details=reponse_data_fail)

        send_response(
            event, context, "FAILED", reponse_data_fail, event["PhysicalResourceId"]
        )


def delete_service_control_policy(event: dict, context: Any):

    log.info("Delete_ServiceControlPolicy.")

    boto_organizations_client = boto3.client("organizations")
    reponse_data = dict()

    try:

        # TODO: Before you perform this operation, you must first detach the policy from all OUs, roots, and accounts.
        # If only done via Cloud Formation CFN DependsOn will sort this out,
        # will fail if any human meddling has occured
        for i in range(0, 10):
            try:
                sleep(randint(5, 30))
                log.info("Attempting request " + str(i))

                boto_organizations_client.delete_policy(
                    PolicyId=event["PhysicalResourceId"]
                )

            except Exception as BotoException:
                log.info(str(BotoException))
                if "PolicyInUseException" in str(
                    BotoException
                ) or "ConcurrentModificationException" in str(BotoException):
                    log.info("A PolicyInUseException was detected, will retry")
                    continue
                else:
                    raise

            break

        reponse_data["Message"] = "Resource deleted successfully"

        log.debug(reponse_data)

        send_response(
            event, context, "SUCCESS", reponse_data, event["PhysicalResourceId"]
        )

    except Exception as e:

        reponse_data_fail = {"Message": "Failed resource: " + str(e)}

        log.error("Delete Error:", details=reponse_data_fail)

        send_response(
            event, context, "FAILED", reponse_data_fail, event["PhysicalResourceId"]
        )


def create_service_control_policy_attachment(event: dict, context: Any):

    log.info("Create_ServiceControlPolicyAttachment.")

    boto_organizations_client = boto3.client("organizations")
    reponse_data = dict()

    try:
        policy_id = event["ResourceProperties"]["PolicyId"]

        # Root: a string that begins with "r-" followed by from 4 to 32 lower-case letters or digits.
        # Account: a string that consists of exactly 12 digits.
        # Organizational unit (OU): a string that begins with "ou-" followed by from 4 to 32 lower-case
        #  letters or digits (the ID of the root that the OU is in) followed by a second "-"
        # dash and from 8 to 32 additional lower-case letters or digits.

        # _delete_default_service_control_policy_attachment
        # _create_default_service_control_policy_attachment

        target_id = event["ResourceProperties"]["TargetId"]
        physical_resource_id = "SCPAttachment" + event["LogicalResourceId"]

        if target_id.lower() == "root":
            responseroot = boto_organizations_client.list_roots()
            # Get the root ID
            target_id = responseroot["Roots"][0]["Id"]
            log.info("Parent Root Id Is" + target_id)

            # TODO check if p-FullAWSAccess and root, check if it is already attached
            # if attached throw success
            # TODO check if target = root if so then remove any default
            # attachment

        for i in range(0, 10):
            try:
                sleep(randint(5, 30))
                log.info("Attempting request " + str(i))

                boto_organizations_client.attach_policy(
                    PolicyId=policy_id, TargetId=target_id
                )

            except Exception as BotoException:

                log.info(str(BotoException))

                if "PolicyInUseException" in str(
                    BotoException
                ) or "ConcurrentModificationException" in str(BotoException):
                    log.info("A PolicyInUseException was detected, will retry")
                    continue
                else:
                    raise

            break

        reponse_data["Message"] = "Created resource with success"
        send_response(event, context, "SUCCESS", reponse_data, physical_resource_id)

    except Exception as e:
        reponse_data_fail = {
            "Message": "Failed Create_ServiceControlPolicyAttachment: " + str(e)
        }

        log.error("Create Error:", details=reponse_data_fail)

        send_response(event, context, "FAILED", reponse_data_fail, "Failed/Create")


def update_service_control_policy_attachment(event: dict, context: Any):  # noqa: C901

    log.info("Update_ServiceControlPolicyAttachment.")

    boto_organizations_client = boto3.client("organizations")
    reponse_data = dict()

    try:
        policy_id = event["ResourceProperties"]["PolicyId"]
        target_id = event["ResourceProperties"]["TargetId"]

        for i in range(0, 10):
            try:
                sleep(randint(5, 30))
                log.info("Attempting request " + str(i))

                boto_organizations_client.detach_policy(
                    PolicyId=event["OldResourceProperties"]["PolicyId"],
                    TargetId=event["OldResourceProperties"]["TargetId"],
                )

            except Exception as BotoException:
                log.info(str(BotoException))
                if "PolicyInUseException" in str(
                    BotoException
                ) or "ConcurrentModificationException" in str(BotoException):
                    log.info("A PolicyInUseException was detected, will retry")
                    continue
                else:
                    raise

            break

        for i in range(0, 10):
            try:
                sleep(randint(5, 30))
                log.info("Attempting request " + str(i))

                boto_organizations_client.attach_policy(
                    PolicyId=policy_id, TargetId=target_id
                )

            except Exception as BotoException:
                log.info(str(BotoException))
                if "PolicyInUseException" in str(
                    BotoException
                ) or "ConcurrentModificationException" in str(BotoException):
                    log.info("A PolicyInUseException was detected, will retry")
                    continue
                else:
                    raise

            break

        reponse_data["Message"] = "Created resource with success"

        send_response(
            event, context, "SUCCESS", reponse_data, event["PhysicalResourceId"]
        )

    except Exception as e:
        reponse_data_fail = {
            "Message": "Failed Create_ServiceControlPolicyAttachment: " + str(e)
        }

        log.error("Create Error:", details=reponse_data_fail)

        send_response(
            event, context, "FAILED", reponse_data_fail, event["PhysicalResourceId"]
        )


def delete_service_control_policy_attachment(event: dict, context: Any):

    log.info("Delete_ServiceControlPolicyAttachment.")

    boto_organizations_client = boto3.client("organizations")
    reponse_data = dict()
    try:
        policy_id = event["ResourceProperties"]["PolicyId"]
        target_id = event["ResourceProperties"]["TargetId"]

        for i in range(0, 10):
            try:
                log.info("Attempting request " + str(i))

                attachments = boto_organizations_client.list_targets_for_policy(
                    PolicyId=policy_id
                )

                if len(attachments.Targets) <= 1:
                    _create_default_service_control_policy_attachment(event, context)
                    sleep(randint(5, 30))

                boto_organizations_client.detach_policy(
                    PolicyId=policy_id, TargetId=target_id
                )

            except Exception as e:

                msg = str(e)

                log.info("Error: ", e)

                if (
                    "PolicyInUseException" in msg
                    or "ConcurrentModificationException" in msg
                ):
                    log.info("A PolicyInUseException was detected, will retry")

                    sleep(randint(5, 30))

                    continue
                else:
                    raise

            break

        reponse_data["Message"] = "Delete resource with success"
        send_response(
            event, context, "SUCCESS", reponse_data, event["PhysicalResourceId"]
        )

    except Exception as e:

        reponse_data_fail = {
            "Message": "Failed Delete_ServiceControlPolicyAttachment: " + str(e)
        }

        log.error("Error deleting policy:", details=reponse_data_fail)

        send_response(
            event, context, "FAILED", reponse_data_fail, event["PhysicalResourceId"]
        )


def get_default_policy() -> list[dict]:

    log.info("get_default_policy")

    boto_organizations_client = boto3.client("organizations")

    response_policy = boto_organizations_client.list_policies(
        Filter="SERVICE_CONTROL_POLICY"
    )

    if "Policies" in response_policy:
        policies = response_policy["Policies"]
    else:
        policies = []

    # details should be a dictionary, not a list
    log.info("Service Control Policy", details={"Policies": policies})

    return policies


def _delete_default_service_control_policy_attachment(event, context):

    log.info("_delete_default_service_control_policy_attachment")

    boto_organizations_client = boto3.client("organizations")

    policy_id = "p-FullAWSAccess"
    target_id = event["ResourceProperties"]["TargetId"]

    for i in range(0, 10):
        try:
            sleep(randint(5, 30))
            log.info("Attempting request " + str(i))

            boto_organizations_client.detach_policy(
                PolicyId=policy_id, TargetId=target_id
            )

        except Exception as BotoException:
            log.info(BotoException)
            if "PolicyInUseException" in str(
                BotoException
            ) or "ConcurrentModificationException" in str(BotoException):
                log.info("A PolicyInUseException was detected, will retry")
                continue
            else:
                raise

        break


def _create_default_service_control_policy_attachment(event, context):

    log.info("Create_ServiceControlPolicyAttachment.")

    boto_organizations_client = boto3.client("organizations")

    policy_id = "p-FullAWSAccess"
    target_id = event["ResourceProperties"]["TargetId"]

    if target_id.lower() == "root":
        responseroot = boto_organizations_client.list_roots()
        # Get the root ID
        target_id = responseroot["Roots"][0]["Id"]
        log.info("Parent Root Id Is" + target_id)

    for i in range(0, 10):
        try:
            sleep(randint(5, 30))
            log.info("Attempting request " + str(i))

            boto_organizations_client.attach_policy(
                PolicyId=policy_id, TargetId=target_id
            )

        except Exception as BotoException:
            log.info(BotoException)
            if "PolicyInUseException" in str(
                BotoException
            ) or "ConcurrentModificationException" in str(BotoException):
                log.info("A PolicyInUseException was detected, will retry")
                continue
            else:
                raise

        break
