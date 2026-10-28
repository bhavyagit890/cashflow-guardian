# Cash-Flow Guardian 💸

**An AI-powered cash-flow monitoring assistant for freelancers and small businesses.**

Cash-Flow Guardian helps freelancers and small business owners monitor unpaid invoices, identify overdue payments, understand upcoming expenses, and prepare personalized payment reminders for review.

Late payments can create cash-flow gaps even when a business has completed its work. Cash-Flow Guardian aims to make those risks easier to understand and help business owners take timely action.

##  
Features

- **Invoice monitoring:** Synchronize and review invoice information from the PayPal Sandbox.
- **Overdue invoice tracking:** Identify invoices that are past their due date and remain unpaid.
- **AI-assisted reminders:** Generate personalized payment reminder drafts.
- **Human approval workflow:** Review, approve, or reject reminder drafts before contacting clients.
- **Cash-flow overview:** View expected invoice receivables, upcoming expenses, and projected cash-flow gaps.
- **Expense tracking:** Review unpaid expenses and their due dates.
- **Webhook processing:** Receive and retry supported PayPal webhook events.
- **Automated agent cycle:** Run the backend agent through a Django management command.
- **Risk assessment:** Apply illustrative rules to classify invoice risk.

## 🛠️ Tech Stack

| Layer | Technologies |
|---|---|
| Frontend | React, TypeScript, Vite, CSS |
| Backend | Python, Django, Django REST Framework |
| Database | SQLite for local development |
| Payments integration | PayPal Sandbox API and webhooks |
| AI integration | Google Gemini API |
| Testing | Django automated tests |

## 🏗️ Project Structure

```text
cashflow-guardian/
├── backend/
│   ├── config/                 # Django project configuration
│   ├── core/
│   │   ├── agent/              # Cash-flow agent logic
│   │   ├── management/commands/ # Agent management commands
│   │   ├── migrations/         # Database migrations
│   │   ├── models.py           # Database models
│   │   ├── serializers.py      # API serializers
│   │   ├── views.py            # API endpoints
│   │   ├── webhooks.py         # PayPal webhook handling
│   │   └── tests.py            # Backend tests
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
└── SPEC.md
```

## ⚙️ Getting Started

### Prerequisites

Install the following before running the project:

- Python 3.12 or a compatible version
- Node.js and npm
- Git

PayPal Sandbox and Gemini credentials are required for the corresponding integrations.

### 1. Clone the repository

```bash
git clone https://github.com/bhavyagit890/cashflow-guardian.git
cd cashflow-guardian
```

### 2. Configure environment variables

Copy the example environment file to create your local `.env` file.

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Fill in the appropriate values in `.env`:

```dotenv
DJANGO_SECRET_KEY=replace-with-a-local-secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

PAYPAL_CLIENT_ID=your-sandbox-client-id
PAYPAL_CLIENT_SECRET=your-sandbox-client-secret
PAYPAL_WEBHOOK_ID=your-webhook-id
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com

GEMINI_API_KEY=your-gemini-api-key
```

Use the exact variable names expected by the application. Never commit your actual `.env` file or expose API credentials.

### 3. Set up the Django backend

From the project root, run:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
cd backend
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py runserver
```

The backend will normally be available at `http://127.0.0.1:8000/`.

### 4. Set up the React frontend

Open a second terminal at the project root and run:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually `http://localhost:5173/`.

## 🧪 Running Tests

From the `backend` directory, with the virtual environment activated:

```powershell
python manage.py test core.tests
```

The test suite covers backend behavior such as reminder approval, agent error handling, invoice synchronization, webhook processing, and other application workflows.

## 🔐 Safety and Design Notes

- **Human-in-the-loop:** Approving a reminder records the owner's decision; approval does not automatically send a message.
- **Reminder drafts:** AI-generated reminders should be reviewed before being used to contact clients.
- **Sandbox integration:** PayPal integration is intended for sandbox development and testing.
- **Forecast limitations:** Cash-flow forecasts are estimates, not guarantees. The current implementation does not perform currency conversion, and partial payments may not be deducted from invoice amounts.
- **Risk assessment:** Risk levels use illustrative rules and should not be interpreted as validated financial predictions.
- **Secrets:** Keep credentials in local environment variables, not in source control.

## 🚧 Current Scope

Cash-Flow Guardian is a development and hackathon project. Its current capabilities and limitations should be evaluated against the implemented code and configured integrations. Production deployment would require additional security, operational, and financial validation.

## 👩‍💻 Author

**Bhavya Tiwari**

GitHub: [@bhavyagit890](https://github.com/bhavyagit890)

---

*Cash-Flow Guardian — helping freelancers understand what is coming in, what is going out, and what needs attention.*
