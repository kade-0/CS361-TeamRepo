using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Microsoft.Data.Sqlite;

// usage: [account service url] [--insecure] [--mail-dir <path>] [--db <path>]
// --insecure accepts self-signed certificates, for local HTTPS testing only
// --mail-dir is the service's dev inbox (MAIL_DIR), where verification emails are read from
// --db is the service's accounts.db, only needed for the expired link test
string[] valueOptions = ["--mail-dir", "--db"];
string? Option(string name) => args.SkipWhile(a => a != name).Skip(1).FirstOrDefault();
var insecure = args.Contains("--insecure");
var mailDir = Path.GetFullPath(Option("--mail-dir") ?? "../mail");
var dbPath = Option("--db");
var baseUrl = (args.Where((a, i) => !a.StartsWith("--") && (i == 0 || !valueOptions.Contains(args[i - 1]))).FirstOrDefault() ?? "http://localhost:4000").TrimEnd('/');
var baseUri = new Uri(baseUrl);

var handler = new HttpClientHandler();
if (insecure) handler.ServerCertificateCustomValidationCallback = HttpClientHandler.DangerousAcceptAnyServerCertificateValidator;
using var http = new HttpClient(handler) { BaseAddress = baseUri };

const string Password = "my-strong-password-1930@#!";
const int MaxValueLength = 64;
var tokenInLink = new Regex("#token=([A-Za-z0-9_-]+)");
var passed = 0;
var skipped = 0;
var failed = new List<string>();
var log = new List<string>();

Console.WriteLine($"Testing account service at {baseUrl}");
Console.WriteLine($"Reading emails from {mailDir}");
try
{
    await http.GetAsync("/v1/accounts/me");
}
catch (HttpRequestException e)
{
    Console.WriteLine($"Could not reach the account service: {e.Message}");
    return 1;
}

/// TESTS ///

// registration

Section("Registration");
var email = NewEmail();
string? genericBody = null;

await Test("Valid registration returns 202 with a message", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", Registration(email, displayName: "  Tester  "));
    ExpectStatus(res, HttpStatusCode.Accepted);
    Expect(!string.IsNullOrWhiteSpace(res.Json?["message"]?.GetValue<string>()), "response has no message");
    genericBody = res.Body;
});

await Test("New account starts pending verification", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/auth/login", new { email, password = Password });
    ExpectStatus(res, HttpStatusCode.Forbidden);
    ExpectCode(res, "email_not_verified");
});

await Test("Taken email gets the identical response", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", Registration(email, "a-different-pass"));
    ExpectStatus(res, HttpStatusCode.Accepted);
    ExpectEqual(genericBody, res.Body, "response body");
});

await Test("Taken email in different case gets the identical response", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", Registration(email.ToUpperInvariant()));
    ExpectStatus(res, HttpStatusCode.Accepted);
    ExpectEqual(genericBody, res.Body, "response body");
});

await Test("Registering a taken email does not change its password", async () =>
{
    // the original password still matches (403 = right password, not verified yet) and the new one doesn't
    var original = await Send(HttpMethod.Post, "/v1/auth/login", new { email, password = Password });
    ExpectStatus(original, HttpStatusCode.Forbidden);
    var other = await Send(HttpMethod.Post, "/v1/auth/login", new { email, password = "a-different-pass" });
    ExpectStatus(other, HttpStatusCode.Unauthorized);
});

await Test("Invalid email returns 400 with only an email error", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", Registration("not-an-email"));
    ExpectFieldErrors(res, "email");
});

await Test("11-character password is rejected", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", Registration(NewEmail(), "elevenchars"));
    ExpectFieldErrors(res, "password");
});

await Test("12-character password is accepted", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", Registration(NewEmail(), "twelve-chars"));
    ExpectStatus(res, HttpStatusCode.Accepted);
});

await Test("Password over 256 characters is rejected", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", Registration(NewEmail(), new string('a', 257)));
    ExpectFieldErrors(res, "password");
});

await Test("Missing display name is rejected", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", Registration(NewEmail(), displayName: "   "));
    ExpectFieldErrors(res, "displayName");
});

await Test("Display name over 40 characters is rejected", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", Registration(NewEmail(), displayName: new string('n', 41)));
    ExpectFieldErrors(res, "displayName");
});

