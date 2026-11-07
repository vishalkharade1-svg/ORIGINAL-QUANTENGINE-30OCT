from risk.risk_manager import RiskManager

risk = RiskManager(
    account_balance=10000,
    risk_percent=1,
)

print("Risk Amount:", risk.risk_amount())
print("Position Size:", risk.position_size(64000, 63950))