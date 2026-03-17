# FuelPass Support Skill

## Overview

The FuelPass Support Skill is a telephony-based AI assistant designed to help users with Sri Lanka’s National Fuel Pass QR system.

It operates via inbound SIP calls using LiveKit and provides automated support in Sinhala and Tamil.

The assistant answers frequently asked questions related to vehicle registration, QR code usage, and common issues using an official knowledge base.

If a question cannot be answered using the knowledge base, the system automatically creates a support ticket via AgentMail.

---

## Supported Languages

- Sinhala
- Tamil

Language selection is performed using DTMF input during the call:

- Press 1 → Sinhala
- Press 2 → Tamil

---

## Capabilities

The assistant can:

- Answer Fuel Pass FAQ questions
- Guide users on vehicle registration issues
- Explain QR code usage
- Provide troubleshooting steps for common errors
- Assist with OTP issues
- Provide information on eligibility and requirements
- Offer support contact information
- Escalate unresolved issues to human support

---

## Knowledge Source

Responses are generated strictly from an internal Fuel Pass FAQ knowledge base derived from official guidance.

The assistant MUST NOT provide information outside this knowledge base.

---

## Tool Integration

### AgentMail Ticketing Tool

Used when the assistant cannot answer a Fuel Pass–related question with certainty.

#### Purpose

Create a complaint/support ticket for follow-up by a human support team.

#### Trigger Condition

- The question is Fuel Pass–related
- The answer is not present in the knowledge base
- The assistant is not fully confident

#### Inputs

- Question summary (1–2 sentences)
- Caller phone number (automatically inferred from SIP headers: `sip.phoneNumber`, `sip.from`, etc., or passed manually)

#### Output

- Ticket created via email (Subject format: `complaint ####` with a unique 4-digit ID)
- Reuses or creates a dedicated AgentMail Inbox per username to prevent hitting inbox limits
- Unique complaint number generated

---

## Escalation Behavior

When escalation occurs:

1. A ticket is automatically created via AgentMail.
2. The caller is informed that their request has been forwarded.
3. No additional information is provided beyond the standard message.

---

## Behavioral Rules

The assistant must:

- Respond only in the selected language
- Use only the approved knowledge base
- Avoid guessing or hallucinating information
- Escalate when unsure
- Remain polite and concise
- Provide clear instructions to callers
- Not engage in unrelated conversation

---

## Limitations

The assistant cannot:

- Access real-time Fuel Pass databases
- Modify vehicle registrations
- Check fuel quota balances
- Process payments
- Verify personal user records
- Provide information beyond the knowledge base

---

## Telephony Integration

### Platform

- LiveKit Agents framework
- SIP inbound calling

### Call Flow

1. Caller connects via inbound SIP call
2. Greeting audio (`assets/welcomeMSG.wav`) is played in a loop
3. Caller selects language via DTMF (1 for Sinhala, 2 for Tamil)
4. AI assistant (`gemini-live-2.5-flash-native-audio` via Vertex AI) joins the call
5. Conversation begins
6. Escalation occurs if needed via AgentMail tool
7. Call ends normally

---

## Technical Components

- LiveKit AgentSession workflow
- Google Realtime LLM using Vertex AI (`gemini-live-2.5-flash-native-audio`)
- Silero Voice Activity Detection (VAD)
- SIP DTMF event handling for language selection
- Audio playback for the initial greeting file
- AgentMail API for ticket creation with Inbox caching
- Automatic Caller ID extraction from SIP attributes

---

## Configuration & Environment

To run the agent, the following environment variables are required:

- **Google Cloud Platform (GCP)**
  - `GCP_PROJECT`: Your GCP project ID for Vertex AI.
  - `GCP_LOCATION`: Your GCP location (e.g., `us-central1`).
- **AgentMail**
  - `AGENTMAIL_API_KEY`: API key for AgentMail.
  - `AGENTMAIL_USERNAME`: Username for Inbox creation/identification.
  - `AGENTMAIL_TO_EMAIL`: The destination email for escalated tickets.
  - `AGENTMAIL_INBOX_ID` (Optional): To explicitly pin a specific inbox.

---

## Intended Use

This skill is designed for automated customer support for the Fuel Pass system through voice calls.

It is suitable for deployment in IVR systems and government service hotlines.

---

## Future Enhancements (Optional)

Potential improvements may include:

- Additional languages
- Integration with official Fuel Pass APIs
- Real-time quota checks
- SMS notifications
- Expanded knowledge base
- Multi-skill routing
