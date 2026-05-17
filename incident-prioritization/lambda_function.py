import json, boto3, os, logging
from datetime import datetime, timezone
from botocore.config import Config
from prioritizer import calculate_priority

logger = logging.getLogger()
logger.setLevel(logging.INFO)

boto_config = Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2})
dynamodb = boto3.resource("dynamodb", config=boto_config)
sns      = boto3.client("sns", config=boto_config)
TABLE_NAME    = os.environ["DYNAMODB_TABLE"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
RULE_VERSION  = os.environ.get("RULE_VERSION", "v1")

DESCRIPTION_SUFFIX = {
    "CRITICAL": "สถานการณ์อยู่ในขั้นวิกฤต จำเป็นต้องระดมทรัพยากรและตอบสนองทันที",
    "HIGH":     "สถานการณ์รุนแรง จำเป็นต้องเร่งส่งทีมช่วยเหลือและแจ้งเตือนประชาชนในพื้นที่",
    "MEDIUM":   "สถานการณ์น่าเป็นห่วง ควรส่งเจ้าหน้าที่เข้าประเมินและติดตามอย่างใกล้ชิด",
    "LOW":      "สถานการณ์อยู่ในการควบคุม เจ้าหน้าที่กำลังติดตามสถานการณ์",
}

def build_description(base_desc: str, priority: str) -> str:
    suffix = DESCRIPTION_SUFFIX.get(priority, "")
    base = base_desc.strip() if base_desc else ""
    return f"{base} {suffix}".strip()

def handler(event, context):
    trace_id = context.aws_request_id
    table = dynamodb.Table(TABLE_NAME)
    for record in event["Records"]:
        try:
            body = json.loads(record["body"])
            incident = json.loads(body["Message"]) if "Message" in body else body
            logger.info(json.dumps({"operation": "Received", "traceId": trace_id, "incident": incident}))

            incident_id     = incident.get("incident_id") or incident.get("incidentId")
            incident_type   = incident.get("incident_type") or incident.get("incidentType", "UNKNOWN")
            severity        = incident.get("severity")
            upstream_status = incident.get("status", "")
            affected_count  = incident.get("affected_count")
            address_name    = incident.get("address_name", "")

            if not incident_id:
                logger.error(json.dumps({"operation": "MissingIncidentId", "traceId": trace_id}))
                continue

            # Idempotency check
            existing = table.get_item(Key={"incident_id": incident_id}).get("Item")
            if existing:
                logger.info(json.dumps({"operation": "AlreadyProcessed", "traceId": trace_id, "incident_id": incident_id}))
                continue

            verification_status = upstream_status.upper()
            priority, decision_reason = calculate_priority(
                incident_type, severity, affected_count,
                incident.get("description", ""), address_name
            )
            now = datetime.now(timezone.utc).isoformat()
            base_desc = incident.get("description", "")
            enriched_description = build_description(base_desc, priority)

            # Save to DynamoDB
            table.put_item(Item={
                "incident_id":    incident_id,
                "disaster_type":  incident_type,
                "severity_level": severity,
                "description":    enriched_description,
                "priority":       priority,
                "decisionReason": decision_reason,
                "status":         "PRIORITIZED",
                "created_at":     now,
                "updated_at":     now,
                "classifiedAt":   now,
                "lastUpdatedAt":  now,
                "version":        1,
                "source":         "TrustedNews",
                "ruleVersion":    RULE_VERSION,
            })
            logger.info(json.dumps({"operation": "Saved", "traceId": trace_id, "incident_id": incident_id}))

            # Publish to SNS
            result = {
                "schemaVersion":    "1.0",
                "incident_Id":      incident_id,
                "status":           verification_status,
                "severity":         priority,
                "description":      enriched_description,
                "prioritizeStatus": "PRIORITIZE",
                "operatorId":       "IncidentPrioritizationService",
                "classifiedAt":     now,
            }
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Message=json.dumps(result, ensure_ascii=False),
                Subject="IncidentPrioritized",
                MessageAttributes={"priority": {"DataType": "String", "StringValue": priority}}
            )
            logger.info(json.dumps({"operation": "Published", "traceId": trace_id, "result": result}))

        except Exception as e:
            logger.error(json.dumps({"operation": "Error", "traceId": trace_id, "error": str(e)}))
            raise
    return {"statusCode": 200}