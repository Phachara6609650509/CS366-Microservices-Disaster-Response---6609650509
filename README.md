# IncidentPrioritization Service

**CS366 Microservices — Disaster Response System**
Service Owner: นาย พชร พรพงศ์ `6609650509` ภาคพิเศษ

---

## Overview

IncidentPrioritization Service รับผิดชอบการจำแนกประเภทภัยพิบัติและจัดกลุ่มระดับความเร่งด่วน (priority) ของเหตุการณ์ เพื่อสนับสนุนทีมกู้ภัยในการตัดสินใจว่าเหตุการณ์ใดควรได้รับการช่วยเหลือก่อน โดยใช้ **rule-based decision logic** ที่ชัดเจนและโปร่งใส

**Pain Point ที่แก้ไข:** ในสถานการณ์ภัยพิบัติมักมีเหตุการณ์จำนวนมากถูกแจ้งพร้อมกันโดยไม่มีการจัดลำดับความสำคัญ บริการนี้แปลงข้อมูลเหตุการณ์ให้เป็นระดับความสำคัญที่เข้าใจง่าย เพื่อสนับสนุนการตัดสินใจภาคสนาม

---

## Architecture

```
Trusted News Outlets
        │
        ▼ SNS (incident-prioritization-topic)
        │
        ▼ SQS (incident-prioritization-queue)
        │                    │ fail > 3 ครั้ง
        │                    ▼
        │              SQS DLQ
        ▼
Lambda IncidentPrioritizationFunction
        │                    │
        ▼                    ▼
  DynamoDB            SNS (incident-prioritized-topic)
  (store)                    │
                             ▼
                    IncidentReporter Service

API Gateway ──► Lambda IncidentApiHandlerFunction ──► DynamoDB (read)
```

**Two communication patterns:**
- **Async (Event-driven):** SNS → SQS → Lambda → DynamoDB + SNS publish
- **Sync (REST API):** API Gateway → Lambda → DynamoDB (read-only)

---

## Service Boundary

### In-scope
- รับ incident event จาก Trusted News Outlets ผ่าน SNS → SQS → Lambda
- จำแนกประเภทภัยพิบัติ: `EARTHQUAKE` / `FLOOD` / `STORM`
- ประเมิน priority: `CRITICAL` / `HIGH` / `MEDIUM` / `LOW`
- สร้าง enriched description ตามระดับความรุนแรง
- บันทึกผลลัพธ์ลง DynamoDB
- Publish ผลลัพธ์ไปยัง SNS downstream
- REST API สำหรับดึงข้อมูล incident ที่ผ่านการ prioritize แล้ว

### Out-of-scope
- การรับแจ้งเหตุและจัดเก็บ incident master data
- การสั่งการหรือ dispatch หน่วยกู้ภัย
- การจัดสรรทรัพยากรหรือยานพาหนะ
- การจัดการศูนย์พักพิง
- การ authenticate ผู้ใช้งาน

---

## Priority Decision Logic

### Step 1 — Base Priority (by incident_type)

| Incident Type | Base Priority |
|--------------|--------------|
| EARTHQUAKE | HIGH |
| FLOOD | MEDIUM |
| STORM | MEDIUM |
| อื่นๆ (fallback) | MEDIUM |

> `severity` ที่ส่งมาจาก upstream จะเป็น `null` เสมอ — ระบบกำหนด base priority จาก `incident_type` โดยอัตโนมัติ

### Step 2 — Boost Logic (max +2)

| Factor | เงื่อนไข | คะแนน |
|--------|---------|-------|
| `affected_count` | >= 500 | +2 |
| `affected_count` | >= 100 | +1 |
| Keyword ใน description/address | ติดอยู่, trapped, เสียชีวิต, บาดเจ็บสาหัส, ถล่ม, collapsed, อพยพ, evacuate, หลายร้อย, หลายพัน, โรงพยาบาล, โรงเรียน, มหาวิทยาลัย | +1 |

