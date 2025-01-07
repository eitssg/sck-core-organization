""" Module to manage Organizational Units in AWS Organizations. """

from typing import Any

import boto3

from random import randint
from time import sleep
import collections.abc

import core_logging as log
import core_helper.aws as aws

from .response import send_response


def list_organizational_units(event: dict, context: Any):

    log.info("List_OrganizationalUnits.\n")

    boto_organizations_client = aws.org_client()
    response_data: dict[str, Any] = {}

    try:
        response = boto_organizations_client.list_organizational_units_for_parent(
            ParentId=event["ResourceProperties"]["ParentId"]
        )

        ou_list = list()

        for ou in response["OrganizationalUnits"]:
            ou_list.append(ou)

        response_data["OrganizationalUnits"] = ou_list
        response_data["Message"] = "Listed OUs with success"

        send_response(event, context, "SUCCESS", response_data, "Listed")

    except Exception as e:
        reponse_data_fail: dict = {}
        log.error(str(e))
        reponse_data_fail["Message"] = "Failed List_OrganizationalUnits: " + str(e)
        send_response(event, context, "FAILED", reponse_data_fail, "Failed/List")


def create_organizational_unit(event: dict, context: Any):  # noqa: C901

    log.info("Create_OrganizationalUnit.\n")

    boto_organizations_client = aws.org_client()
    reponse_data = dict()

    try:
        parent_id = event["ResourceProperties"]["ParentId"]
        log.info("The parent id is " + parent_id)

        ou_name = event["ResourceProperties"]["Name"]
        children = event["ResourceProperties"].get("Children", None)

        if parent_id.lower() == "root":
            responseroot = boto_organizations_client.list_roots()
            # Get the root ID
            parent_id = responseroot["Roots"][0]["Id"]
            log.info("Parent Root Id Is" + parent_id)

        for i in range(0, 10):
            try:
                sleep(randint(5, 30))
                log.info("Attempting request " + str(i))

                response = boto_organizations_client.create_organizational_unit(
                    ParentId=parent_id, Name=ou_name
                )

                ou_id = response["OrganizationalUnit"]["Id"]
                ou_arn = response["OrganizationalUnit"]["Arn"]

                reponse_data["Arn"] = ou_arn
                reponse_data["Id"] = ou_id
                reponse_data["Message"] = "Created OU with success"
                # TODO Really this should happen at the end , but if the stack fails while the children
                # Are getting added below, then CFN assigns the OU a random PhsyicalId and the rollback fails
                # The real workaround to this is to not do child attachment here but have a seperate OrganizationalUnitAttachment
                # Custom resource that attaches the accounts and Refs the OU
                # This makes the CFN way bigger and ugglier but it might be the only way
                send_response(event, context, "SUCCESS", reponse_data, ou_id)

                if isinstance(children, collections.abc.Iterable) and not isinstance(
                    children, str
                ):
                    log.info("Doing add child iteration")

                    for child in children:
                        log.info("Working on " + child)
                        prentresponse = boto_organizations_client.list_parents(
                            ChildId=child
                        )
                        log.info("Parent is " + prentresponse["Parents"][0]["Id"])
                        for i in range(0, 10):
                            try:
                                sleep(randint(5, 30))
                                boto_organizations_client.move_account(
                                    AccountId=child,
                                    SourceParentId=prentresponse["Parents"][0]["Id"],
                                    DestinationParentId=response["OrganizationalUnit"][
                                        "Id"
                                    ],
                                )
                            except Exception as BotoException:
                                log.info(str(BotoException))
                                if "PolicyInUseException" in str(
                                    BotoException
                                ) or "ConcurrentModificationException" in str(
                                    BotoException
                                ):
                                    log.info(
                                        "A PolicyInUseException was detected, will retry"
                                    )
                                    continue
                                else:
                                    raise

                            break
                else:
                    log.error("Children Not iterable")

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

    except Exception as e:
        reponse_data_fail = dict()
        log.error(str(e))
        reponse_data_fail["Message"] = "Failed Create_OrganizationalUnit: " + str(e)
        send_response(event, context, "FAILED", reponse_data_fail, "Failed/Create")


