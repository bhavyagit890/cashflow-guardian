# Cash-Flow Guardian: Project Spec

Built for the PayPal AI Hackathon (Devpost). Submission deadline: Nov 12, 2026 US evening (Nov 13, 1:30 AM IST). Aim to submit a day early.

## 1. Problem and pitch

Freelancers and tiny businesses do the work, send an invoice, and then wait weeks for payment while their own bills come due. Late payment is a serious cash-flow problem for them, and they usually have no one to chase it.

Cash-Flow Guardian is an AI agent that watches a seller's PayPal invoices, acts when one goes overdue, and warns the owner before a late invoice causes a cash gap.

What the agent does:
- Watches invoices and payment events from the PayPal sandbox (webhooks plus a periodic check).
- When an invoice is overdue, drafts a reminder whose tone fits the client's history (friendly for a good payer, firmer for a repeat late payer) and sends it with a payment link.
- When a client looks like they are struggling, proposes a payment plan by splitting the amount into smaller invoices.
- Tells the owner in plain language when late invoices will cause a cash gap, for example "two late invoices mean you cannot cover rent on the 1st".
- Anything sensitive (payment plans, firm final notices) needs owner approval before it is sent.

Honest limits to state in the submission: the agent cannot force anyone to pay, it only helps recover cash faster and surfaces problems earlier. Client payment history in the demo is seeded sample data because the sandbox has no real history.

## 2. Tech stack

- Backend: Python 3.12, Django 5, Django REST Framework, django-cors-headers
- Frontend: React with Vite and TypeScript, Tailwind CSS, TanStack Query, React Router
- Database: SQLite in development, Postgres on deployment (configure through DATABASE_URL)
- LLM: Gemini via the Google GenAI Python library (API key from Google AI Studio). Keep the model call behind one small function so the provider can be swapped.
- HTTP to PayPal: the `requests` library
- Background work: Django management commands run by cron (no Celery)
- Deployment: Render (Django web service, React static site, cron job)
- Local webhook testing: ngrok or cloudflared tunnel

## 3. Repository layout

```
cashflow-guardian/
  backend/
    manage.py
    config/            (settings, urls)
    core/
      models.py
      serializers.py
      views.py          (REST API for the dashboard)
      webhooks.py       (PayPal webhook view)  <- owner writes this
      paypal_client.py  (token handling and API calls)
      agent/
        loop.py         (agent loop)           <- owner writes this
        tools.py        (tool functions the model can call)
        prompts.py
        llm.py          (single function that calls the model)
      management/commands/
        check_overdue.py
        seed_demo.py
      tests/
  frontend/
    src/ (pages, components, api client)
  SPEC.md
  .env.example
```

## 4. Data models

Client: id, name, email, reliability_score (0 to 100, seeded), avg_days_late, notes.

Invoice: id, paypal_invoice_id, client (FK), amount, currency, issued_at, due_date, status (DRAFT, SENT, OVERDUE, PARTIALLY_PAID, PAID, CANCELLED), payment_link, risk_level (LOW, MEDIUM, HIGH), last_synced_at.

ReminderLog: id, invoice (FK), tone (FRIENDLY, FIRM, FINAL), subject, body, status (DRAFTED, PENDING_APPROVAL, SENT, REJECTED), created_at, sent_at.

PaymentPlan: id, invoice (FK), installments (count), status (PROPOSED, APPROVED, ACTIVE, REJECTED), created_at.

AgentAction: id, invoice (FK, nullable), trigger (WEBHOOK, SCHEDULE, MANUAL), tool_name, tool_input (JSON), tool_output (JSON), reasoning (text), requires_approval (bool), approved (nullable bool), created_at. This is the activity log shown in the dashboard and the main thing judges will see.

WebhookEvent: id, paypal_event_id (unique), event_type, payload (JSON), processed (bool), received_at.

CashFlowSnapshot: id, date, expected_inflow, upcoming_obligations (seeded numbers), projected_gap.

## 5. PayPal integration (sandbox only)

Use sandbox credentials and the sandbox base URL. Authenticate with the OAuth client credentials flow and cache the access token until it expires.

Needed capabilities: create and send an invoice, list and fetch invoices, send an invoice reminder, record or detect payment, cancel an invoice, and receive invoice webhooks (paid, cancelled, and similar). Verify webhook signatures using PayPal's verify-webhook-signature endpoint before trusting any event, and store event ids to ignore duplicates.