### Step 3 — Downgrade Logic (max -2)

| Factor | เงื่อนไข | คะแนน |
|--------|---------|-------|
| `affected_count` | < 20 | -1 |
| Keyword ใน description/address | เล็กน้อย, เบาๆ, ขัง, ขัดการจราจร | -1 |
| ไม่มี serious keyword + `affected_count` | < 50 | -1 |

### Step 4 — Floor Priority (ขั้นต่ำ)

| Incident Type | Min Priority |
|--------------|-------------|
| EARTHQUAKE | MEDIUM |
| FLOOD | LOW |
| STORM | LOW |

### ตัวอย่างผลลัพธ์

| Scenario | Base | Boost | Downgrade | Result |
|----------|------|-------|-----------|--------|
| EARTHQUAKE + 5 คน + "เบาๆ เล็กน้อย" | HIGH | 0 | -2 → floor | **MEDIUM** |
| FLOOD + 150 คน + "น้ำท่วมสูง" | MEDIUM | +1 | 0 | **HIGH** |
| FLOOD + 600 คน + "หลายร้อยหลัง อพยพ" | MEDIUM | +2 | 0 | **CRITICAL** |
| FLOOD + 300 คน + "โรงพยาบาล ติดอยู่" | MEDIUM | +2 | 0 | **CRITICAL** |
| STORM + 30 คน + "ลมแรง ฝนตกหนัก" | MEDIUM | 0 | -1 | **LOW** |
| STORM + 25 คน + "บ้านเรือนเสียหาย" | MEDIUM | 0 | 0 | **MEDIUM** |
| FLOOD + 8 คน + "น้ำขังเล็กน้อย" | MEDIUM | 0 | -2 | **LOW** |

---

## REST API

**Base URL:** `https://l8k58q9rl6.execute-api.us-east-1.amazonaws.com/prod`

### GET /v1/incidents
ดึงรายการ incident ที่ผ่านการ prioritize ทั้งหมด

```bash
curl https://l8k58q9rl6.execute-api.us-east-1.amazonaws.com/prod/v1/incidents
```

**Response 200:**
```json
[
  {
    "incident_id": "INC_0001",
    "priority": "HIGH",
    "status": "PRIORITIZED",
    "disaster_type": "FLOOD",
    "description": "น้ำท่วมสูง สถานการณ์รุนแรง...",
    "decisionReason": "FLOOD default=MEDIUM | boost +1: affected_count=150",
    "classifiedAt": "2026-05-11T19:11:26+00:00",
    "source": "TrustedNews",
    "ruleVersion": "v1"
  }
]
```

---

### GET /v1/incidents/{id}
ดึงข้อมูล incident เฉพาะ ID

```bash
curl https://l8k58q9rl6.execute-api.us-east-1.amazonaws.com/prod/v1/incidents/INC_0001
```

| Status | Description |
|--------|-------------|
| 200 | พบข้อมูล |
| 404 | `{ "message": "Incident INC_0001 not found", "traceId": "..." }` |

---

### GET /v1/incidents/priority/{level}
ดึง incident ตาม priority level (`CRITICAL` / `HIGH` / `MEDIUM` / `LOW`)

```bash
curl https://l8k58q9rl6.execute-api.us-east-1.amazonaws.com/prod/v1/incidents/priority/CRITICAL
```

| Status | Description |
|--------|-------------|
| 200 | รายการ incident ตาม priority |
| 400 | `{ "message": "No incidents found with priority HIGH", "traceId": "..." }` |

---

## Message Contracts

### Upstream — รับจาก Trusted News Outlets (Async)

**Channel:** SNS → SQS `incident-prioritization-queue`

