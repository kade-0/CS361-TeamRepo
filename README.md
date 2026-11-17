# Banking Service
This service is dependent on the accounts service which must also be running.
See: https://github.com/kade-0/CS361-TeamRepo/tree/accounts

# API Documentation

...

# Certificate Creation

Run the following command to generate a self-signed certificate:
```
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 365 -subj "/CN=localhost"
```

# Interoperability Testing

Builds will be available for testing under the releases section.