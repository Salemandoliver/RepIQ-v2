"""HR field-group permission map (brief §4.2), consumed by core.projection.

Scope tokens (produced by core.rbac.projection_scopes for a viewer↔target pair):
  self · manager.team · admin · admin.financial
"""
from ...core.projection import Projection, group

# Personal details
PERSONAL = Projection([
    group("self.personal",
          ["preferred_name", "profile_photo", "title", "first_name", "middle_name", "last_name",
           "dob", "sex", "gender_identity", "nationality", "about"],
          read={"self", "admin"}, write={"self", "admin"}),
    group("personal.ni",                 # National Insurance number — admin only (brief §5.1)
          ["ni_number"],
          read={"admin"}, write={"admin"}),
])

# Contact details — personal contact is self-editable; work email/phone are admin-assigned.
CONTACT = Projection([
    group("self.contact",
          ["personal_email", "personal_mobile", "addr_line1", "addr_line2", "town", "county",
           "postcode", "country", "preferred_contact_method"],
          read={"self", "admin"}, write={"self", "admin"}),
    group("contact.work",
          ["work_email", "work_phone"],
          read={"self", "manager.team", "admin"}, write={"admin"}),
])

# Emergency contacts — self + admin (never managers).
EMERGENCY = Projection([
    group("self.emergency",
          ["full_name", "relation", "phone_primary", "phone_secondary", "email", "address",
           "priority", "notes"],
          read={"self", "admin"}, write={"self", "admin"}),
])

# Role / position — visible to self, the team manager, and admin; changed by admin only.
# ``reports_to`` is a virtual field (it maps to Employee.reports_to_id, handled in services).
ROLE = Projection([
    group("role.core",
          ["department", "grade", "role_effective_date", "reports_to"],
          read={"self", "manager.team", "admin"}, write={"admin"}),
])

# Employment contract — same visibility; changed by admin only.
CONTRACT_DETAILS = Projection([
    group("contract.core",
          ["contract_type", "working_pattern", "weekly_hours", "fte", "start_date",
           "continuous_service_date", "probation_end_date", "notice_period", "work_location"],
          read={"self", "manager.team", "admin"}, write={"admin"}),
])

# Summary card shown to self, the team manager, and admin.
SUMMARY_READ = {"self", "manager.team", "admin"}
