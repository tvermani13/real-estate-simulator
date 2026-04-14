"use client";

import { useEffect, useId } from "react";

type Props = Readonly<{
  open: boolean;
  onClose: () => void;
}>;

export function InstructionsModal({ open, onClose }: Props) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button className="absolute inset-0 bg-black/40" aria-label="Close instructions" onClick={onClose} />

      <dialog
        open
        aria-labelledby={titleId}
        className="relative m-0 w-full max-w-3xl overflow-hidden rounded-xl border border-zinc-200 bg-white p-0 shadow-xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-zinc-200 px-5 py-4">
          <div>
            <div id={titleId} className="text-base font-semibold text-zinc-950">
              How to use this dashboard
            </div>
            <div className="mt-1 text-sm text-zinc-600">
              A practical guide + definitions of the key terms shown in the UI.
            </div>
          </div>
          <button
            className="rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-900 hover:bg-zinc-50"
            onClick={onClose}
          >
            Close
          </button>
        </div>

        <div className="max-h-[75vh] overflow-y-auto px-5 py-4">
          <div className="grid grid-cols-1 gap-6">
            <section className="space-y-2">
              <div className="text-sm font-semibold text-zinc-900">Quick start (2 minutes)</div>
              <ol className="list-decimal pl-5 text-sm text-zinc-700 space-y-2">
                <li>
                  In <span className="font-medium">Portfolio inputs</span>, enter your portfolio value, cost basis, and an estimate of volatility.
                  (If you don’t know volatility, start with <span className="font-medium">0.20–0.25</span>.)
                </li>
                <li>
                  In <span className="font-medium">Deal inputs</span>, enter purchase price, down payment, rent, and operating expenses.
                </li>
                <li>
                  Use <span className="font-medium">SOFR shock (bps)</span> to see how higher rates affect the SBLOC deal in real time.
                </li>
                <li>
                  Read the three main outputs:
                  <ul className="mt-2 list-disc pl-5 space-y-1">
                    <li>
                      <span className="font-medium">Deal matrix</span>: monthly NOI vs monthly SBLOC interest, plus stress rows.
                    </li>
                    <li>
                      <span className="font-medium">Scenario A</span>: how much stock you may need to sell and the estimated tax drag/opportunity cost.
                    </li>
                    <li>
                      <span className="font-medium">Risk</span>: probability of breaching maintenance LTV (margin call risk) over 12/36/60 months.
                    </li>
                  </ul>
                </li>
              </ol>
            </section>

            <section className="space-y-2">
              <div className="text-sm font-semibold text-zinc-900">What each section is telling you</div>
              <div className="text-sm text-zinc-700 space-y-2">
                <div>
                  <span className="font-medium">Macro banner</span>: shows reference rates (SOFR/EFFR). SBLOC pricing is modeled as
                  {" "}
                  <span className="font-medium">SOFR + broker spread</span>.
                </div>
                <div>
                  <span className="font-medium">Deal matrix (cashflow spread)</span>: compares your property’s monthly NOI to the monthly interest-only SBLOC payment.
                  The stress rows bump SOFR by +100/+200/+300 bps to show when cashflow flips negative.
                </div>
                <div>
                  <span className="font-medium">Risk &amp; stress testing</span>: runs Monte Carlo simulations of portfolio value using your volatility estimate and reports
                  the probability that your LTV breaches the maintenance threshold (which can trigger forced liquidation).
                </div>
                <div>
                  <span className="font-medium">10-year projection</span>: a simplified comparison of net worth trajectories for do-nothing vs sell-stocks vs SBLOC.
                  Treat this as directional; it’s not tax/legal advice and doesn’t model every cashflow/tax nuance.
                </div>
              </div>
            </section>

            <section className="space-y-2">
              <div className="text-sm font-semibold text-zinc-900">Definitions (glossary)</div>
              <dl className="grid grid-cols-1 gap-3 text-sm text-zinc-700">
                <div className="rounded-lg bg-zinc-50 p-3">
                  <dt className="font-semibold text-zinc-900">SOFR</dt>
                  <dd className="mt-1">
                    Secured Overnight Financing Rate. A benchmark interest rate based on overnight Treasury repo transactions. Many SBLOCs are priced as
                    {" "}
                    <span className="font-medium">SOFR + spread</span>.
                  </dd>
                </div>
                <div className="rounded-lg bg-zinc-50 p-3">
                  <dt className="font-semibold text-zinc-900">EFFR</dt>
                  <dd className="mt-1">
                    Effective Federal Funds Rate. The volume-weighted median rate at which depository institutions lend balances to each other overnight.
                    Often used as general rate context.
                  </dd>
                </div>
                <div className="rounded-lg bg-zinc-50 p-3">
                  <dt className="font-semibold text-zinc-900">SBLOC</dt>
                  <dd className="mt-1">
                    Securities-Backed Line of Credit: a revolving line of credit collateralized by your brokerage portfolio. If your portfolio value drops,
                    your allowable borrowing may drop too.
                  </dd>
                </div>
                <div className="rounded-lg bg-zinc-50 p-3">
                  <dt className="font-semibold text-zinc-900">Spread (cashflow spread)</dt>
                  <dd className="mt-1">
                    In this dashboard: <span className="font-medium">NOI (monthly) − SBLOC interest (monthly)</span>. Positive means rent covers interest + expenses
                    (under these assumptions); negative means you need outside cash to carry the position.
                  </dd>
                </div>
                <div className="rounded-lg bg-zinc-50 p-3">
                  <dt className="font-semibold text-zinc-900">NOI</dt>
                  <dd className="mt-1">
                    Net Operating Income. Here it is modeled monthly as <span className="font-medium">rent − operating expenses</span> (interest is handled separately).
                  </dd>
                </div>
                <div className="rounded-lg bg-zinc-50 p-3">
                  <dt className="font-semibold text-zinc-900">LTV</dt>
                  <dd className="mt-1">
                    Loan-to-Value. Here: <span className="font-medium">SBLOC balance ÷ portfolio value</span>. If LTV exceeds the broker’s maintenance limit, you can be
                    forced to repay or the broker may liquidate assets.
                  </dd>
                </div>
                <div className="rounded-lg bg-zinc-50 p-3">
                  <dt className="font-semibold text-zinc-900">Maintenance requirement / maintenance LTV max</dt>
                  <dd className="mt-1">
                    The maximum LTV your broker will tolerate (example: 0.70 means your loan cannot exceed 70% of your portfolio value).
                  </dd>
                </div>
                <div className="rounded-lg bg-zinc-50 p-3">
                  <dt className="font-semibold text-zinc-900">Volatility</dt>
                  <dd className="mt-1">
                    A measure of how much returns fluctuate. Higher volatility increases the chance of large drawdowns, which increases margin-call risk.
                  </dd>
                </div>
                <div className="rounded-lg bg-zinc-50 p-3">
                  <dt className="font-semibold text-zinc-900">Monte Carlo simulation</dt>
                  <dd className="mt-1">
                    A method that runs many randomized price paths to estimate risk probabilities (e.g., probability of breaching maintenance LTV).
                  </dd>
                </div>
              </dl>
            </section>

            <section className="space-y-2">
              <div className="text-sm font-semibold text-zinc-900">Interpretation tips</div>
              <ul className="list-disc pl-5 text-sm text-zinc-700 space-y-2">
                <li>
                  If the deal is only barely cashflow-positive at today’s SOFR, the stress rows matter a lot.
                </li>
                <li>
                  Margin-call probability is highly sensitive to your volatility estimate and your maintenance limit—treat it as a risk “thermometer,” not a promise.
                </li>
                <li>
                  Always consider liquidity reserves: even a “good” deal can fail if you can’t cover a drawdown + negative carry.
                </li>
              </ul>
            </section>
          </div>
        </div>

        <div className="border-t border-zinc-200 px-5 py-3 text-xs text-zinc-500">
          This tool is for educational modeling only and does not constitute financial, tax, or legal advice.
        </div>
      </dialog>
    </div>
  );
}