await Test("Every bad field is reported at once", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", Registration("bad", "short", ""));
    ExpectFieldErrors(res, "email", "password", "displayName");
});

await Test("Wrong JSON types are rejected", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", rawBody: """{"email":5,"password":["x"],"displayName":{}}""");
    ExpectFieldErrors(res, "email", "password", "displayName");
});

await Test("Empty body is rejected", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", rawBody: "{}");
    ExpectFieldErrors(res, "email", "password", "displayName");
});

await Test("Malformed JSON returns 400", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", rawBody: "{bad");
    ExpectStatus(res, HttpStatusCode.BadRequest);
});

await Test("Registration is limited to 5 requests per IP per minute", async () =>
{
    var ip = NewIp();
    for (var i = 1; i <= 5; i++)
    {
        var ok = await Send(HttpMethod.Post, "/v1/accounts", rawBody: "{}", ip: ip);
        Expect(ok.Status != HttpStatusCode.TooManyRequests, $"request {i} was rate limited too early");
    }
    var res = await Send(HttpMethod.Post, "/v1/accounts", rawBody: "{}", ip: ip);
    ExpectStatus(res, HttpStatusCode.TooManyRequests);
    Expect(res.RetryAfter != null, "429 response has no Retry-After header");
});

await Test("Rate limit is tracked separately per IP", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts", rawBody: "{}");
    ExpectStatus(res, HttpStatusCode.BadRequest);
});

await Test("95% of registrations finish in under 500 ms", async () =>
{
    var times = new List<double>();
    for (var i = 0; i < 20; i++)
    {
        var watch = Stopwatch.StartNew();
        var res = await Send(HttpMethod.Post, "/v1/accounts", Registration(NewEmail()), show: i == 0);
        times.Add(watch.Elapsed.TotalMilliseconds);
        ExpectStatus(res, HttpStatusCode.Accepted);
    }
    times.Sort();
    var p95 = times[(int)Math.Ceiling(times.Count * 0.95) - 1];
    Note("(19 more registrations like this one)");
    Note($"p95 {p95:F0} ms, max {times[^1]:F0} ms");
    Expect(p95 < 500, $"p95 was {p95:F0} ms");
});

// email verification

Section("Email verification");
string? firstLink = null;
string? secondLink = null;
string? resendBody = null;

await Test("Verification email is sent within 1 minute", async () =>
{
    firstLink = await WaitForVerificationToken(email, 0);
});

await Test("Verification token has at least 128 bits of randomness", async () =>
{
    var bits = FromBase64Url(firstLink!).Length * 8;
    Note($"token decodes to {bits} bits");
    Expect(bits >= 128, $"token is only {bits} bits");
    await Task.CompletedTask;
});

await Test("Unverified account login is denied with a prompt to verify", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/auth/login", new { email, password = Password });
    ExpectStatus(res, HttpStatusCode.Forbidden);
    ExpectCode(res, "email_not_verified");
    Expect(res.Json?["error"]?.GetValue<string>().Contains("verify") == true, "message does not tell the user to verify");
});

await Test("Resend sends a new link", async () =>
{
    var res = await Resend(email);
    ExpectStatus(res, HttpStatusCode.Accepted);
    resendBody = res.Body;
    secondLink = await WaitForVerificationToken(email, 1);
    Expect(secondLink != firstLink, "the new link is the same as the old one");
});

await Test("Resend invalidates earlier links", async () =>
{
    var res = await Verify(firstLink!);
    ExpectStatus(res, HttpStatusCode.BadRequest);
    ExpectCode(res, "token_invalid");
});

await Test("Valid link activates the account", async () =>
{
    ExpectStatus(await Verify(secondLink!), HttpStatusCode.OK);
    var me = await Send(HttpMethod.Get, "/v1/accounts/me", token: await Login(email, Password));
    ExpectStatus(me, HttpStatusCode.OK);
    ExpectEqual("active", me.Json?["status"]?.GetValue<string>(), "status");
    ExpectEqual(email, me.Json?["email"]?.GetValue<string>(), "email");
    ExpectEqual("Tester", me.Json?["displayName"]?.GetValue<string>(), "trimmed displayName");
});

await Test("Used link is rejected without changing the account", async () =>
{
    var res = await Verify(secondLink!);
    ExpectStatus(res, HttpStatusCode.BadRequest);
    ExpectCode(res, "token_used");
    var me = await Send(HttpMethod.Get, "/v1/accounts/me", token: await Login(email, Password));
    ExpectEqual("active", me.Json?["status"]?.GetValue<string>(), "status");
});

await Test("Made-up link is rejected", async () =>
{
    var res = await Verify("not-a-real-token");
    ExpectStatus(res, HttpStatusCode.BadRequest);
    ExpectCode(res, "token_invalid");
});

await Test("Missing token is rejected", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/accounts/verify-email", rawBody: "{}");
    ExpectStatus(res, HttpStatusCode.BadRequest);
    ExpectCode(res, "token_invalid");
});

await Test("Resend response is identical for unknown and verified emails", async () =>
{
    var unknown = await Resend(NewEmail());
    ExpectStatus(unknown, HttpStatusCode.Accepted);
    ExpectEqual(resendBody, unknown.Body, "unknown email response");
    var verified = await Resend(email);
    ExpectStatus(verified, HttpStatusCode.Accepted);
    ExpectEqual(resendBody, verified.Body, "verified email response");
});

await Test("Resend to a verified account sends no new link", async () =>
{
    var before = VerificationTokens(email).Count;
    ExpectStatus(await Resend(email), HttpStatusCode.Accepted);
    await Task.Delay(3000);
    Note("(waited 3 s for the email worker)");
    ExpectEqual(before, VerificationTokens(email).Count, "verification emails");
});

await Test("Resend rejects an invalid email", async () =>
{
    var res = await Resend("not-an-email");
    ExpectFieldErrors(res, "email");
});

await Test("Resend is limited to 3 per hour per account", async () =>
{
    // every request comes from a different IP, so this is the per-account limit
    var target = NewEmail();
    for (var i = 1; i <= 3; i++)
        ExpectStatus(await Resend(target), HttpStatusCode.Accepted);
    var res = await Resend(target);
    ExpectStatus(res, HttpStatusCode.TooManyRequests);
    Expect(res.RetryAfter != null, "429 response has no Retry-After header");
});

await Test("Expired link is rejected and the account stays pending", async () =>
{
    if (dbPath == null) throw new SkipTest("pass --db <path to accounts.db> to run this test");
    var target = NewEmail();
    ExpectStatus(await Send(HttpMethod.Post, "/v1/accounts", Registration(target)), HttpStatusCode.Accepted);
    var link = await WaitForVerificationToken(target, 0);
    ExpireToken(link);
    var res = await Verify(link);
    ExpectStatus(res, HttpStatusCode.BadRequest);
    ExpectCode(res, "token_expired");
    var login = await Send(HttpMethod.Post, "/v1/auth/login", new { email = target, password = Password });
    ExpectCode(login, "email_not_verified");
});

// login, tokens and logout

Section("Auth");
string? wrongPasswordBody = null;

await Test("Wrong password returns 401", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/auth/login", new { email, password = "wrong-password-1" });
    ExpectStatus(res, HttpStatusCode.Unauthorized);
    wrongPasswordBody = res.Body;
});

await Test("Unknown email returns the same 401 as a wrong password", async () =>
{
    var res = await Send(HttpMethod.Post, "/v1/auth/login", new { email = NewEmail(), password = Password });
    ExpectStatus(res, HttpStatusCode.Unauthorized);
    ExpectEqual(wrongPasswordBody, res.Body, "response body");
});

await Test("GET /me without a token returns 401", async () =>
{
    var res = await Send(HttpMethod.Get, "/v1/accounts/me");
    ExpectStatus(res, HttpStatusCode.Unauthorized);
});

await Test("GET /me with a made-up token returns 401", async () =>
{
    var res = await Send(HttpMethod.Get, "/v1/accounts/me", token: "not-a-real-token");
    ExpectStatus(res, HttpStatusCode.Unauthorized);
});

await Test("Logout revokes the token", async () =>
{
    var token = await Login(email, Password);
    ExpectStatus(await Send(HttpMethod.Post, "/v1/auth/logout", token: token), HttpStatusCode.NoContent);
    ExpectStatus(await Send(HttpMethod.Get, "/v1/accounts/me", token: token), HttpStatusCode.Unauthorized);
});

Console.WriteLine();
Console.WriteLine($"{passed} passed, {failed.Count} failed, {skipped} skipped");
failed.ForEach(name => Console.WriteLine($"  FAIL  {name}"));
return failed.Count == 0 ? 0 : 1;

/// TESTS ///

// test runner functions

void Section(string name) => Console.WriteLine($"\n{name}");

async Task Test(string name, Func<Task> body)
{
    log.Clear();
    try
    {
        await body();
        passed++;
        Console.WriteLine($"  PASS  {name}");
        PrintLog();
    }
    catch (SkipTest e)
    {
        skipped++;
        Console.WriteLine($"  SKIP  {name}");
        Console.WriteLine($"        {e.Message}");
    }
    catch (Exception e)
    {
        failed.Add(name);
        Console.WriteLine($"  FAIL  {name}");
        PrintLog();
        Console.WriteLine($"        FAILED: {e.Message}");
    }
    Console.WriteLine();
}

void PrintLog() => log.ForEach(line => Console.WriteLine($"        {line}"));

void Note(string line) => log.Add(line);

string Shorten(string text)
{
    JsonNode? node;
    try { node = JsonNode.Parse(text); } catch (JsonException) { return text; }
    var changed = false;
    void Walk(JsonNode? n)
    {
        if (n is JsonObject obj)
            foreach (var (key, value) in obj.ToList())
            {
                if (value is JsonValue v && v.TryGetValue<string>(out var str) && str.Length > MaxValueLength)
                {
                    obj[key] = $"{str[..MaxValueLength]}... ({str.Length} chars)";
                    changed = true;
                }
                else Walk(value);
            }
        else if (n is JsonArray arr) arr.ToList().ForEach(Walk);
    }
    Walk(node);
    return changed ? node!.ToJsonString(new JsonSerializerOptions { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping }) : text;
}

void Expect(bool condition, string message)
{
    if (!condition) throw new TestFailure(message);
}

void ExpectEqual<T>(T expected, T actual, string what) =>
    Expect(EqualityComparer<T>.Default.Equals(expected, actual), $"{what}: expected {expected}, got {actual}");

void ExpectStatus(Response res, HttpStatusCode expected) =>
    Expect(res.Status == expected, $"expected {(int)expected} {expected}, got {(int)res.Status}: {res.Body}");

void ExpectCode(Response res, string code) =>
    ExpectEqual(code, res.Json?["code"]?.GetValue<string>(), "error code");

// a 400 that names exactly these fields

void ExpectFieldErrors(Response res, params string[] fields)
{
    ExpectStatus(res, HttpStatusCode.BadRequest);
    var got = res.Json?["fields"]?.AsObject().Select(f => f.Key).Order().ToArray() ?? [];
    var want = fields.Order().ToArray();
    Expect(got.SequenceEqual(want), $"expected field errors [{string.Join(", ", want)}], got [{string.Join(", ", got)}]");
}

// request helper functions

string NewEmail() => $"test-{Guid.NewGuid():N}@example.com";

// each request gets its own fake client IP so tests don't use up each other's rate limit
string NewIp() => $"10.{Random.Shared.Next(256)}.{Random.Shared.Next(256)}.{Random.Shared.Next(1, 255)}";

object Registration(string email, string password = Password, string displayName = "Tester") => new { email, password, displayName };

async Task<Response> Send(HttpMethod method, string path, object? body = null, string? token = null, string? ip = null, string? rawBody = null, bool show = true)
{
    using var req = new HttpRequestMessage(method, path);
    var sent = body != null ? JsonSerializer.Serialize(body) : rawBody;
    if (sent != null) req.Content = new StringContent(sent, Encoding.UTF8, "application/json");
    if (token != null) req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
    req.Headers.Add("X-Forwarded-For", ip ?? NewIp());
    if (show)
    {
        Note($"> {method} {path}");
        if (token != null) Note($"  Authorization: Bearer {token}");
        if (sent != null) Note($"  {Shorten(sent)}");
    }
    using var res = await http.SendAsync(req);
    var text = await res.Content.ReadAsStringAsync();
    if (show)
    {
        Note($"< {(int)res.StatusCode} {res.StatusCode}");
        if (res.Headers.RetryAfter != null) Note($"  Retry-After: {res.Headers.RetryAfter}");
        if (text.Length > 0) Note($"  {Shorten(text)}");
    }
    JsonNode? json = null;
    try { if (text.Length > 0) json = JsonNode.Parse(text); } catch (JsonException) { }
    return new Response(res.StatusCode, text, json, res.Headers.RetryAfter);
}

Task<Response> Verify(string token) => Send(HttpMethod.Post, "/v1/accounts/verify-email", new { token });

Task<Response> Resend(string to) => Send(HttpMethod.Post, "/v1/accounts/verify-email/resend", new { email = to });

// mailbox helper functions, reading the json files the service writes to its dev inbox

List<string> VerificationTokens(string to)
{
    if (!Directory.Exists(mailDir)) return [];
    var tokens = new List<string>();
    foreach (var file in Directory.GetFiles(mailDir, "*.json").Order())
    {
        JsonNode? mail;
        try { mail = JsonNode.Parse(File.ReadAllText(file)); } catch (Exception e) when (e is JsonException or IOException) { continue; }
        if (!string.Equals(mail?["to"]?.GetValue<string>(), to, StringComparison.OrdinalIgnoreCase)) continue;
        var match = tokenInLink.Match(mail?["text"]?.GetValue<string>() ?? "");
        if (match.Success) tokens.Add(match.Groups[1].Value);
    }
    return tokens;
}

// waits up to a minute for a verification email beyond the ones already seen, and returns its token

async Task<string> WaitForVerificationToken(string to, int alreadySeen)
{
    var watch = Stopwatch.StartNew();
    while (watch.Elapsed < TimeSpan.FromMinutes(1))
    {
        var tokens = VerificationTokens(to);
        if (tokens.Count > alreadySeen)
        {
            Note($"@ verification email to {to} arrived after {watch.ElapsedMilliseconds} ms");
            Note($"  link token: {tokens[^1]}");
            return tokens[^1];
        }
        await Task.Delay(100);
    }
    throw new TestFailure($"no verification email for {to} within 1 minute (looked in {mailDir})");
}

byte[] FromBase64Url(string value)
{
    var base64 = value.Replace('-', '+').Replace('_', '/');
    return Convert.FromBase64String(base64.PadRight(base64.Length + (4 - base64.Length % 4) % 4, '='));
}

// moves a verification token's expiry into the past, straight in the service's database

void ExpireToken(string token)
{
    var hash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(token)));
    using var connection = new SqliteConnection($"Data Source={dbPath}");
    connection.Open();
    using var command = connection.CreateCommand();
    command.CommandText = "UPDATE verification_tokens SET expires_at = $past WHERE token_hash = $hash";
    command.Parameters.AddWithValue("$past", DateTime.UtcNow.AddHours(-1).ToString("yyyy-MM-ddTHH:mm:ss.fffZ"));
    command.Parameters.AddWithValue("$hash", hash);
    Expect(command.ExecuteNonQuery() == 1, "token was not found in the database");
    Note("@ moved the token's expiry 1 hour into the past in the database (as if 24 hours had passed)");
}

async Task<string> Login(string loginEmail, string password)
{
    var res = await Send(HttpMethod.Post, "/v1/auth/login", new { email = loginEmail, password });
    ExpectStatus(res, HttpStatusCode.OK);
    return res.Json!["accessToken"]!.GetValue<string>();
}

async Task<SslProtocols> Handshake(SslProtocols protocols)
{
    using var tcp = new TcpClient();
    await tcp.ConnectAsync(baseUri.Host, baseUri.Port);
    await using var ssl = new SslStream(tcp.GetStream());
    await ssl.AuthenticateAsClientAsync(new SslClientAuthenticationOptions
    {
        TargetHost = baseUri.Host,
        EnabledSslProtocols = protocols,
        RemoteCertificateValidationCallback = insecure ? (_, _, _, _) => true : null,
    });
    return ssl.SslProtocol;
}

record Response(HttpStatusCode Status, string Body, JsonNode? Json, RetryConditionHeaderValue? RetryAfter);

class TestFailure(string message) : Exception(message);

class SkipTest(string reason) : Exception(reason);
