import os

# Align API keys so that if the SDK insists on using GOOGLE_API_KEY, it uses the valid GEMINI_API_KEY value
if "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

try:
    import google.auth
    google.auth.default()
except Exception:
    from google.auth.credentials import AnonymousCredentials
    google.auth.default = lambda *args, **kwargs: (AnonymousCredentials(), "mock-project")


