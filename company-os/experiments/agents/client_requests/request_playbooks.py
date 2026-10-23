"""One short playbook per kind of client request: what to ask for, the steps for the client, and the least-privilege rule."""
NEVER_LINE = "Please do not send passwords or keys in chat or email."

PLAYBOOKS = {
    "shopify_collaborator_access": {
        "title": "Shopify collaborator access",
        "ask": "Accept DevX's collaborator request on your Shopify store.",
        "steps": ["Open your Shopify admin and go to Settings, then Users.",
                  "Find the pending collaborator request from DevX and open it.",
                  "Tick only the areas we listed in the request, then accept."],
        "least_privilege": "A collaborator account, never the store owner login. Remove it when the project ends.",
        "check": "The developer opens the store admin from the collaborator account."},
    "theme_access": {
        "title": "Theme access",
        "ask": "Let the DevX developer edit the live and the draft theme.",
        "steps": ["In the Shopify admin open Settings, then Users, then the DevX collaborator.",
                  "Under permissions tick Themes only.", "Save."],
        "least_privilege": "Themes permission only. No access to orders, customers or payments.",
        "check": "The theme editor opens and a draft theme can be saved."},
    "app_install_approval": {
        "title": "App install approval",
        "ask": "Approve the app install we describe.",
        "steps": ["Open the approval request from Shopify or the link we send.",
                  "Read the permissions the app asks for.", "Approve, or tell us what to change."],
        "least_privilege": "Approve only the permissions the app needs. We list them in the request.",
        "check": "The app shows as installed in the store."},
    "dns_record": {
        "title": "DNS records",
        "ask": "Add the DNS records we list on your domain.",
        "steps": ["Sign in to the place where your domain is managed (your DNS provider).",
                  "Add each record exactly as listed in the ticket (type, name and value).",
                  "Save and tell us. It can take a few hours to show."],
        "least_privilege": "Add only the listed records. DevX gets no access to your DNS account.",
        "check": "A DNS lookup shows both records."},
    "cloud_role": {
        "title": "Cloud role",
        "ask": "Create a limited role for DevX in your cloud account.",
        "steps": ["Open your cloud console and go to the identity and access section.",
                  "Create a role from the policy file in the ticket and let the DevX account assume it.",
                  "Share the role name through the vault link."],
        "least_privilege": "A role for the staging account only, with the listed policy. No long-lived user keys.",
        "check": "The role can be assumed from the DevX build account and reads the staging resources."},
    "api_keys_via_vault": {
        "title": "API keys through the vault",
        "ask": "Add the needed keys to the vault link DevX sent you.",
        "steps": ["Open the vault link we sent.", "Add each key as a new entry with the name we listed.",
                  "Tell us when it is done. Use test keys where the provider has them."],
        "least_privilege": "Test or restricted keys only. Prefer a sign-in through your own account over a shared login.",
        "check": "The vault entry opens and a test call works."},
    "content_assets": {
        "title": "Content and files",
        "ask": "Share the files or text we list.",
        "steps": ["Open the shared folder we sent.", "Upload the files we listed.", "Tell us when they are in."],
        "least_privilege": "Share only the listed files. Remove personal data from samples.",
        "check": "The developer opens the files."},
    "decision": {
        "title": "Decision",
        "ask": "Tell us your decision on the question we list.",
        "steps": ["Read the options in the ticket.", "Reply here with the option you choose.",
                  "If you need more time, tell us the date."],
        "least_privilege": "No access is needed.",
        "check": "The decision is written down in the project record."},
}
KINDS = tuple(PLAYBOOKS)
ACCESS_KINDS = ("shopify_collaborator_access", "theme_access", "dns_record", "cloud_role", "api_keys_via_vault")


def playbook_for(kind) -> dict:
    return PLAYBOOKS[kind]


def kickoff_kinds(platform, uses_client_domain, uses_client_cloud) -> list:
    """Everything the client must give at the start, from the project profile."""
    kinds = []
    if platform == "shopify":
        kinds += ["shopify_collaborator_access", "theme_access", "app_install_approval"]
    if uses_client_domain:
        kinds.append("dns_record")
    if uses_client_cloud:
        kinds.append("cloud_role")
    return kinds + ["api_keys_via_vault", "content_assets", "decision"]
