"""RepIQ platform core.

Cross-cutting foundations shared by every feature module (HR, Orders, CallIQ, SalesIQ…):
module registry, RBAC (roles + scopes), field-level projection, audit log, encryption,
the financial-month calendar, notifications, and storage.

These libraries are additive — importing this package has no side effects and does not
change any existing behaviour. Modules opt in by using them.
"""
