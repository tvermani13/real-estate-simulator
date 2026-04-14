# SBLOC & Real Estate Investment Dashboard: System Architecture & Requirements

## 1. System Overview
This document outlines the architecture, data models, and algorithmic requirements for a custom application designed to model the "Buy, Borrow, Die" strategy. The system evaluates the financial viability and risk of using a Securities-Backed Line of Credit (SBLOC) to fund real estate investments versus liquidating equities.

## 2. Recommended Tech Stack
To handle both the user interface and the heavy algorithmic processing required for risk modeling, a decoupled architecture is recommended:
* **Frontend:** Next.js (React) with Tailwind CSS and Recharts/D3.js for complex data visualization.
* **Backend / Algorithmic Engine:** Python with FastAPI. Python is ideal here for utilizing libraries like `numpy` and `pandas` for Monte Carlo simulations and quantitative risk assessment.
* **Infrastructure:** AWS (e.g., deploying the API via API Gateway/Lambda or ECS, and using RDS for saving simulation states). 

## 3. Data Architecture & Inputs

### A. Manual User Inputs (The Portfolio & Deal Specs)
The application requires a state management system to hold the following user-defined parameters:
* **Portfolio Metrics:**
    * `total_portfolio_value` ($)
    * `weighted_average_cost_basis` ($ or %)
    * `portfolio_beta` or `historical_volatility` (critical for risk modeling)
    * `broker_maintenance_requirement` (e.g., 30% equity / 70% LTV limit)
* **Real Estate Deal Metrics:**
    * `property_purchase_price` ($)
    * `down_payment_required` ($)
    * `expected_monthly_rent` ($)
    * `operating_expenses` ($/month - property tax, insurance, maintenance, capex)
    * `expected_annual_appreciation` (%)

### B. Macro Data Integrations (Automated Pulls)
The backend should integrate with external APIs to dynamically fetch macroeconomic conditions:
* **Interest Rates:** Integration with the FRED (Federal Reserve Economic Data) API to pull the Secured Overnight Financing Rate (SOFR) or the Effective Federal Funds Rate. SBLOC rates are typically `SOFR + [Broker Spread]`.
* **Tax Rates:** A static lookup table or API for current IRS Long-Term Capital Gains brackets (0%, 15%, 20%) and the Net Investment Income Tax (NIIT) threshold (3.8%).
* **Market Yields:** Pulling forward yield curves to estimate future SBLOC interest rate changes.

## 4. Algorithmic Core (The "Engine")

The Python backend will execute three primary algorithmic models:

### Model 1: The Liquidity & Tax Drag Calculator (Scenario A)
If the user sells stock to fund the real estate:
1.  Calculate total capital gains based on `down_payment_required` and `weighted_average_cost_basis`.
2.  Determine the gross amount of stock that must be sold to net the required down payment after paying state and federal capital gains taxes.
3.  Calculate the opportunity cost: The lost compound growth of the gross sold amount over a 10-year horizon.

### Model 2: The SBLOC Cash Flow & Spread Analyzer (Scenario B)
If the user borrows against the portfolio:
1.  **Current Rate Calculation:** `Current SOFR + User's Tiered Broker Spread`.
2.  **Debt Service:** Calculate the monthly interest-only payment on the SBLOC.
3.  **Net Operating Income (NOI):** `expected_monthly_rent - operating_expenses`.
4.  **The Spread:** Determine if the real estate yields positive cash flow after the SBLOC debt service. 
5.  *Dynamic Adjustment:* Stress test the cash flow by algorithmically raising the SOFR by +100bps, +200bps, and +300bps to see at what interest rate the real estate deal becomes cash-flow negative.

### Model 3: Quantitative Risk Model (Margin Call Probability)
This is the most critical feature of the dashboard. Using the portfolio's historical volatility:
1.  Establish the **LTV Danger Zone** (e.g., Portfolio value drops to the point where Loan = 70% of Portfolio Value).
2.  Execute a **Monte Carlo Simulation** (e.g., 10,000 runs) projecting the portfolio's value over 12, 36, and 60 months using Geometric Brownian Motion (GBM).
3.  Output the probability (e.g., 4.2%) that the portfolio will breach the maintenance margin threshold during the investment horizon, triggering a forced liquidation.

## 5. UI/UX Dashboard Layout

### Section 1: The Command Center (Inputs & Macro Status)
* **Left Sidebar:** Form fields for Portfolio Data and Real Estate Deal Data.
* **Top Banner:** Live macro indicators pulled from APIs (Current SOFR, SBLOC Estimated Rate, S&P 500 VIX index for market volatility context).

### Section 2: The Deal Matrix (Cash Flow Analysis)
* A clean, modular card displaying the Real Estate NOI vs. SBLOC Interest.
* A traffic light indicator (Green/Yellow/Red) showing the health of the cash flow spread.
* A slider allowing the user to artificially increase the SBLOC interest rate to see real-time impact on net cash flow.

### Section 3: Risk & Stress Testing (The Quant View)
* **Visual:** A distribution curve (bell curve) showing the Monte Carlo simulation results of the portfolio's future value.
* **Key Metric:** A highly visible "Margin Call Probability" percentage. 
* **Visual:** A line chart plotting the user's current LTV against the Broker's maximum allowable LTV.

### Section 4: 10-Year Net Wealth Projection
* A comparative multi-line chart (similar to the earlier widget) projecting Total Net Worth under three scenarios:
    1.  Do Nothing (Leave money in stocks, no real estate).
    2.  Sell Stocks to Buy Real Estate.
    3.  Use SBLOC to Buy Real Estate.

## 6. Implementation Milestones
* **Phase 1:** Build the core Python mathematical models and test via CLI with static data.
* **Phase 2:** Integrate FRED API for macro data and build the FastAPI endpoints.
* **Phase 3:** Develop the Next.js frontend, focusing heavily on state management for the user inputs.
* **Phase 4:** Implement Recharts/D3 for the Monte Carlo risk visualizations.
* **Phase 5:** Deploy backend to AWS for high-performance algorithm execution and host frontend on Vercel/AWS Amplify.
