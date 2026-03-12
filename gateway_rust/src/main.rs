use xiaomeng_gateway::{
    gateway::{GatewayManager, BaseGateway},
    http::{HttpGateway, HttpGatewayConfig},
    websocket::{WebSocketGateway, WebSocketGatewayConfig},
    cli::CliGateway,
    models::{Message, Response},
};
use std::sync::Arc;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();

    let args: Vec<String> = std::env::args().collect();
    let mode = args.get(1).map(|s| s.as_str()).unwrap_or("cli");

    match mode {
        "http" => start_http_gateway().await?,
        "websocket" => start_websocket_gateway().await?,
        "all" => start_all_gateways().await?,
        _ => start_cli_gateway().await?,
    }

    Ok(())
}

async fn start_cli_gateway() -> anyhow::Result<()> {
    println!("Starting CLI Gateway...");
    
    let mut gateway = CliGateway::new("owner");
    
    gateway.set_message_handler(Arc::new(|msg: Message| {
        Box::pin(async move {
            let response = format!("收到消息: {}", msg.content);
            Ok(Response::simple(response))
        })
    }));

    gateway.run_interactive().await?;
    Ok(())
}

async fn start_http_gateway() -> anyhow::Result<()> {
    println!("Starting HTTP Gateway...");
    
    let config = HttpGatewayConfig {
        host: "0.0.0.0".to_string(),
        port: 8080,
    };
    
    let mut gateway = HttpGateway::new(config);
    
    gateway.set_message_handler(Arc::new(|msg: Message| {
        Box::pin(async move {
            let response = format!("HTTP 收到消息: {}", msg.content);
            Ok(Response::simple(response))
        })
    }));

    gateway.start().await?;

    println!("HTTP Gateway running on http://0.0.0.0:8080");
    println!("API endpoints:");
    println!("  POST /api/chat - Send a message");
    println!("  GET  /api/health - Health check");
    println!("  GET  /ws - WebSocket connection");

    tokio::signal::ctrl_c().await?;
    println!("\nShutting down...");
    gateway.stop().await?;

    Ok(())
}

async fn start_websocket_gateway() -> anyhow::Result<()> {
    println!("Starting WebSocket Gateway...");
    
    let config = WebSocketGatewayConfig {
        host: "127.0.0.1".to_string(),
        port: 18789,
    };
    
    let mut gateway = WebSocketGateway::new(config);
    
    gateway.set_message_handler(Arc::new(|msg: Message| {
        Box::pin(async move {
            let response = format!("WebSocket 收到消息: {}", msg.content);
            Ok(Response::simple(response))
        })
    }));

    gateway.start().await?;

    println!("WebSocket Gateway running on ws://127.0.0.1:18789");

    tokio::signal::ctrl_c().await?;
    println!("\nShutting down...");
    gateway.stop().await?;

    Ok(())
}

async fn start_all_gateways() -> anyhow::Result<()> {
    println!("Starting all gateways...");
    
    let manager = GatewayManager::new();

    let http_config = HttpGatewayConfig::default();
    let mut http_gateway = HttpGateway::new(http_config);
    http_gateway.set_message_handler(Arc::new(|msg: Message| {
        Box::pin(async move {
            Ok(Response::simple(format!("回复: {}", msg.content)))
        })
    }));

    let ws_config = WebSocketGatewayConfig::default();
    let mut ws_gateway = WebSocketGateway::new(ws_config);
    ws_gateway.set_message_handler(Arc::new(|msg: Message| {
        Box::pin(async move {
            Ok(Response::simple(format!("回复: {}", msg.content)))
        })
    }));

    manager.register("http", Box::new(http_gateway)).await;
    manager.register("websocket", Box::new(ws_gateway)).await;

    manager.start_all().await?;

    println!("All gateways running:");
    println!("  HTTP: http://0.0.0.0:8080");
    println!("  WebSocket: ws://127.0.0.1:18789");

    tokio::signal::ctrl_c().await?;
    println!("\nShutting down...");
    manager.stop_all().await?;

    Ok(())
}
