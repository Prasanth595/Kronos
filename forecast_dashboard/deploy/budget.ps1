# deploy/budget.ps1 - create a Cloud Billing budget + alert at BUDGET_AMOUNT
# USD/month for this project. Alerts fire at 50/90/100%. A budget alert
# NOTIFIES; it does not hard-cap spend. The real cost guard is the idle
# auto-stop watchdog (see vm_setup.sh).
. "$PSScriptRoot\_common.ps1"
$P = "--project=$Project"
$BudgetName   = if ($cfg['BUDGET_NAME'])   { $cfg['BUDGET_NAME'] }   else { 'kronos-demo-budget' }
$BudgetAmount = if ($cfg['BUDGET_AMOUNT']) { $cfg['BUDGET_AMOUNT'] } else { '30' }

$acctLine = (& $GcloudExe beta billing projects describe $Project `
    "--format=value(billingAccountName)" 2>$null | Select-Object -First 1)
$BillingAcct = ($acctLine -replace 'billingAccounts/', '').Trim()
if (-not $BillingAcct) {
    Write-Error "Could not resolve billing account for $Project. Link billing: https://console.cloud.google.com/billing"
    exit 1
}

Write-Host "Creating budget '$BudgetName' = `$$BudgetAmount/mo on billing acct $BillingAcct"
& $GcloudExe billing budgets create `
    "--billing-account=$BillingAcct" `
    "--display-name=$BudgetName" `
    "--budget-amount=$($BudgetAmount)USD" `
    "--filter-projects=projects/$Project" `
    --threshold-rule=percent=0.5 `
    --threshold-rule=percent=0.9 `
    --threshold-rule=percent=1.0
if ($LASTEXITCODE -ne 0) { Write-Host "(if it already exists, that's fine)" }
Write-Host "Done. Manage at https://console.cloud.google.com/billing/$BillingAcct/budgets"