```json
{
  "incident_id": "INC_0009",
  "incident_type": "FLOOD",
  "severity": null,
  "status": "VERIFIED",
  "affected_count": 150,
  "address_name": "ถนนสุขุมวิท กรุงเทพมหานคร",
  "description": "น้ำท่วมสูงระดับเข่า บริเวณถนนสุขุมวิท",
  "incident_start": "2026-05-17T00:00:00.000Z"
}
```

### Downstream — ส่งให้ IncidentReporter Service (Async / fire-and-forget)

**Channel:** SNS `incident-prioritized-topic`

```json
{
  "schemaVersion": "1.0",
  "incident_Id": "INC_0009",
  "status": "VERIFIED",
  "severity": "HIGH",
  "description": "น้ำท่วมสูง สถานการณ์รุนแรง จำเป็นต้องเร่งส่งทีมช่วยเหลือ...",
  "prioritizeStatus": "PRIORITIZE",
  "operatorId": "IncidentPrioritizationService",
  "classifiedAt": "2026-05-17T14:11:26+00:00"
}
```

---

## Non-Functional Requirements

| Requirement | Implementation |
|-------------|---------------|
| **Idempotency** | เช็ค `incident_id` ใน DynamoDB ก่อนประมวลผล — ถ้าซ้ำจะ skip ทันที |
| **Concurrency** | Lambda reserved concurrency = 3 |
| **Timeout** | boto3 `connect_timeout=3s`, `read_timeout=5s` |
| **DLQ** | SQS DLQ รับ message ที่ fail เกิน 3 ครั้ง |
| **Observability** | Structured JSON log + `traceId` + `X-Trace-Id` header |
| **Schema Versioning** | `schemaVersion: 1.0` ใน SNS message |
| **Decision Transparency** | ฟิลด์ `decisionReason` บันทึกทุก factor (boost/downgrade reason) |
| **Priority Floor** | EARTHQUAKE ต่ำสุด MEDIUM, FLOOD/STORM ต่ำสุด LOW |

---

## AWS Resources

| Resource | ARN / URL |
|----------|-----------|
| API Gateway | `https://l8k58q9rl6.execute-api.us-east-1.amazonaws.com/prod` |
| SNS Topic (downstream) | `arn:aws:sns:us-east-1:552692352531:incident-prioritized-topic` |
| SQS Queue | `arn:aws:sqs:us-east-1:552692352531:incident-prioritization-queue` |
| DynamoDB Table | `arn:aws:dynamodb:us-east-1:552692352531:table/incident-prioritization-table` |
| SNS Topic (upstream, Trusted News) | `arn:aws:sns:us-east-1:445880711982:incident-prioritization-topic` |

---

## Service Interactions

| Direction | Service | Channel | Style |
|-----------|---------|---------|-------|
| Upstream | Trusted News Outlets | SNS → SQS | Async (event-driven) |
| Downstream | IncidentReporter Service | SNS | Async (fire-and-forget) |
| Downstream | Command Center Dashboard | REST API | Sync |
| Downstream | Dispatch Service | REST API | Sync |

---

## Repository Structure

| File | Description |
|------|-------------|
| [`lambda_function.py`](incident-prioritization/lambda_function.py) | SQS trigger handler — calculate priority, save DynamoDB, publish SNS |
| [`prioritizer.py`](incident-prioritization/prioritizer.py) | Rule-based priority logic: base + boost/downgrade + floor |
| [`api_handler.py`](incident-prioritization/api_handler.py) | REST API handler สำหรับ GET /v1/incidents endpoints |

---

## Target Users

บริการนี้เป็น **backend service** สำหรับระบบตอบสนองภัยพิบัติ ไม่ได้ออกแบบให้ประชาชนเรียกใช้โดยตรง

- **IncidentReporter Service** — รับผลลัพธ์การ prioritize แบบ async ผ่าน SNS
- **Command Center Dashboard** — ดึงข้อมูลผ่าน REST API
- **Dispatch Service** — ดึงข้อมูลเพื่อตัดสินใจส่งทีมช่วยเหลือ
