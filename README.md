# Cash-Flow Guardian 💸

**An AI-powered cash-flow monitoring assistant for freelancers and small businesses.**

Cash-Flow Guardian helps freelancers and small business owners monitor unpaid invoices, identify overdue payments, understand upcoming expenses, and prepare personalized payment reminders for review.

Late payments can create cash-flow gaps even when a business has completed its work. Cash-Flow Guardian aims to make those risks easier to understand and help business owners take timely action.

## ✨ Features

- **Invoice monitoring:** Track invoice amounts, due dates, payment statuses, and PayPal invoice references.
- **Overdue invoice tracking:** Identify invoices that are past their due date and remain unpaid.
- **AI-assisted reminders:** Generate personalized payment reminder drafts using Google Gemini.
- **Human approval workflow:** Review, approve, or reject reminder drafts before contacting clients.
- **Cash-flow overview:** View expected invoice receivables, upcoming expenses, and projected cash-flow gaps.
- **Expense tracking:** Record and review business expenses, payment status, and due dates.
- **Webhook processing:** Receive PayPal invoice events, verify signatures, and persist supported events.
- **Pending event retry:** Retry previously saved webhook events through a Django management command.
- **Automated agent cycle:** Run the backend cash-flow agent through a Django management command.
- **Risk assessment:** Apply illustrative rules to classify invoice risk.
- **Business data isolation:** Keep business records scoped to the authenticated user's workspace.

## 🛠️ Tech Stack

| Layer | Technologies |
|---|---|
| Frontend | React 19, TypeScript, Vite, CSS |
| Backend | Python, Django 5.2, Django REST Framework |
| Database | SQLite (local development), PostgreSQL (production) |
| Payments Integration | PayPal Sandbox API and Webhooks |
| AI Integration | Google Gemini API |
| Authentication | Django REST Framework Token Authentication |
| Deployment | Render |
| Static Files | WhiteNoise |
| Application Server | Gunicorn |
| Testing | Django automated tests |

## 🏗️ Project Structure

```text
cashflow-guardian/
├── backend/
│   ├── config/                   # Django project configuration
│   ├── core/
│   │   ├── agent/                # Cash-flow agent logic
│   │   ├── management/commands/  # Management commands
│   │   ├── migrations/           # Database migrations
│   │   ├── models.py             # Database models
│   │   ├── serializers.py        # API serializers
│   │   ├── views.py              # API endpoints
│   │   ├── webhooks.py           # PayPal webhook handling
│   │   └── tests.py              # Backend tests
│   ├── manage.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── App.css
│   │   └── api.ts
│   ├── package.json
│   └── vite.config.ts
├── .env.example
├── .gitignore
├── README.md
└── SPEC.md
```

## ⚙️ Getting Started

### Prerequisites

- Python 3.12 or a compatible version
- Node.js and npm
- Git
- PayPal Sandbox developer account (for payment integration)
- Google Gemini API key (for AI reminder generation)

### 1. Clone the repository

```bash
git clone https://github.com/bhavyagit890/cashflow-guardian.git
cd cashflow-guardian
```

### 2. Create and configure environment variables

Create a local `.env` file using the example:

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

Configure the following variables in `.env`:

```dotenv
DJANGO_SECRET_KEY=replace-with-a-random-secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

PAYPAL_CLIENT_ID=your-sandbox-client-id
PAYPAL_CLIENT_SECRET=your-sandbox-client-secret
PAYPAL_WEBHOOK_ID=your-webhook-id
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com

GEMINI_API_KEY=your-gemini-api-key

DEMO_USERNAME=your-demo-username
DEMO_PASSWORD=your-demo-password
DEMO_BUSINESS_NAME=your-demo-business-name
```

The three `DEMO_` variables are used by the demo data management command. Add them to your local `.env` if you intend to run that command.

For local development, `DATABASE_URL` can remain unset when using the configured SQLite fallback.

Never commit your actual `.env` file or expose API credentials.

### 3. Set up the Django backend

From the project root, create a virtual environment and activate it:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Navigate to the backend directory:

```powershell
cd backend
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Apply database migrations:

```powershell
python manage.py migrate
```

Check the Django configuration:

```powershell
python manage.py check
```

Create demo data (optional):

```powershell
python manage.py seed_demo
```

Start the development server:

```powershell
python manage.py runserver
```

The backend will normally be available at:

`http://127.0.0.1:8000/`

### 4. Set up the React frontend

Open a second terminal at the project root:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually:

`http://localhost:5173/`

## 🧪 Running Tests

From the `backend` directory, with the virtual environment activated:

```powershell
python manage.py test core
```

The current backend test suite contains **55 passing tests**.

It covers:

- PayPal webhook verification and event processing
- Invoice synchronization logic
- Reminder approval and rejection
- Business ownership and data isolation
- Cash-flow forecasting
- Agent behavior and error handling

## 🔐 Safety and Design Notes

- **Human-in-the-loop:** Approving a reminder records the owner's decision. Approval does not automatically send an email or message.
- **Reminder drafts:** AI-generated reminders should be reviewed before being used to contact clients.
- **Sandbox integration:** PayPal integration is configured for Sandbox development and testing.
- **Webhook security:** Incoming PayPal webhook events undergo signature verification before being persisted and processed.
- **Pending events:** Events for invoices that do not yet exist locally are retained for retry.
- **Forecast limitations:** Cash-flow forecasts are estimates, not guarantees. The current implementation does not perform currency conversion, and partial payments may not be deducted from invoice amounts.
- **Risk assessment:** Risk levels use illustrative rules and should not be interpreted as validated financial predictions.
- **Secrets:** Keep credentials in environment variables, not in source control.

## 🚧 Current Scope and Limitations

Cash-Flow Guardian is a development and hackathon project.

- PayPal invoice fetching and synchronization logic is implemented and tested, but automatic synchronization of externally created invoices is not yet integrated into the production webhook workflow.
- PayPal webhook delivery, signature verification, and event persistence have been verified in the deployed application.
- Webhook events without matching local invoices remain pending until they can be processed.
- The pending webhook retry mechanism exists through a Django management command, but scheduled production execution has not yet been verified.
- AI-generated reminders require owner review and are not automatically emailed.
- Forecasting assumes consistent currencies and does not deduct partial invoice payments.
- Production use would require additional security, operational, and financial validation.

## 🌐 Live Demo

**Application:** https://cashflow-guardian.onrender.com

**GitHub Repository:** https://github.com/bhavyagit890/cashflow-guardian

## 👩‍💻 Author

**Bhavya Tiwari**

GitHub: [@bhavyagit890](https://github.com/bhavyagit890)

---

*Cash-Flow Guardian — helping freelancers understand what is coming in, what is going out, and what needs attention.*