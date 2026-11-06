
const API_BASE_URL = "/api";

export function getAuthToken(): string | null {
  return localStorage.getItem("authToken");
}

async function fetchApi<T>(endpoint: string): Promise<T> {
  const token = getAuthToken();

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: {
      ...(token && {
        Authorization: `Token ${token}`,
      }),
    },
  });

  if (response.status === 401) {
    localStorage.removeItem("authToken");
    window.location.href = "/";
    throw new Error("Session expired. Please log in again.");
  }

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
  const token = getAuthToken();

  const response = await fetch(
    `${API_BASE_URL}/reminders/${reminderId}/${action}/`,
    {
      method: "POST",
      headers: {
        ...(token && {
          Authorization: `Token ${token}`,
        }),
      },
    }
  );

  if (response.status === 401) {
    localStorage.removeItem("authToken");
    window.location.href = "/";
    throw new Error("Session expired. Please log in again.");
  }

  if (!response.ok) {
    let errorMessage = `Failed to ${action} reminder (${response.status})`;

    try {
      const errorData = await response.json();
      errorMessage =
        errorData.error ?? errorData.message ?? errorMessage;
    } catch {
      // Keep the fallback message if the response isn't JSON.
    }

    throw new Error(errorMessage);
  }

  return response.json();
}
