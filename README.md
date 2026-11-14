# Requirements

Email must be `name@domain.tld`. Must be unique.

Password must be at least 8 characters.

Display Name 1-40 characters (trimmed whitespace)

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
