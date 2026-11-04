
import { useCallback, useEffect, useState } from "react";
import "./App.css";

import {
  getInvoices,
  getExpenses,
  getReminders,
  getCashFlowSnapshots,
  reviewReminder,
  type Invoice,
  type Expense,
  type Reminder,
  type CashFlowSnapshot,
} from "./api";

type Page = "Dashboard" | "Invoices" | "Reminders" | "Expenses";

function money(value: string | number, currency = "USD") {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
  }).format(Number(value) || 0);
}

function readableStatus(status: string) {
  return status.replaceAll("_", " ");
}

function App() {
  const [page, setPage] = useState<Page>("Dashboard");
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [snapshots, setSnapshots] = useState<CashFlowSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [reviewingReminder, setReviewingReminder] =
    useState<number | null>(null);

  const loadData = useCallback(async () => {
    try {
      const results = await Promise.allSettled([
        getInvoices(),
        getExpenses(),
        getReminders(),
        getCashFlowSnapshots(),
      ]);

      const failures: string[] = [];

      if (results[0].status === "fulfilled") {
        setInvoices(results[0].value);
      } else {
        failures.push("Invoices could not be loaded.");
      }

      if (results[1].status === "fulfilled") {
        setExpenses(results[1].value);
      } else {
        failures.push("Expenses could not be loaded.");
      }

      if (results[2].status === "fulfilled") {
        setReminders(results[2].value);
      } else {
        failures.push("Reminders could not be loaded.");
      }

      if (results[3].status === "fulfilled") {
        setSnapshots(results[3].value);
      } else {
        failures.push("Cash-flow snapshots could not be loaded.");
      }

      setErrors(failures);
    } catch {
      setErrors([
        "Something went wrong while loading dashboard data.",
      ]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Defer the initial data load until after the effect runs.
    // This avoids synchronously triggering state updates inside the effect.
    const timeoutId = window.setTimeout(() => {
      void loadData();
    }, 0);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [loadData]);

  async function handleReminderReview(
    reminderId: number,
    action: "approve" | "reject"
  ) {
    setMessage("");

    try {
      setReviewingReminder(reminderId);
      await reviewReminder(reminderId, action);
      await loadData();

      setMessage(
        action === "approve"
          ? "Reminder approved. No message was sent."
          : "Reminder rejected. No message was sent."
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not update the reminder."
      );
    } finally {
      setReviewingReminder(null);
    }
  }

  const pendingReminders = reminders.filter(
    (reminder) => reminder.status === "PENDING_APPROVAL"
  );

  const overdueInvoices = invoices.filter(
    (invoice) => invoice.is_overdue
  );

  const unpaidExpenses = expenses.filter(
    (expense) => !expense.is_paid
  );

  const latestSnapshot = snapshots.length
    ? [...snapshots].sort(
        (a, b) => b.date.localeCompare(a.date)
      )[0]
    : undefined;

  const expectedInflow = invoices
    .filter(
      (invoice) =>
        invoice.status === "SENT" ||
        invoice.status === "PARTIALLY_PAID"
    )
    .reduce(
      (total, invoice) => total + Number(invoice.amount),
      0
    );

  const upcomingExpenses = latestSnapshot
    ? Number(latestSnapshot.upcoming_obligations)
    : unpaidExpenses.reduce(
        (total, expense) => total + Number(expense.amount),
        0
      );

 // Backend projected_gap = obligations - expected inflow.
// Negative means surplus; positive means shortfall.
  const netForecast = latestSnapshot
  ? Number(latestSnapshot.projected_gap)
  : upcomingExpenses - expectedInflow;

const forecastLabel =
  netForecast < 0
    ? "Projected Surplus"
    : netForecast > 0
      ? "Projected Shortfall"
      : "Balanced Forecast";

const forecastAmount = money(Math.abs(netForecast));


  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon">C</span>
          <span>
            CashFlow <strong>Guardian</strong>
          </span>
        </div>

        <p className="sidebar-label">WORKSPACE</p>

        <nav className="sidebar-nav">
          {(
            ["Dashboard", "Invoices", "Reminders", "Expenses"] as Page[]
          ).map((item) => (
            <button
              key={item}
              type="button"
              className={
                page === item ? "nav-item active" : "nav-item"
              }
              onClick={() => setPage(item)}
            >
              {item === "Dashboard" && "▦"}
              {item === "Invoices" && "▤"}
              {item === "Reminders" && "✉"}
              {item === "Expenses" && "↗"} {item}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <strong>Demo Workspace</strong>
          <p>Freelancer account</p>
        </div>
      </aside>

      <main className="main-content">
        <header className="page-header">
          <div>
            <p className="eyebrow">
              {page === "Dashboard"
                ? "FINANCIAL OVERVIEW"
                : "WORKSPACE"}
            </p>

            <h1>
              {page === "Dashboard"
                ? "Cash-flow dashboard"
                : page}
            </h1>

            <p className="page-subtitle">
              {page === "Dashboard"
                ? "Understand what is coming in, what is going out, and what needs attention."
                : `Review your ${page.toLowerCase()} and their latest status.`}
            </p>
          </div>

          <span className="connection-badge">
            <span className="status-dot" />
            Connected dashboard
          </span>
        </header>

        {message && (
          <div className="notice" role="status">
            {message}
            <button
              type="button"
              onClick={() => setMessage("")}
            >
              Dismiss
            </button>
          </div>
        )}

        {errors.length > 0 && (
          <div className="error-notice" role="alert">
            <strong>Some data could not be loaded.</strong>
            <p>
              Check that Django is running and the API endpoints
              are available. Some displayed data may be outdated.
            </p>
            <ul>
              {errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
            <button
              type="button"
              disabled={loading}
              onClick={() => {
                setLoading(true);
                void loadData();
              }}
            >
              {loading ? "Retrying..." : "Try again"}
            </button>
          </div>
        )}

        {loading && (
          <p className="loading-message" role="status">
            Loading your financial data...
          </p>
        )}

        {!loading && page === "Dashboard" && (
          <>
            <section className="stats-grid">
              <StatCard
                title="Expected Inflow"
                amount={money(expectedInflow)}
                detail="Unpaid invoice receivables"
                icon="↗"
              />

              <StatCard
                title="Upcoming Expenses"
                amount={money(upcomingExpenses)}
                detail="From the latest forecast"
                icon="↘"
              />

              <StatCard
                title={forecastLabel}
                amount={forecastAmount}
                detail="Net cash position after upcoming obligations"
                icon="$"
              />

              <StatCard
                title="Overdue Invoices"
                amount={String(overdueInvoices.length)}
                detail="Needs your attention"
                icon="!"
              />
            </section>

            <section className="dashboard-grid">
              <article className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Invoice attention</h2>
                    <p>
                      Invoices that may affect your cash flow
                    </p>
                  </div>

                  <span className="count-badge">
                    {overdueInvoices.length} overdue
                  </span>
                </div>

                {overdueInvoices.length === 0 ? (
                  <p className="empty-state">
                    No overdue invoices.
                  </p>
                ) : (
                  overdueInvoices.map((invoice) => (
                    <div
                      className="invoice-row"
                      key={invoice.id}
                    >
                      <span className="row-icon">$</span>

                      <div className="row-details">
                        <strong>
                          {invoice.paypal_invoice_id}
                        </strong>
                        <p>
                          Due {invoice.due_date ?? "No due date"} ·{" "}
                          {invoice.status}
                        </p>
                        <p>
                          Risk level:{" "}
                          {invoice.risk_level || "Not assessed"}
                        </p>
                      </div>

                      <div className="row-amount">
                        <strong>
                          {money(
                            invoice.amount,
                            invoice.currency
                          )}
                        </strong>
                        <span className="overdue-label">
                          Overdue
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </article>

              <article className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>AI reminder review</h2>
                    <p>Drafts waiting for your decision</p>
                  </div>

                  <span className="pending-badge">
                    {pendingReminders.length} pending
                  </span>
                </div>

                {pendingReminders.length === 0 ? (
                  <p className="empty-state">
                    No reminders awaiting approval.
                  </p>
                ) : (
                  pendingReminders.map((reminder) => (
                    <ReminderCard
                      key={reminder.id}
                      reminder={reminder}
                      reviewing={
                        reviewingReminder === reminder.id
                      }
                      onReview={handleReminderReview}
                    />
                  ))
                )}

                <p className="safety-caption">
                  Review drafts before contacting clients. No message
                  is sent automatically.
                </p>
              </article>
            </section>

            <section className="panel expenses-panel">
              <div className="panel-heading">
                <div>
                  <h2>Upcoming expenses</h2>
                  <p>
                    Unpaid expenses recorded in your workspace
                  </p>
                </div>

                <strong>
                  {money(
                    unpaidExpenses.reduce(
                      (total, expense) =>
                        total + Number(expense.amount),
                      0
                    )
                  )}
                </strong>
              </div>

              {unpaidExpenses.length === 0 ? (
                <p className="empty-state">
                  No unpaid expenses found.
                </p>
              ) : (
                unpaidExpenses.map((expense) => (
                  <div
                    className="expense-row"
                    key={expense.id}
                  >
                    <span className="row-icon expense-icon">
                      ↗
                    </span>

                    <div className="row-details">
                      <strong>{expense.description}</strong>
                      <p>
                        {expense.category} · Due {expense.due_date}
                      </p>
                    </div>

                    <span className="unpaid-badge">Unpaid</span>

                    <strong>
                      {money(expense.amount, expense.currency)}
                    </strong>
                  </div>
                ))
              )}
            </section>
          </>
        )}

        
        {!loading && page === "Invoices" && (
          <section className="panel invoices-panel">
            <div className="panel-heading">
              <div>
                <h2>All invoices</h2>
                <p>Track invoice payments, due dates and risk levels</p>
              </div>
              <strong>{invoices.length} total</strong>
            </div>

            {invoices.length === 0 ? (
              <p className="empty-state">No invoices found.</p>
            ) : (
              <div className="data-table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Invoice</th>
                      <th>Due date</th>
                      <th>Status</th>
                      <th>Risk level</th>
                      <th className="amount-column">Amount</th>
                    </tr>
                  </thead>

                  <tbody>
                    {invoices.map((invoice) => (
                      <tr key={invoice.id}>
                        <td>
                          <strong className="table-invoice-id">
                            {invoice.paypal_invoice_id}
                          </strong>
                        </td>

                        <td>
                          {invoice.due_date ?? "No due date"}
                        </td>

                        <td>
                          <span
                            className={`table-status status-${invoice.status.toLowerCase()}`}
                          >
                            {readableStatus(invoice.status)}
                          </span>
                        </td>

                        <td>
                          <span
                            className={`table-risk risk-${(invoice.risk_level || "unknown").toLowerCase()}`}
                          >
                            {readableStatus(
                              invoice.risk_level || "Not assessed"
                            )}
                          </span>
                        </td>

                        <td className="amount-column">
                          <strong>
                            {money(invoice.amount, invoice.currency)}
                          </strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}


        {!loading && page === "Reminders" && (
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Reminder review</h2>
                <p>Review drafts before contacting clients</p>
              </div>

              <span className="pending-badge">
                {pendingReminders.length} pending
              </span>
            </div>

            {reminders.length === 0 ? (
              <p className="empty-state">No reminders found.</p>
            ) : (
              reminders.map((reminder) => (
                <ReminderCard
                  key={reminder.id}
                  reminder={reminder}
                  reviewing={
                    reviewingReminder === reminder.id
                  }
                  onReview={handleReminderReview}
                />
              ))
            )}

            <p className="safety-caption">
              Approval records your decision only. Sending is a
              separate action.
            </p>
          </section>
        )}

        {!loading && page === "Expenses" && (
          <section className="expenses-page">
            <div className="expenses-overview">
              <div className="panel-heading">
                <div>
                  <h2>Expense overview</h2>
                  <p>Monitor your upcoming business obligations</p>
                </div>

                <span className="expense-count">
                  {expenses.length} records
                </span>
              </div>

              <div className="expense-summary-grid">
                <div className="expense-summary-card">
                  <span>Total unpaid</span>
                  <strong>
                    {money(
                      expenses.reduce(
                        (total, expense) =>
                          total +
                          (expense.is_paid
                            ? 0
                            : Number(expense.amount)),
                        0
                      )
                    )}
                  </strong>
                  <small>Outstanding obligations</small>
                </div>

                <div className="expense-summary-card">
                  <span>Paid expenses</span>
                  <strong>
                    {expenses.filter((expense) => expense.is_paid).length}
                  </strong>
                  <small>Completed payments</small>
                </div>

                <div className="expense-summary-card">
                  <span>Unpaid expenses</span>
                  <strong>
                    {expenses.filter((expense) => !expense.is_paid).length}
                  </strong>
                  <small>Awaiting payment</small>
                </div>
              </div>
            </div>

            <section className="panel expense-list-panel">
              <div className="panel-heading">
                <div>
                  <h2>All expenses</h2>
                  <p>Review planned payments and their status</p>
                </div>
              </div>

              {expenses.length === 0 ? (
                <p className="empty-state">
                  No expenses found.
                </p>
              ) : (
                <div className="expense-list">
                  {expenses.map((expense) => (
                    <div className="expense-row" key={expense.id}>
                      <div className="expense-icon">
                        {expense.is_paid ? "✓" : "↗"}
                      </div>

                      <div className="expense-information">
                        <strong>{expense.description}</strong>
                        <p>
                          {expense.category} · Due {expense.due_date}
                        </p>
                      </div>

                      <span
                        className={
                          expense.is_paid
                            ? "paid-badge"
                            : "unpaid-badge"
                        }
                      >
                        {expense.is_paid ? "Paid" : "Unpaid"}
                      </span>

                      <strong className="expense-amount">
                        {money(expense.amount, expense.currency)}
                      </strong>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </section>
        )}


        <footer className="app-footer">
          Cash-Flow Guardian · Demo workspace · Forecasts are
          estimates, not guarantees.
        </footer>
      </main>
    </div>
  );
}

function StatCard({
  title,
  amount,
  detail,
  icon,
}: {
  title: string;
  amount: string;
  detail: string;
  icon: string;
}) {
  return (
    <article className="stat-card">
      <div className="stat-heading">
        <span>{title}</span>
        <span className="stat-icon">{icon}</span>
      </div>

      <div className="stat-amount">{amount}</div>
      <p>{detail}</p>
    </article>
  );
}


function ReminderCard({
  reminder,
  reviewing,
  onReview,
}: {
  reminder: Reminder;
  reviewing: boolean;
  onReview: (
    reminderId: number,
    action: "approve" | "reject"
  ) => Promise<void>;
}) {
  const pending = reminder.status === "PENDING_APPROVAL";

  const hasPlaceholder =
    /\[[^\]]+\]/.test(reminder.subject) ||
    /\[[^\]]+\]/.test(reminder.body) ||
    /\bYour Name\/Company Name\b/i.test(reminder.body) ||
    /\bYour Name\b/i.test(reminder.body) ||
    /\bYour Company\b/i.test(reminder.body) ||
    /\bAccounts Receivable\b/i.test(reminder.body);

  const statusLabel =
    reminder.status === "APPROVED"
      ? "APPROVED · NOT SENT"
      : readableStatus(reminder.status);

  const bodyPreview =
    reminder.body.length > 180
      ? reminder.body.slice(0, 180).trimEnd() + "..."
      : reminder.body;

  return (
    <article
      className={`reminder-card ${
        pending ? "reminder-card-pending" : "reminder-card-archived"
      }`}
    >
      <div className="reminder-title-row">
        <span className="row-icon">✉</span>

        <div className="row-details">
          <strong>{reminder.subject}</strong>
          <p>
            Reminder #{reminder.id} · {reminder.tone}
          </p>
        </div>

        <span
          className={`reminder-status status-${reminder.status.toLowerCase()}`}
        >
          {statusLabel}
        </span>
      </div>

      {hasPlaceholder && (
        <div className="error-notice reminder-warning" role="alert">
          <strong>Review required: placeholder text detected.</strong>
          <p>
            This reminder contains a name, company, or signature
            placeholder. Replace it with verified information before
            sending.
          </p>
        </div>
      )}

      <p className="reminder-body">
        {pending ? reminder.body : bodyPreview}
      </p>

      {pending && (
        <div className="reminder-actions">
          <button
            type="button"
            disabled={reviewing}
            onClick={() => void onReview(reminder.id, "approve")}
          >
            {reviewing ? "Processing..." : "Approve"}
          </button>

          <button
            type="button"
            disabled={reviewing}
            onClick={() => void onReview(reminder.id, "reject")}
          >
            {reviewing ? "Processing..." : "Reject"}
          </button>
        </div>
      )}

      {reminder.status === "APPROVED" && (
        <p className="safety-caption">
          Approved by the owner. This reminder has not been sent.
        </p>
      )}

      {reminder.status === "REJECTED" && (
        <p className="safety-caption">
          This reminder was rejected.
        </p>
      )}
    </article>
  );
}


export default App;
