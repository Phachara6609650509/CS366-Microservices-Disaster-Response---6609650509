import json
import boto3
import os
import logging
from boto3.dynamodb.conditions import Attr
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

boto_config = Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2})
dynamodb = boto3.resource("dynamodb", config=boto_config)
TABLE_NAME = os.environ["DYNAMODB_TABLE"]

def format_incident(item):
    return {
        "incident_id":        item.get("incident_id"),
        "priority":           item.get("priority"),
        "status":             item.get("status"),
        "verificationStatus": item.get("verificationStatus"),
        "classifiedAt":       item.get("classifiedAt"),
        "disaster_type":      item.get("disaster_type"),
        "severity_level":     item.get("severity_level"),
        "decisionReason":     item.get("decisionReason"),
        "source":             item.get("source"),
        "ruleVersion":        item.get("ruleVersion"),
        "version":            item.get("version"),
        "created_at":         item.get("created_at"),
        "updated_at":         item.get("updated_at"),
        "lastUpdatedAt":      item.get("lastUpdatedAt"),
        "description":        item.get("description"),
    }

def handler(event, context):
    trace_id = context.aws_request_id
    table = dynamodb.Table(TABLE_NAME)

    http_method = event.get("httpMethod")
    path = event.get("path", "")
    path_params = event.get("pathParameters") or {}

    logger.info(json.dumps({"operation": "Request", "traceId": trace_id, "method": http_method, "path": path}))

    try:
        # GET /incidents or /v1/incidents
        if http_method == "GET" and path in ("/incidents", "/v1/incidents"):
            result = table.scan()
            return response(200, [format_incident(i) for i in result["Items"]], trace_id)

        # GET /incidents/priority/{level} or /v1/incidents/priority/{level}
        elif http_method == "GET" and "level" in path_params:
            level = path_params["level"].upper()
            result = table.scan(FilterExpression=Attr("priority").eq(level))
            items = result.get("Items", [])
            if not items:
                return response(404, {"message": f"No incidents found with priority {level}"}, trace_id)
            return response(200, [format_incident(i) for i in items], trace_id)

        # GET /incidents/{id} or /v1/incidents/{id}
        elif http_method == "GET" and "id" in path_params:
            incident_id = path_params["id"]
            result = table.get_item(Key={"incident_id": incident_id})
            item = result.get("Item")
            if not item:
                return response(404, {"message": f"Incident {incident_id} not found"}, trace_id)
            return response(200, format_incident(item), trace_id)

        else:
            return response(404, {"message": "Route not found"}, trace_id)

    except Exception as e:
        logger.error(json.dumps({"operation": "Error", "traceId": trace_id, "error": str(e)}))
        return response(500, {"message": "Internal server error"}, trace_id)


def response(status_code, body, trace_id=None):
    if isinstance(body, dict) and status_code >= 400:
        body["traceId"] = trace_id or ""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "X-Trace-Id": trace_id or "",
        },
        "body": json.dumps(body, default=str),
    }