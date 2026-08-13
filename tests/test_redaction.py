from argus.kktix.router import _redact_body_pii, _redact_headers


def test_redact_webhook_log_data_removes_secrets_and_contact_pii():
    """Remove credentials and contact details before a webhook is logged."""
    headers = {"Authorization": "Bearer token", "X-Request-ID": "request-1"}
    body = {
        "notifications": [
            {
                "contact": {
                    "name": "Chester",
                    "email": "chester@example.com",
                    "mobile": "123",
                }
            }
        ]
    }

    assert _redact_headers(headers) == {
        "Authorization": "***",
        "X-Request-ID": "request-1",
    }
    assert _redact_body_pii(body) == {
        "notifications": [{"contact": {"name": "***", "email": "***", "mobile": "***"}}]
    }
    assert body["notifications"][0]["contact"]["email"] == "chester@example.com"
