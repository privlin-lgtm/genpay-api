"""Well-known ApiClient names, shared between seed_data.py (which creates them)
and the services that need to look one up (e.g. to attribute a webhook-originated
authorization to the "processor-webhook" system actor)."""

INTERNAL_ADMIN_CLIENT_NAME = "internal-admin"
PROCESSOR_WEBHOOK_CLIENT_NAME = "processor-webhook"
