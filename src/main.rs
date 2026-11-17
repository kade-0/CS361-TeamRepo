use axum::{
    Json, Router,
    extract::Request,
    http::{HeaderMap, StatusCode, header::AUTHORIZATION},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use axum_server::tls_rustls::RustlsConfig;
use serde::Deserialize;
use std::{env, net::SocketAddr, process};

const PORT: u16 = 8320;

#[derive(Deserialize)]
struct AS_RegisterRequest {
    email: String,
    password: String,
    displayName: String,
}

#[derive(Deserialize)]
struct AS_LoginRequest {
    email: String,
    password: String,
}

// TODO: need to get account service port. not guaranteed to be running on port 4000. can be set with PORT env var

#[tokio::main]
async fn main() {
    let args: Vec<String> = env::args().collect();

    if args.len() != 3 {
        eprintln!("Usage: {} <cert.pem> <key.pem>", args[0]);
        eprintln!(
            "You may need to use the following command to generate a cert/key pair: openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 365 -subj \"/CN=localhost\""
        );
        process::exit(1);
    }

    let protected_router = Router::new()
        .route("/logout", post(handle_logout_from_user_account))
        .route("/create-bank-account", post(handle_create_bank_account))
        .route_layer(middleware::from_fn(require_authorization_header));

    let app = Router::new()
        .route("/register", post(handle_register_user_account))
        .route("/login", post(handle_login_to_user_account))
        .merge(protected_router);

    let config = RustlsConfig::from_pem_file(&args[1], &args[2])
        .await
        .expect("Failed to load cert/key");

    let addr = SocketAddr::from(([0, 0, 0, 0], PORT));
    println!("Banking service listening on https://{addr}");

    axum_server::bind_rustls(addr, config)
        .serve(app.into_make_service())
        .await
        .unwrap();
}

async fn handle_register_user_account(
    Json(body): Json<AS_RegisterRequest>,
) -> Result<(StatusCode, String), (StatusCode, &'static str)> {
    let client = reqwest::Client::new();

    let res = match client
        .post("https://localhost:4000/v1/accounts")
        .json(&serde_json::json!({
            "email": body.email,
            "password": body.password,
            "displayName": body.displayName,
        }))
        .send()
        .await
    {
        Ok(res) => res,
        Err(e) => {
            eprintln!("Request failed: {}", e);
            return Err((StatusCode::BAD_REQUEST, "Request failed"));
        }
    };

    let status =
        StatusCode::from_u16(res.status().as_u16()).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);
    let text = res.text().await.unwrap_or_default();

    Ok((status, text))
}

async fn handle_login_to_user_account(
    Json(body): Json<AS_LoginRequest>,
) -> Result<(StatusCode, String), (StatusCode, &'static str)> {
    let client = reqwest::Client::new();

    let res = match client
        .post("https://localhost:4000/v1/auth/login")
        .json(&serde_json::json!({
            "email": body.email,
            "password": body.password,
        }))
        .send()
        .await
    {
        Ok(res) => res,
        Err(e) => {
            eprintln!("Request failed: {}", e);
            return Err((StatusCode::BAD_REQUEST, "Request failed"));
        }
    };

    let status =
        StatusCode::from_u16(res.status().as_u16()).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);
    let text = res.text().await.unwrap_or_default();

    Ok((status, text))
}

async fn handle_logout_from_user_account(
    headers: HeaderMap,
) -> Result<(StatusCode, String), (StatusCode, &'static str)> {
    let res = reqwest::Client::new()
        .post("https://localhost:4000/v1/auth/logout")
        .header(
            reqwest::header::AUTHORIZATION,
            headers[AUTHORIZATION].as_bytes(),
        )
        .send()
        .await
        .map_err(|e| {
            eprintln!("Request failed: {}", e);
            (StatusCode::BAD_REQUEST, "Request failed")
        })?;

    let status =
        StatusCode::from_u16(res.status().as_u16()).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);
    let text = res.text().await.unwrap_or_default();

    Ok((status, text))
}

async fn handle_create_bank_account() {
    todo!("Implement")
}

async fn handle_delete_bank_account() {
    todo!("Implement")
}

async fn handle_transfer_funds_to() {
    todo!("Implement")
}

async fn handle_withdraw_funds() {
    todo!("Implement")
}

async fn handle_deposit_funds() {
    todo!("Implement")
}

async fn handle_get_transaction_history() {
    todo!("Implement")
}

async fn handle_setup_recurring_payment() {
    // No data saving necessary
    todo!("Implement")
}

async fn require_authorization_header(req: Request, next: Next) -> Response {
    if !req.headers().contains_key(AUTHORIZATION) {
        return (StatusCode::UNAUTHORIZED, "Missing Authorization header").into_response();
    }
    next.run(req).await
}
