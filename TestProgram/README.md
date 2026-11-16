# Running

Start the account service, then from this folder:

```
dotnet run # http://localhost:4000
dotnet run -- http://localhost:4100 # another URL
dotnet run -- https://localhost:4000 --insecure # local HTTPS with a self-signed cert
dotnet run -- --mail-dir ../mail --db ../accounts.db # where to read emails from, and the database for the expired link test
```

It exits with `0` if every test passes and `1` otherwise.