#!/usr/bin/env bash
# deploy/budget.sh — create a Cloud Billing budget + alert at BUDGET_AMOUNT
# USD/month for this project. Alerts fire at 50/90/100% to the billing admins'
# email. NOTE: a budget alert NOTIFIES; it does not hard-cap spend. The real
# cost guard is the idle auto-stop watchdog (see vm_setup.sh).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/config.env"

BILLING_ACCT=$(gcloud beta billing projects describe "$PROJECT" \
    --format="value(billingAccountName)" 2>/dev/null | sed 's#billingAccounts/##')
if [ -z "${BILLING_ACCT:-}" ]; then
    echo "ERROR: could not resolve billing account for $PROJECT." >&2
    echo "Link billing first: https://console.cloud.google.com/billing" >&2
    exit 1
fi

echo "Creating budget '$BUDGET_NAME' = \$$BUDGET_AMOUNT/mo on billing acct $BILLING_ACCT"
gcloud billing budgets create \
    --billing-account="$BILLING_ACCT" \
    --display-name="$BUDGET_NAME" \
    --budget-amount="${BUDGET_AMOUNT}USD" \
    --filter-projects="projects/$PROJECT" \
    --threshold-rule=percent=0.5 \
    --threshold-rule=percent=0.9 \
    --threshold-rule=percent=1.0 \
    2>&1 || echo "(if it already exists, that's fine)"
echo "Done. Manage at https://console.cloud.google.com/billing/$BILLING_ACCT/budgets"
