import os
import psycopg
from dotenv import load_dotenv

# 1) Load environment variables from .env
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")


# 2) SQL to create the Calls1 table
# Note: PostgreSQL lowercases unquoted identifiers, so this will be "calls1" internally,
# but you can still query it as Calls1 without quotes.
CREATE_CALLS1_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS Calls1 (
    -- Core event info
    id                      UUID PRIMARY KEY,              -- message.call.id
    org_id                  UUID,                          -- message.call.orgId
    event_timestamp_ms      BIGINT,                        -- message.timestamp (ms since epoch)
    event_type              TEXT,                          -- message.type (e.g. 'tool-calls')

    -- Call-level info
    call_type               TEXT,                          -- call.type (e.g. 'inboundPhoneCall')
    call_status             TEXT,                          -- call.status (if present)
    call_cost               NUMERIC(10,4),                 -- call.cost
    call_created_at         TIMESTAMPTZ,                   -- call.createdAt
    call_updated_at         TIMESTAMPTZ,                   -- call.updatedAt

    -- Transport / provider info
    conversation_type       TEXT,                          -- call.transport.conversationType
    transport_provider      TEXT,                          -- call.transport.provider
    phone_call_provider     TEXT,                          -- call.phoneCallProvider
    phone_call_transport    TEXT,                          -- call.phoneCallTransport
    phone_call_provider_id  TEXT,                          -- call.phoneCallProviderId

    -- Customer info
    customer_number         TEXT,                          -- top-level customer.number or call.customer.number
    customer_sip_uri        TEXT,                          -- customer.sipUri

    -- Our phone number info
    phone_number_id         UUID,                          -- phoneNumber.id or call.phoneNumberId
    phone_number            TEXT,                          -- phoneNumber.number
    phone_number_name       TEXT,                          -- phoneNumber.name

    -- Assistant info
    assistant_id            UUID,                          -- assistant.id
    assistant_org_id        UUID,                          -- assistant.orgId
    assistant_name          TEXT,                          -- assistant.name
    assistant_model         TEXT,                          -- assistant.model.model
    assistant_model_provider TEXT,                         -- assistant.model.provider
    assistant_voice_id      TEXT,                          -- assistant.voice.voiceId
    assistant_voice_provider TEXT,                         -- assistant.voice.provider

    -- High-level text fields from artifact/messages, if you want to extract later
    last_user_message       TEXT,                          -- optional: last user message text
    last_assistant_message  TEXT,                          -- optional: last assistant message text

    -- JSONB buckets for nested data
    tool_calls_json             JSONB,                     -- message.toolCalls
    tool_call_list_json         JSONB,                     -- message.toolCallList
    tool_with_tool_call_list_json JSONB,                   -- message.toolWithToolCallList
    artifact_json               JSONB,                     -- message.artifact
    call_json                   JSONB,                     -- message.call
    phone_number_json           JSONB,                     -- message.phoneNumber
    customer_json               JSONB,                     -- message.customer
    assistant_json              JSONB,                     -- message.assistant

    -- Full raw payload (future-proof everything)
    raw_payload                 JSONB,                     -- entire message object

    -- Audit timestamps
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);
"""

# 3) Helpful indexes
CREATE_INDEXES_SQL = [
    # Look up by customer fast
    "CREATE INDEX IF NOT EXISTS idx_calls1_customer_number ON Calls1 (customer_number);",
    # Time-based queries & dashboards
    "CREATE INDEX IF NOT EXISTS idx_calls1_call_created_at ON Calls1 (call_created_at);",
    # Filter by type of call
    "CREATE INDEX IF NOT EXISTS idx_calls1_call_type ON Calls1 (call_type);",
    # Org-level analytics
    "CREATE INDEX IF NOT EXISTS idx_calls1_org_id ON Calls1 (org_id);"
]


def init_calls1_schema():
    print("Connecting to database...")
    with psycopg.connect(DATABASE_URL) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("Creating Calls1 table (IF NOT EXISTS)...")
            cur.execute(CREATE_CALLS1_TABLE_SQL)

            print("Creating indexes (IF NOT EXISTS)...")
            for stmt in CREATE_INDEXES_SQL:
                cur.execute(stmt)

    print("✅ Calls1 table and indexes are ready.")


if __name__ == "__main__":
    init_calls1_schema()
