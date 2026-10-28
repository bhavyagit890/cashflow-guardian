const API_BASE_URL = "/api";

async function fetchApi<T>(endpoint: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(
      `API request failed: ${endpoint} (${response.status})`
    );
  }

  return response.json() as Promise<T>;
}

export interface Invoice {
  id: number;
  paypal_invoice_id: string;
  amount: string;
  currency: string;
  due_date: string;
  status: string;
  is_overdue: boolean;
  risk_level: string;
  client: number;
}

export interface Expense {
  id: number;
  description: string;
  amount: string;
  currency: string;
  due_date: string;
  category: string;
  is_paid: boolean;
}

export interface Reminder {
  id: number;
  subject: string;
  body: string;
  status: string;
  tone: string;
  invoice: number;
}

export interface CashFlowSnapshot {
  id: number;
  date: string;
  expected_inflow: string;
  upcoming_obligations: string;
  projected_gap: string;
}

export const getInvoices = () => fetchApi<Invoice[]>("/invoices/");
export const getExpenses = () => fetchApi<Expense[]>("/expenses/");
export const getReminders = () => fetchApi<Reminder[]>("/reminders/");

export const getCashFlowSnapshots = () =>
  fetchApi<CashFlowSnapshot[]>("/cash-flow-snapshots/");


export async function reviewReminder(
  reminderId: number,
  action: "approve" | "reject"
): Promise<{ message: string; reminder_id: number; status: string }> {
  const response = await fetch(
    `${API_BASE_URL}/reminders/${reminderId}/${action}/`,
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken") ?? "",
      },
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to ${action} reminder (${response.status})`);
  }

  return response.json();
}

function getCookie(name: string): string | null {
  const cookies = document.cookie.split("; ");

  for (const cookie of cookies) {
    const [key, ...value] = cookie.split("=");

    if (key === name) {
      return decodeURIComponent(value.join("="));
    }
  }

  return null;
}