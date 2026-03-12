use async_trait::async_trait;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{RwLock, mpsc};
use anyhow::Result;

use crate::models::{Message, Response, Source};

pub type MessageHandler = Arc<dyn Fn(Message) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<Response>> + Send>> + Send + Sync>;

#[async_trait]
pub trait BaseGateway: Send + Sync {
    fn source(&self) -> Source;
    
    async fn start(&mut self) -> Result<()>;
    
    async fn stop(&mut self) -> Result<()>;
    
    async fn send_message(&self, response: Response) -> Result<()>;
    
    fn is_running(&self) -> bool;
    
    fn set_message_handler(&mut self, handler: MessageHandler);
}

pub struct GatewayManager {
    gateways: Arc<RwLock<HashMap<String, Box<dyn BaseGateway>>>>,
    message_tx: mpsc::Sender<Message>,
    message_rx: Option<mpsc::Receiver<Message>>,
}

impl GatewayManager {
    pub fn new() -> Self {
        let (tx, rx) = mpsc::channel(1000);
        Self {
            gateways: Arc::new(RwLock::new(HashMap::new())),
            message_tx: tx,
            message_rx: Some(rx),
        }
    }

    pub async fn register(&self, name: impl Into<String>, gateway: Box<dyn BaseGateway>) {
        let mut gateways = self.gateways.write().await;
        gateways.insert(name.into(), gateway);
    }

    pub async fn start_all(&self) -> Result<()> {
        let mut gateways = self.gateways.write().await;
        for (name, gateway) in gateways.iter_mut() {
            tracing::info!("Starting gateway: {}", name);
            gateway.start().await?;
        }
        Ok(())
    }

    pub async fn stop_all(&self) -> Result<()> {
        let mut gateways = self.gateways.write().await;
        for (name, gateway) in gateways.iter_mut() {
            tracing::info!("Stopping gateway: {}", name);
            gateway.stop().await?;
        }
        Ok(())
    }

    pub async fn broadcast(&self, response: Response, exclude: Option<&str>) {
        let gateways = self.gateways.read().await;
        for (name, gateway) in gateways.iter() {
            if exclude.map(|e| name != e).unwrap_or(true) {
                if let Err(e) = gateway.send_message(response.clone()).await {
                    tracing::error!("Broadcast error to {}: {}", name, e);
                }
            }
        }
    }

    pub fn message_sender(&self) -> mpsc::Sender<Message> {
        self.message_tx.clone()
    }

    pub fn take_message_receiver(&mut self) -> Option<mpsc::Receiver<Message>> {
        self.message_rx.take()
    }
}

impl Default for GatewayManager {
    fn default() -> Self {
        Self::new()
    }
}
