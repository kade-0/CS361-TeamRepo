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

# Password Reset

The flow takes 3 steps: enter your email, open the emailed link, choose a new password.

1. `POST /v1/auth/password-reset/request` always returns `202` with the same message, whether or not the email has an account.
2. The link points to `RESET_URL#token=...` (default `http://localhost:3000/reset-password`).
3. `POST /v1/auth/password-reset/confirm` sets the new password. It returns `200` on success. Then:
   - the link and any other open reset links for the account stop working
   - every access token for the account is revoked, which logs it out everywhere
   - a "password changed" email is sent

Links expire after 30 minutes and work once. Requesting a new link replaces the old one. Tokens are stored as SHA-256 hashes.

`check` and `confirm` return `400` with one of these codes when the link can't be used, with a message that offers a new link:

- `token_invalid`: unknown or altered link, or replaced by a newer one
- `token_used`: already used
- `token_expired`: older than 30 minutes

`confirm` also returns `400` when the new password fails the password policy, or with `code: "password_recently_used"` when it matches the current password or one of the 4 before it.

Rate limits: `request` allows 10 per IP per 15 minutes and 3 per email address per hour. `check` and `confirm` together allow 20 per IP per 15 minutes.

Every request, rejection and completion is logged with the account id and a masked email. Tokens and passwords are never logged.

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
TLS_CERT_PATH=cert.pem
npm start
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

/v1/auth/password-reset/check, POST, Body: token 

/v1/auth/password-reset/confirm, POST, Body: token, newPassword 

/v1/accounts/me, GET, Header: Authorization: Bearer <accessToken> 

/v1/accounts/me, PATCH, Header: Authorization. Body: displayName, optional newEmail, optional currentPassword + newPassword 

/v1/accounts/me, DELETE, Header: Authorization. Body: password 

# Communication

In JSON
