# Requirements

Email must be `name@domain.tld`, at most 254 characters. Must be unique.

Password must be 12-256 characters.

Display Name 1-40 characters (trimmed whitespace)

New accounts start as `pending_verification`.

Registration (`POST /v1/accounts`) returns the same `202` message whether or not the email is already taken. Invalid input returns `400` with an error for each field. It is limited to 5 requests per IP per minute (`429` after that).

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