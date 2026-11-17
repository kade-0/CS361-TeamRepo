# Accounts Microservice

This microservice handles a database for account registration, and management.

## How to send/receive data

### Sending

Send an HTTP request to an endpoint below. Send the body as JSON with the header `Content-Type: application/json`. 
Endpoints that need a logged-in user also need the header `Authorization: Bearer <accessToken>`, where the token comes from the login response.

```python
import requests

BASE_URL = "http://localhost:4000"

email = "test@example.com"
password = "my-strong-password-1930"

def register():
    res = requests.post(f"{BASE_URL}/v1/accounts", json={
        "email": email,
        "password": password,
        "displayName": "Test",
    })
    print(res.status_code, res.json())


def login():
    res = requests.post(f"{BASE_URL}/v1/auth/login", json={
        "email": email,
        "password": password,
    })
    print(res.status_code, res.json())
    return res.json().get("accessToken")
```

## Receiving

Every response comes back over the same HTTP connection as the request. Check the status code first, then read the JSON body (a 204 has no body).

```python
# ... (code from send)

def get_account(access_token):
    res = requests.get(
        f"{BASE_URL}/v1/accounts/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    print(res.status_code, res.json())
```

# Requirements

Email must be `name@domain.tld`, at most 254 characters. Must be unique.

Password must be 12-256 characters.

Display Name 1-40 characters (trimmed whitespace)

New accounts start as `pending_verification`.

# Email Verification

New accounts must verify their email before they can log in. Logging in before that returns `403` with `code: "email_not_verified"`.

Verification links expire after 24 hours and work once.

`POST /v1/accounts/verify-email` returns `200` on success, or `400` with one of these codes:

- `token_invalid`: unknown link, or replaced by a newer one
- `token_used`: already used
- `token_expired`: older than 24 hours

The link points to `VERIFY_URL` (default `http://localhost:3000/verify-email`).

# Email

Without SMTP settings, emails are written to `mail/` as JSON files instead (ignored by git). Set `MAIL_DIR` to change the folder.

To send real email, set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` and `MAIL_FROM`. Set `SMTP_SECURE=true` for port 465.

# TLS

Setup your env like so:

```
TLS_KEY_PATH=/path/to/key.pem 
TLS_CERT_PATH=/path/to/cert.pem npm start
```

## Local HTTPS for testing

Make a self-signed certificate:

```
openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=localhost" -keyout key.pem -out cert.pem
```

Setting the env (.pem is ignored by git):

```
TLS_KEY_PATH=key.pem 
TLS_CERT_PATH=cert.pem npm start
```

Point it at node:

```
ACCOUNT_SERVICE_URL=https://localhost:4000 
NODE_EXTRA_CA_CERTS=account-service/cert.pem 
npm start
```

# Schema

/v1/accounts, POST, Body: email, password, displayName 

/v1/accounts/verify-email, POST, Body: token 

/v1/accounts/verify-email/resend, POST, Body: email 

/v1/auth/password-reset/request, POST, Body: email 

/v1/auth/password-reset/confirm, POST, Body: token, newPassword 

/v1/accounts/me, GET, Header: Authorization: Bearer <accessToken> 

/v1/accounts/me, PATCH, Header: Authorization. Body: displayName, optional newEmail, optional currentPassword + newPassword 

/v1/accounts/me, DELETE, Header: Authorization. Body: password 

# Communication

In JSON
