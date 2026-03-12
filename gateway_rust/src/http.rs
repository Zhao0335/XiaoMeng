use axum::{
    extract::Json,
    routing::{get, post},
    Router,
};
use std::sync::Arc;
use tokio::sync::RwLock;
use tower_http::cors::{Any, CorsLayer};
use anyhow::Result;

use crate::models::{Message, User, UserLevel};
use crate::gateway::{BaseGateway, MessageHandler};

#[derive(Debug, Clone)]
pub struct HttpGatewayConfig {
    pub host: String,
    pub port: u16,
}

impl Default for HttpGatewayConfig {
    fn default() -> Self {
        Self {
            host: "0.0.0.0".to_string(),
            port: 8080,
        }
    }
}

pub struct HttpGateway {
    config: HttpGatewayConfig,
    running: Arc<RwLock<bool>>,
    message_handler: Arc<RwLock<Option<MessageHandler>>>,
}

impl HttpGateway {
    pub fn new(config: HttpGatewayConfig) -> Self {
        Self {
            config,
            running: Arc::new(RwLock::new(false)),
            message_handler: Arc::new(RwLock::new(None)),
        }
    }
}

#[async_trait::async_trait]
impl BaseGateway for HttpGateway {
    fn source(&self) -> crate::models::Source {
        crate::models::Source::Web
    }

    async fn start(&mut self) -> Result<()> {
        let addr = format!("{}:{}", self.config.host, self.config.port);
        tracing::info!("HTTP Gateway starting on {}", addr);

        *self.running.write().await = true;

        let message_handler = self.message_handler.clone();
        let running = self.running.clone();

        tokio::spawn(async move {
            let app = Router::new()
                .route("/api/chat", post({
                    let message_handler = message_handler.clone();
                    move |Json(req): Json<ChatRequest>| {
                        let message_handler = message_handler.clone();
                        async move {
                            let user = User::new(req.user_id, req.user_level);
                            let message = Message::web(user, req.content);
                            
                            let handler = message_handler.read().await;
                            if let Some(handler) = handler.as_ref() {
                                match handler(message).await {
                                    Ok(response) => Json(ChatResponse {
                                        success: true,
                                        response: Some(response.content),
                                        error: None,
                                    }),
                                    Err(e) => Json(ChatResponse {
                                        success: false,
                                        response: None,
                                        error: Some(e.to_string()),
                                    }),
                                }
                            } else {
                                Json(ChatResponse {
                                    success: false,
                                    response: None,
                                    error: Some("No handler".to_string()),
                                })
                            }
                        }
                    }
                }))
                .route("/api/health", get(|| async { "OK" }))
                .layer(CorsLayer::new().allow_origin(Any).allow_methods(Any).allow_headers(Any));

            let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
            axum::serve(listener, app).await.ok();
        });

        Ok(())
    }

    async fn stop(&mut self) -> Result<()> {
        *self.running.write().await = false;
        tracing::info!("HTTP Gateway stopped");
        Ok(())
    }

    async fn send_message(&self, _response: crate::models::Response) -> Result<()> {
        Ok(())
    }

    fn is_running(&self) -> bool {
        futures::executor::block_on(async {
            *self.running.read().await
        })
    }

    fn set_message_handler(&mut self, handler: MessageHandler) {
        futures::executor::block_on(async {
            let mut h = self.message_handler.write().await;
            *h = Some(handler);
        });
    }
}

#[derive(serde::Deserialize)]
struct ChatRequest {
    content: String,
    user_id: String,
    #[serde(default)]
    user_level: UserLevel,
}

#[derive(serde::Serialize)]
struct ChatResponse {
    success: bool,
    response: Option<String>,
    error: Option<String>,
}