def update_organizational_unit(event: dict, context: Any):  # noqa: C901
    log.info("Update_OrganizationalUnit.\n")

    boto_organizations_client = boto3.client("organizations")
    reponse_data = dict()
    try:
        parent_id = event["ResourceProperties"]["ParentId"]
        ou_name = event["ResourceProperties"]["Name"]
        children = event["ResourceProperties"].get("Children", None)

        if parent_id.lower() == "root":
            responseroot = boto_organizations_client.list_roots()
            # Get the root ID
            parent_id = responseroot["Roots"][0]["Id"]

        for i in range(0, 10):
            try:
                sleep(randint(5, 30))
                log.info("Attempting request " + str(i))

                response = boto_organizations_client.update_organizational_unit(
                    OrganizationalUnitId=event["PhysicalResourceId"], Name=ou_name
                )

                if isinstance(children, collections.abc.Iterable) and not isinstance(
                    children, str
                ):
                    log.info("Doing add child iteration")

                    for child in children:
                        log.info("Working on " + child)
                        prentresponse = boto_organizations_client.list_parents(
                            ChildId=child
                        )
                        log.info("Parent is " + prentresponse["Parents"][0]["Id"])
                        for i in range(0, 10):
                            try:
                                sleep(randint(5, 30))
                                boto_organizations_client.move_account(
                                    AccountId=child,
                                    SourceParentId=prentresponse["Parents"][0]["Id"],
                                    DestinationParentId=response["OrganizationalUnit"][
                                        "Id"
                                    ],
                                )
                            except Exception as BotoException:
                                log.info(str(BotoException))
                                if "PolicyInUseException" in str(
                                    BotoException
                                ) or "ConcurrentModificationException" in str(
                                    BotoException
                                ):
                                    log.info(
                                        "A PolicyInUseException was detected, will retry"
                                    )
                                    continue
                                else:
                                    raise

                            break
                else:
                    log.error("Children Not iterable")

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

        ou_id = response["OrganizationalUnit"]["Id"]
        ou_arn = response["OrganizationalUnit"]["Arn"]

        reponse_data["Arn"] = ou_arn
        reponse_data["Id"] = ou_id
        reponse_data["Message"] = "Updated OU with success"

        send_response(event, context, "SUCCESS", reponse_data, ou_id)

    except Exception as e:
        reponse_data_fail = dict()
        log.error(str(e))
        reponse_data_fail["Message"] = "Failed Update_OrganizationalUnit: " + str(e)
        send_response(
            event, context, "FAILED", reponse_data_fail, event["PhysicalResourceId"]
        )


def delete_organizational_unit(event: dict, context: Any):

    log.info("Delete_OrganizationalUnit.\n")

    boto_organizations_client = boto3.client("organizations")
    reponse_data = dict()

    move_all_children_to_root(event, context)

    try:
        for i in range(0, 10):
            try:
                sleep(randint(5, 30))
                log.info("Attempting request " + str(i))

                boto_organizations_client.delete_organizational_unit(
                    OrganizationalUnitId=event["PhysicalResourceId"],
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

        reponse_data["Message"] = "Deleted OU with success"
        send_response(
            event, context, "SUCCESS", reponse_data, event["PhysicalResourceId"]
        )

    except Exception as e:
        reponse_data_fail = dict()
        log.error(str(e))
        reponse_data_fail["Message"] = "Failed Delete_OrganizationalUnit: " + str(e)
        send_response(
            event, context, "FAILED", reponse_data_fail, event["PhysicalResourceId"]
        )


def move_all_children_to_root(event: dict, context: Any):
    log.info("move_all_children_to_root.\n")

    boto_organizations_client = boto3.client("organizations")

    responseroot = boto_organizations_client.list_roots()

    responseChildren = boto_organizations_client.list_children(
        ParentId=event["PhysicalResourceId"], ChildType="ACCOUNT"
    )

    try:
        for child in responseChildren["Children"]:
            for i in range(0, 10):
                try:
                    sleep(randint(5, 20))
                    log.info("Attempting request " + str(i))

                    boto_organizations_client.move_account(
                        AccountId=child["Id"],
                        SourceParentId=event["PhysicalResourceId"],
                        DestinationParentId=responseroot["Roots"][0]["Id"],
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

    except Exception as e:
        log.error(str(e))