IMPORTANT for the coding agent: do not guess endpoints or field names. Read PayPal's official Invoicing and Webhooks documentation (and any PayPal context plugin available) and confirm each call before writing it. Test every call against the sandbox, and write a small script that creates a sample invoice end to end first.

If the PayPal MCP server or Agent Toolkit is easy to wire in, mention it in the write-up. It is optional, and direct REST calls are fine.

## 6. Agent design

Trigger paths: (a) a verified webhook saves a WebhookEvent and returns 200 quickly, (b) the `check_overdue` command runs on a schedule (every 15 minutes in production, manually in the demo) and marks overdue invoices. A separate step processes unprocessed events and overdue invoices by running the agent. Never call the model inside the webhook request.

Tools the model may call (each a plain Python function in tools.py with a JSON schema):
- get_invoice(invoice_id)
- get_client_history(client_id)
- draft_reminder(invoice_id, tone, message)
- send_reminder(reminder_id) which only sends if approved or if tone is FRIENDLY
- propose_payment_plan(invoice_id, installments)
- notify_owner(message, severity)
- get_cash_flow_projection()

Loop: give the model the trigger context and the tools, execute the tool it picks, log an AgentAction, feed the result back, and stop when the model says it is done or after a maximum of 6 steps.

Guardrails:
- FIRM and FINAL reminders and all payment plans require owner approval (requires_approval = true).
- The agent can never cancel, refund, or alter amounts on its own.
- Cap reminders per invoice (maximum 1 per 3 days).
- Log every tool call and the model's short reasoning.
- If the model returns invalid output, log it and fall back to notifying the owner.

## 7. REST API (for the React dashboard)

- GET /api/invoices/ (filter by status and risk)
- GET /api/invoices/{id}/ (with reminders and actions)
- GET /api/actions/ (activity log, newest first)
- POST /api/actions/{id}/approve/ and POST /api/actions/{id}/reject/
- GET /api/summary/ (totals: outstanding, overdue, projected gap)
- POST /api/demo/trigger-overdue/ (demo helper that backdates an invoice and runs the agent)
- POST /api/webhooks/paypal/ (PayPal webhook)

Authentication: a single demo seller. Use a simple token or session and do not build a full signup system.

## 8. Frontend pages

- Dashboard: summary cards (outstanding, overdue, projected cash gap), a cash-flow warning banner, and the invoice table sorted by urgency.
- Invoice detail: timeline of reminders and agent actions, status, payment link.
- Approvals: a queue of actions waiting for owner approval, with approve and reject buttons and the draft text visible.
- Activity log: every agent action with its reasoning.
Poll the API every few seconds (TanStack Query) so the dashboard visibly updates when a webhook arrives during the demo.

## 9. Demo seed data

`seed_demo` creates about 8 clients with varied reliability and 12 invoices across statuses, including two overdue ones from a historically late client and one from a reliable client, plus a CashFlowSnapshot that produces a visible projected gap. Clearly label the data as sample data in the UI footer.

## 10. Security and config

All secrets come from environment variables (see .env.example): PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_WEBHOOK_ID, GEMINI_API_KEY, DJANGO_SECRET_KEY, DATABASE_URL. Never commit secrets. Sandbox only. Verify webhook signatures. Keep DEBUG off in deployment.

## 11. Build order

Week 1: Django project, models, PayPal client, a script creating and listing sandbox invoices, webhook receiver with signature verification, WebhookEvent storage. In parallel, a React dashboard against mock JSON.
Week 2: tools.py, agent loop, approval flow, check_overdue command, AgentAction logging, REST API.
Week 3: connect React to the real API, approvals page, activity log, seed data, cash-flow banner, tests for the tools and webhook.
Week 4: deploy to Render, test the full live loop, record a 2 to 3 minute demo video, write the Devpost description, submit a day early.

## 12. Instructions for the coding agent

- Always produce a plan first and wait for approval before large changes.
- Leave clearly marked TODO stubs with docstrings for `core/webhooks.py` and `core/agent/loop.py`. The project owner is learning Django and will write these files personally.
- Write small commits, add basic tests for tools, serializers, and webhook handling, and explain non-obvious Django code in comments so the owner can learn from it.
- Prefer simple solutions over clever ones. No Celery, no microservices, no extra frameworks.
- Do not invent PayPal API details. Check the official docs.
