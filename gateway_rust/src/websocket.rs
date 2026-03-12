use tokio_tungstenite::{accept_async, tungstenite::Message as WsMessage};
use tokio::net::TcpListener;
use std::sync::Arc;
use tokio::sync::RwLock;
use futures_util::{SinkExt, StreamExt};
use anyhow::Result;

use crate::models::{Message, Response, Source, User, UserLevel};
use crate::gateway::{BaseGateway, MessageHandler};

#[derive(Debug, Clone)]
pub struct WebSocketGatewayConfig {
    pub host: String,
    pub port: u16,
}

impl Default for WebSocketGatewayConfig {
    fn default() -> Self {
        Self {
            host: "127.0.0.1".to_string(),
            port: 18789,
        }
    }
}

pub struct WebSocketGateway {
    config: WebSocketGatewayConfig,
    running: Arc<RwLock<bool>>,
    message_handler: Arc<RwLock<Option<MessageHandler>>>,
    shutdown_tx: Option<tokio::sync::broadcast::Sender<()>>,
}

impl WebSocketGateway {
    pub fn new(config: WebSocketGatewayConfig) -> Self {
        Self {
            config,
            running: Arc::new(RwLock::new(false)),
            message_handler: Arc::new(RwLock::new(None)),
            shutdown_tx: None,
        }
    }
}

#[async_trait::async_trait]
impl BaseGateway for WebSocketGateway {
    fn source(&self) -> Source {
        Source::WebSocket
    }

    async fn start(&mut self) -> Result<()> {
        let (shutdown_tx, mut shutdown_rx) = tokio::sync::broadcast::channel(1);
        self.shutdown_tx = Some(shutdown_tx);

        let addr = format!("{}:{}", self.config.host, self.config.port);
        let listener = TcpListener::bind(&addr).await?;
        
        tracing::info!("WebSocket Gateway starting on {}", addr);
        *self.running.write().await = true;

        let running = self.running.clone();
        let message_handler = self.message_handler.clone();

        tokio::spawn(async move {
            loop {
                tokio::select! {
                    _ = shutdown_rx.recv() => {
                        tracing::info!("WebSocket Gateway shutdown signal received");
                        break;
                    }
                    accept_result = listener.accept() => {
                        match accept_result {
                            Ok((stream, addr)) => {
                                let running = running.clone();
                                let handler = message_handler.clone();
                                
                                tokio::spawn(async move {
                                    if let Ok(ws_stream) = accept_async(stream).await {
                                        tracing::debug!("WebSocket connection from {}", addr);
                                        let (mut tx, mut rx) = ws_stream.split();
                                        
                                        while let Some(msg) = rx.next().await {
                                            if !*running.read().await {
                                                break;
                                            }
                                            
                                            match msg {
                                                Ok(WsMessage::Text(text)) => {
                                                    if let Ok(req) = serde_json::from_str::<WsRequest>(&text) {
                                                        let user = User::new(req.user_id, UserLevel::Owner);
                                                        let message = Message::new(Source::WebSocket, user, req.content);
                                                        
                                                        let h = handler.read().await;
                                                        if let Some(handler) = h.as_ref() {
                                                            if let Ok(response) = handler(message).await {
                                                                let _ = tx.send(WsMessage::Text(response.content)).await;
                                                            }
                                                        }
                                                    }
                                                }
                                                Ok(WsMessage::Close(_)) => break,
                                                Err(e) => {
                                                    tracing::error!("WebSocket error: {}", e);
                                                    break;
                                                }
                                                _ => {}
                                            }
                                        }
                                    }
                                });
                            }
                            Err(e) => {
                                tracing::error!("Failed to accept connection: {}", e);
                            }
                        }
                    }
                }
            }
        });

        Ok(())
    }

    async fn stop(&mut self) -> Result<()> {
        *self.running.write().await = false;
        if let Some(tx) = &self.shutdown_tx {
            let _ = tx.send(());
        }
        tracing::info!("WebSocket Gateway stopped");
        Ok(())
    }

    async fn send_message(&self, _response: Response) -> Result<()> {
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
struct WsRequest {
    content: String,
    user_id: String,
}
