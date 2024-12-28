import json
from urllib.request import build_opener, HTTPHandler, Request

import core_logging as log


def send_response(event, context, responseStatus, responseData, physicalId):
    responseBody = json.dumps(
        {
            "Status": responseStatus,
            "Reason": "See the details in CloudWatch Log Stream: "
            + context.log_stream_name
            + "\n"
            + responseData["Message"],
            "PhysicalResourceId": physicalId,
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
            "Data": responseData,
        }
    )

    log.info("ResponseURL: {}".format(event["ResponseURL"]))
    log.info("ResponseBody: {}".format(responseBody))

    opener = build_opener(HTTPHandler)

    request = Request(
        event["ResponseURL"],
        data=responseBody.encode(encoding="utf_8", errors="strict"),
    )

    request.add_header("Content-Type", "")
    request.add_header("Content-Length", len(responseBody))
    request.get_method = lambda: "PUT"

    response = opener.open(request)

    log.info(("Status code: {}".format(response.getcode())))
    log.info(("Status message: {}".format(response.msg)))
